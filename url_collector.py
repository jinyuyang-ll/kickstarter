"""Low-frequency Kickstarter Discover URL collector with CSV audit trail.

This module only builds a candidate URL set.  It never writes to MySQL; use
url_importer.py after reviewing the generated CSV.
"""

from __future__ import annotations

import argparse
import base64
import copy
import math
import csv
import datetime as dt
import hashlib
import json
import os
import random
import sys
import time
import uuid
from http.cookiejar import LoadError, MozillaCookieJar
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from curl_cffi import requests

from project_metadata_spider import build_proxy_url
from url_importer import normalize_url
from request_control import RequestGate, parse_retry_after
import request_diagnostics as diagnostics


BASE_URL = "https://www.kickstarter.com/discover/advanced.json"
CSV_FIELDS = (
    "project_url",
    "project_id",
    "project_name",
    "launched_at",
    "launched_year",
    "project_state",
    "category",
    "subcategory",
    "country",
    "source",
    "source_query",
    "source_page",
    "collected_at",
)
CHALLENGE_MARKERS = ("captcha", "verify you are human", "cf-chl-", "security check", "just a moment")
COOKIE_STORE_DIR = Path(__file__).resolve().parent / ".collection" / "session_state"
CHALLENGE_COOLDOWN_SECONDS = 60 * 60


RANGE_FIELDS = tuple(f"{kind}_{bound}" for kind in ("goal", "pledged", "raised") for bound in ("min", "max"))
COMPLETE_REASONS = {"no_more_results", "passed_requested_years"}
STOP_LABELS = {'no_more_results': '本查询结果已结束', 'passed_requested_years': '已翻过目标年份', 'max_pages': '本轮页数用完，可续跑', 'max_projects': '本轮数量用完，可续跑', 'suspected_pagination_limit': '疑似分页受限，请拆细条件', 'request_failed': '请求失败，进度已保存'}


class CollectionError(RuntimeError):
    def __init__(self, message, **details):
        super().__init__(message)
        self.details = details


ERROR_LABELS = {
    "rate_limited": "HTTP 429：请求受限，已暂停后续批次",
    "forbidden": "HTTP 403：访问被拒绝，需检查访问状态",
    "verification_page": "收到 HTML 验证页面，已暂停后续批次",
    "unexpected_response": "响应格式异常，进度已保存",
    "retry_after_active": "尚未到服务端允许重试的时间，本次未发送请求",
    "challenge_cooldown_active": "Cloudflare 验证冷却中，本次未发送请求",
}


def utc_iso(timestamp):
    if timestamp in (None, ""):
        return ""
    return dt.datetime.fromtimestamp(int(timestamp), tz=dt.timezone.utc).isoformat()


def load_config(path):
    config_path = Path(path)
    if not config_path.exists():
        return {}
    return json.loads(config_path.read_text(encoding="utf-8"))


def proxy_from_config(config):
    proxy = config.get("proxy_config") or {}
    if not proxy.get("enable_proxy"):
        return None
    hosts = proxy.get("proxy_host_list") or []
    if not hosts:
        raise CollectionError("proxy_enabled_but_no_host")
    return build_proxy_url(
        random.choice(hosts),
        proxy.get("proxy_port", 10030),
        proxy.get("proxy_username") or "",
        proxy.get("proxy_pwd") or "",
    )


def validate_discover_url(value):
    parsed = urlparse(value or BASE_URL)
    if parsed.scheme != "https" or parsed.netloc.lower() not in {
        "kickstarter.com",
        "www.kickstarter.com",
    }:
        raise ValueError("discover URL must use https://www.kickstarter.com")
    if not parsed.path.startswith("/discover"):
        raise ValueError("discover URL path must start with /discover")
    path = parsed.path
    if not path.endswith(".json"):
        path = path.rstrip("/") + ".json"
    return urlunparse(("https", "www.kickstarter.com", path, "", parsed.query, ""))


def build_query_url(args, page):
    base = validate_discover_url(args.discover_url)
    parsed = urlparse(base)
    pairs = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "page"]
    def replace(key, values):
        nonlocal pairs
        pairs = [(k, v) for k, v in pairs if k not in (key, key + "[]")]
        pairs.extend((key, str(value)) for value in values)

    # None inherits the URL; explicit empty values clear a control.
    for attr, key in (("term", "term"), ("category_id", "category_id"), ("sort", "sort"), ("woe_id", "woe_id")):
        value = getattr(args, attr, None)
        if value is not None:
            replace(key, [] if value in ("", 0, "0") else [value])
    if args.states is not None:
        replace("state", [])
        pairs.extend(("state[]", state) for state in args.states)
    for kind in ("goal", "pledged", "raised"):
        values = [getattr(args, f"{kind}_{bound}", None) for bound in ("min", "max")]
        if any(value is not None for value in values):
            replace(kind, [])
            for bound, value in zip(("min", "max"), values):
                replace(f"{kind}_{bound}", [] if value in (None, "") else [value])
    if not any(k == "sort" for k, _ in pairs):
        pairs.append(("sort", "newest"))
    effective = dict(pairs)
    for kind in ("goal", "pledged", "raised"):
        bounds = []
        for bound in ("min", "max"):
            value = effective.get(f"{kind}_{bound}")
            number = float(value) if value not in (None, "") else None
            if number is not None and (not math.isfinite(number) or number < 0):
                raise ValueError('金额和比例必须是非负有限数值')
            bounds.append(number)
        if all(x is not None for x in bounds) and bounds[0] >= bounds[1]:
            raise ValueError('区间上限必须大于下限；留空表示不限')
    pairs.append(("page", str(page)))
    return urlunparse(parsed._replace(query=urlencode(pairs, doseq=True)))


def query_signature(args):
    url = build_query_url(args, 1)
    parsed = urlparse(url)
    pairs = sorted((k, v) for k, v in parse_qsl(parsed.query) if k != "page")
    raw = urlunparse(parsed._replace(query=urlencode(pairs, doseq=True)))
    raw += json.dumps(sorted(set(args.years or [])))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def load_existing(path):
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        rows.extend(csv.DictReader(source))
    return rows


def write_csv_atomic(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp, path)


def project_to_row(project, source_url, page, collected_at):
    url = normalize_url((((project.get("urls") or {}).get("web") or {}).get("project")))
    if not url:
        return None
    launched_at = utc_iso(project.get("launched_at"))
    category = project.get("category") or {}
    return {
        "project_url": url,
        "project_id": project.get("id") or "",
        "project_name": project.get("name") or "",
        "launched_at": launched_at,
        "launched_year": launched_at[:4] if launched_at else "",
        "project_state": project.get("state") or "",
        "category": category.get("parent_name") or category.get("name") or "",
        "subcategory": category.get("name") or "",
        "country": project.get("country_displayable_name") or project.get("country") or "",
        "source": "kickstarter_discover",
        "source_query": source_url,
        "source_page": page,
        "collected_at": collected_at,
    }


def cookie_scope(proxy_url):
    if not proxy_url:
        return "direct"
    parsed = urlparse(proxy_url)
    endpoint = f"{parsed.scheme}|{parsed.hostname or ''}|{parsed.port or ''}"
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:12]


def kickstarter_cookies(session):
    cookies = []
    for cookie in session.cookies.jar:
        domain = (cookie.domain or "").lstrip(".").lower()
        if (domain == "kickstarter.com" or domain.endswith(".kickstarter.com")) and not cookie.is_expired():
            cookies.append(cookie)
    return cookies


def kickstarter_cookie_count(session):
    try:
        return len(kickstarter_cookies(session))
    except (AttributeError, TypeError):
        return 0


class CollectionTransport:
    """One proxy per plan, with task-local connections and persisted site cookies."""
    def __init__(self, config, mode="shared", cookie_store_dir=None):
        if mode not in ("shared", "per_batch"):
            raise ValueError("无效连接模式")
        self.proxy_url = proxy_from_config(config)
        self.mode = mode
        self.secrets = diagnostics.configuration_secrets(config)
        store = Path(cookie_store_dir) if cookie_store_dir is not None else COOKIE_STORE_DIR
        self.cookie_path = store / ("kickstarter-" + cookie_scope(self.proxy_url) + ".txt") if mode == "shared" else None
        self.cookie_state_status = "not_loaded" if self.cookie_path else "disabled"
        self.restored_cookie_count = 0
        self.session = None

    def _load_cookies(self, session):
        if not self.cookie_path or not self.cookie_path.exists():
            self.cookie_state_status = "empty" if self.cookie_path else "disabled"
            return
        jar = MozillaCookieJar(str(self.cookie_path))
        try:
            jar.load(ignore_discard=True, ignore_expires=False)
            for cookie in jar:
                domain = (cookie.domain or "").lstrip(".").lower()
                if domain == "kickstarter.com" or domain.endswith(".kickstarter.com"):
                    session.cookies.jar.set_cookie(copy.copy(cookie))
            self.restored_cookie_count = len(kickstarter_cookies(session))
            self.cookie_state_status = "restored"
        except (LoadError, OSError):
            self.cookie_state_status = "invalid"

    def persist_cookies(self):
        if not self.cookie_path or self.session is None:
            return {"status": "disabled", "cookie_count": 0}
        cookies = kickstarter_cookies(self.session)
        if not cookies and not self.cookie_path.exists():
            self.cookie_state_status = "empty"
            return {"status": "empty", "cookie_count": 0}
        self.cookie_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cookie_path.with_suffix(self.cookie_path.suffix + ".tmp")
        jar = MozillaCookieJar(str(temporary))
        for cookie in cookies:
            jar.set_cookie(copy.copy(cookie))
        try:
            jar.save(ignore_discard=True, ignore_expires=False)
            os.replace(temporary, self.cookie_path)
            try:
                os.chmod(self.cookie_path, 0o600)
            except OSError:
                pass
            self.cookie_state_status = "saved"
            return {"status": "saved", "cookie_count": len(cookies)}
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            self.cookie_state_status = "save_failed"
            return {"status": "save_failed", "cookie_count": len(cookies)}

    def acquire(self):
        if self.session is None:
            self.session = requests.Session()
            self._load_cookies(self.session)
            self.session._diagnostic_session_id = uuid.uuid4().hex[:12]
            self.session._cookie_state_status = self.cookie_state_status
            self.session._restored_cookie_count = self.restored_cookie_count
            self.session._persist_cookie_state = self.persist_cookies
            self.session._challenge_cooldown_seconds = CHALLENGE_COOLDOWN_SECONDS
        return self.session

    def release_batch(self):
        if self.mode == "per_batch":
            self.close()

    def close(self):
        if self.session is not None:
            self.session.close()
            self.session = None


def request_page(session, url, proxy_url, timeout, retries):
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    policy = getattr(session, "_collection_policy", None)
    policy = policy if isinstance(policy, RequestGate) else None
    sink = getattr(session, "_diagnostic_sink", None)
    session_id = getattr(session, "_diagnostic_session_id", "")
    session_id = session_id if isinstance(session_id, str) else ""
    secret_values = getattr(session, "_diagnostic_secrets", ())
    secret_values = secret_values if isinstance(secret_values, (list, tuple)) else ()
    last_error = CollectionError("unknown")
    for attempt in range(1, retries + 1):
        if policy:
            policy.before_request()
        started_at = diagnostics.timestamp()
        started = time.monotonic()
        cookie_state = getattr(session, "_cookie_state_status", "unknown")
        cookie_state = cookie_state if isinstance(cookie_state, str) else "unknown"
        restored_count = getattr(session, "_restored_cookie_count", 0)
        restored_count = restored_count if isinstance(restored_count, int) else 0
        request_info = {
            "requested_at": started_at,
            "request_url": diagnostics.safe_url(url),
            "attempt": attempt,
            "session_id": session_id,
            "cookie_state": cookie_state,
            "restored_cookie_count": restored_count,
            **diagnostics.network_context(proxy_url),
        }
        try:
            response = session.get(
                url,
                headers={"accept": "application/json", "accept-language": "en-US,en;q=0.9"},
                proxies=proxies, timeout=timeout, impersonate="chrome124",
            )
        except Exception as exc:
            request_info.update(elapsed_ms=round((time.monotonic() - started) * 1000), kind="network_error", exception_type=type(exc).__name__)
            if callable(sink):
                sink(request_info)
            last_error = CollectionError(type(exc).__name__ + ": network request failed", **request_info)
        else:
            status = response.status_code
            headers = getattr(response, "headers", {})
            content_type = headers.get("content-type", "")
            content_type = content_type if isinstance(content_type, str) else ""
            retry_after = parse_retry_after(headers.get("retry-after"))
            request_info.update(
                elapsed_ms=round((time.monotonic() - started) * 1000),
                http_status=status,
                content_type=content_type[:150],
                final_url=diagnostics.safe_url(getattr(response, "url", url)),
                session_cookie_count=kickstarter_cookie_count(session),
            )
            secrets = [*secret_values, *diagnostics.cookie_secrets(session)]
            details = dict(request_info)
            if retry_after is not None:
                details["retry_after_seconds"] = retry_after
                if policy and status != 200:
                    details["retry_at"] = policy.defer(retry_after)
            text = (response.text or "")[:20000].lower()
            looks_html = "text/html" in content_type.lower() or text.lstrip().startswith(("<!doctype html", "<html"))
            if status == 200:
                try:
                    payload = response.json()
                except (ValueError, TypeError):
                    payload = None
                # Parse valid listing JSON first: project text is not evidence of a challenge.
                if isinstance(payload, dict) and isinstance(payload.get("projects"), list) and isinstance(payload.get("has_more"), bool):
                    success = {**request_info, "kind": "listing_json", "returned": len(payload["projects"]), "total_hits": payload.get("total_hits")}
                    persist_cookie_state = getattr(session, "_persist_cookie_state", None)
                    if callable(persist_cookie_state):
                        success["cookie_state_save"] = persist_cookie_state()
                    if callable(sink):
                        sink(success)
                    return payload
            details.update(diagnostics.response_details(response, secrets))
            explicit_challenge = str(headers.get("cf-mitigated", "")).lower() == "challenge"
            is_verification = explicit_challenge or (looks_html and any(marker in text for marker in CHALLENGE_MARKERS))
            if is_verification:
                kind = "verification_page"
                if policy and retry_after is None:
                    cooldown = getattr(session, "_challenge_cooldown_seconds", CHALLENGE_COOLDOWN_SECONDS)
                    cooldown = cooldown if isinstance(cooldown, (int, float)) and cooldown >= 0 else CHALLENGE_COOLDOWN_SECONDS
                    details["local_cooldown_seconds"] = cooldown
                    details["cooldown_source"] = "local_safety_policy"
                    details["retry_at"] = policy.defer(cooldown, reason="cloudflare_challenge")
            elif status == 429:
                kind = "rate_limited"
            elif status == 403:
                kind = "forbidden"
            else:
                kind = "unexpected_response"
            details["kind"] = kind
            if callable(sink):
                sink(details)
            message = "verification_page" if kind == "verification_page" else ("invalid_discover_payload" if status == 200 else f"http_{status}")
            last_error = CollectionError(message, **details)
            if status in (200, 403, 404, 429) or kind == "verification_page" or retry_after is not None:
                raise last_error
        if attempt < retries and not policy:
            time.sleep(min(20, 3 * (2 ** (attempt - 1))) + random.uniform(0, 1))
    raise last_error


def write_json_atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def collect_urls(args, progress=print, transport=None):
    output = Path(args.output).resolve()
    checkpoint = Path(args.checkpoint or (str(output) + ".checkpoint.json"))
    signature = query_signature(args)
    saved = {}
    if args.resume and checkpoint.exists():
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        if saved.get("query_signature") != signature:
            raise CollectionError("checkpoint_query_mismatch: 条件或年份已改变（旧版断点也不兼容），请新建批次")
        if saved.get("rows", 0) and not output.exists():
            raise CollectionError("checkpoint_output_missing: CSV 已丢失，不能跳过已采集页面")
    page = max(1, int(saved.get("next_page", 1)))
    by_url = {row["project_url"]: row for row in load_existing(output) if row.get("project_url")}
    years = set(args.years or [])
    effective_sort = dict(parse_qsl(urlparse(build_query_url(args, 1)).query)).get("sort")
    owns_transport = transport is None
    transport = transport or CollectionTransport(load_config(args.config))
    proxy_url = transport.proxy_url
    session = transport.acquire()
    session._collection_policy = RequestGate(args.delay_min, args.delay_max, progress)
    session._diagnostic_secrets = transport.secrets
    session._diagnostic_sink = lambda record: progress("REQUEST_DIAGNOSTIC " + json.dumps(record, ensure_ascii=False))
    new_count = pages_done = 0
    old_pages = int(saved.get("old_pages", 0))
    last_success = int(saved.get("last_success_page", 0))
    pending = saved.get("pending")
    reason = saved.get("stop_reason") if saved.get("complete") else "max_pages"
    error = None
    error_details = {}
    last_page_stats = saved.get("last_page_stats")
    total_hits = saved.get("total_hits")

    def persist():
        write_csv_atomic(output, list(by_url.values()))
        write_json_atomic(checkpoint, {
            "version": 2, "query_signature": signature, "next_page": page,
            "output": str(output), "rows": len(by_url), "pending": pending,
            "old_pages": old_pages, "last_success_page": last_success,
            "stop_reason": reason, "complete": reason in COMPLETE_REASONS,
            "last_error": error, "error_details": error_details, "last_page_stats": last_page_stats, "total_hits": total_hits,
            "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
        })

    try:
        while not saved.get("complete") and pages_done < args.max_pages:
            page_url = build_query_url(args, page)
            progress(f"PAGE [{pages_done + 1}/{args.max_pages}] {diagnostics.safe_url(page_url)}")
            try:
                if pending is not None:
                    progress("CACHE_RESUME " + json.dumps({"at": diagnostics.timestamp(), "page": page, "remaining": len(pending["projects"]), "network_request": False}))
                payload = pending if pending is not None else request_page(session, page_url, proxy_url, args.timeout, args.retries)
                if not isinstance(payload, dict) or not isinstance(payload.get("projects"), list) or not isinstance(payload.get("has_more"), bool):
                    raise CollectionError("invalid_discover_payload")
                if not payload["projects"] and payload["has_more"]:
                    raise CollectionError("empty_page_with_more_results")
            except Exception as exc:
                error = str(exc)
                error_details = getattr(exc, "details", {})
                progress("REQUEST_ERROR " + json.dumps({"page": page, "error": error, **error_details}, ensure_ascii=False))
                reason = "suspected_pagination_limit" if error == "http_404" and page > 1 and last_success == page - 1 else "request_failed"
                persist()
                break
            projects = payload["projects"]
            total_hits = payload.get("total_hits", total_hits)
            collected_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            page_years = list(payload.get("page_years", []))
            accepted = 0
            skipped_year = skipped_invalid = skipped_duplicate = skipped_missing_year = 0
            observed_years = {}
            remainder = []
            for index, project in enumerate(projects):
                row = project_to_row(project, page_url, page, collected_at)
                if not row:
                    skipped_invalid += 1
                    continue
                year = int(row["launched_year"]) if row["launched_year"].isdigit() else None
                if year:
                    page_years.append(year)
                    observed_years[str(year)] = observed_years.get(str(year), 0) + 1
                if years and year not in years:
                    if year is None:
                        skipped_missing_year += 1
                    else:
                        skipped_year += 1
                    continue
                if row["project_url"] not in by_url:
                    by_url[row["project_url"]] = row
                    new_count += 1
                    accepted += 1
                    if args.max_projects and new_count >= args.max_projects:
                        remainder = projects[index + 1:]
                        break
                else:
                    skipped_duplicate += 1
            pages_done += 1
            last_page_stats = {"page": page, "returned": len(projects), "accepted": accepted, "skipped_year": skipped_year, "skipped_missing_year": skipped_missing_year, "skipped_invalid_url": skipped_invalid, "skipped_duplicate": skipped_duplicate, "remaining": len(remainder), "observed_years": observed_years, "requested_years": sorted(years)}
            progress(f"PAGE_RESULT page={page} returned={len(projects)} accepted={accepted} total={len(by_url)} skipped_year={skipped_year} skipped_missing_year={skipped_missing_year} skipped_invalid_url={skipped_invalid} skipped_duplicate={skipped_duplicate} remaining={len(remainder)}")
            progress("PAGE_FILTER " + json.dumps(last_page_stats, ensure_ascii=False))
            if remainder:
                # Persist the actual unprocessed records, not a fragile index in a changing live page.
                pending = {"projects": remainder, "has_more": payload["has_more"], "page_years": page_years, "total_hits": total_hits}
                reason = "max_projects"
            else:
                pending = None
                last_success = page
                page += 1
                old_pages = old_pages + 1 if years and effective_sort == "newest" and page_years and max(page_years) < min(years) else 0
                if not payload["has_more"]:
                    reason = "no_more_results"
                elif old_pages >= args.stop_after_old_pages:
                    reason = "passed_requested_years"
                elif args.max_projects and new_count >= args.max_projects:
                    reason = "max_projects"
                else:
                    reason = "max_pages"
            persist()
            if reason in COMPLETE_REASONS or reason == "max_projects":
                break
    finally:
        if owns_transport:
            transport.close()
        else:
            transport.release_batch()
    summary = {
        "output": str(output), "pages_processed": pages_done, "new_urls": new_count,
        "total_urls": len(by_url), "next_page": page, "stop_reason": reason,
        "stop_label": ERROR_LABELS.get(error_details.get("kind"), STOP_LABELS.get(reason, reason)), "complete": reason in COMPLETE_REASONS,
        "query_signature": signature, "error": error, "error_details": error_details, "last_page_stats": last_page_stats, "total_hits": total_hits,
    }
    progress("SUMMARY " + json.dumps(summary, ensure_ascii=False))
    return summary


def search_locations(term, config_path="config.json"):
    from lxml import html
    if not 2 <= len(term.strip()) <= 100:
        raise ValueError('请输入 2 至 100 个字符的国家、州或城市名称（建议英文）')
    proxy = proxy_from_config(load_config(config_path))
    proxies = {"http": proxy, "https": proxy} if proxy else None
    with requests.Session() as session:
        page = session.get("https://www.kickstarter.com/discover/advanced", impersonate="chrome124", proxies=proxies, timeout=25)
        if page.status_code != 200:
            raise CollectionError(f"地区搜索初始化失败 HTTP {page.status_code}")
        csrf = html.fromstring(page.text).xpath('//meta[@name="csrf-token"]/@content')
        if not csrf:
            raise CollectionError("地区搜索不可用，请稍后再试")
        response = session.post("https://www.kickstarter.com/graph", json={
            "operationName": "Locations",
            "query": "query Locations($term: String!) { locations(term: $term) { edges { node { id displayableName } } } }",
            "variables": {"term": term.strip()},
        }, headers={"x-csrf-token": csrf[0], "accept": "application/json", "origin": "https://www.kickstarter.com", "referer": "https://www.kickstarter.com/discover/advanced"}, impersonate="chrome124", proxies=proxies, timeout=25)
        if response.status_code != 200:
            raise CollectionError(f"地区搜索失败 HTTP {response.status_code}")
        data = response.json()
        if data.get("errors"):
            raise CollectionError("地区搜索不可用，请稍后再试")
        locations = []
        for edge in data["data"]["locations"]["edges"]:
            node = edge.get("node")
            if node:
                decoded = base64.b64decode(node["id"]).decode()
                identity = decoded.removeprefix("Location-")
                if identity.isdigit():
                    locations.append({"id": identity, "name": node["displayableName"]})
        return locations


def batch_snapshot(item, directory):
    part = directory / (item["id"] + ".csv")
    checkpoint = Path(str(part) + ".checkpoint.json")
    saved = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {}
    valid = saved.get("query_signature") == item["id"] and (not saved.get("rows") or part.exists())
    return {"complete": bool(valid and saved.get("complete")), "next_page": saved.get("next_page", 1), "total_urls": len(load_existing(part)), "previous_stop_reason": saved.get("stop_reason"), "last_page_stats": saved.get("last_page_stats")}


def collect_plan(plan_path, progress=print):
    plan_path = Path(plan_path).resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    all_ids = {item["id"] for item in plan["batches"]}
    selection = plan.get("selected_batch_ids")
    selected = all_ids if selection is None else set(selection)
    if not selected or not selected <= all_ids:
        raise ValueError("请选择有效批次；筛选条件变化后请重新预览")
    selected_args = [build_parser().parse_args(item["args"]) for item in plan["batches"] if item["id"] in selected]
    configs = {str(Path(args.config).resolve()) for args in selected_args}
    if len(configs) != 1:
        raise ValueError("同一计划须使用同一个网络配置文件")
    request_settings = selected_args[0]
    output = Path(plan["output"])
    directory = output.parent / (output.stem + ".batches")
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    results = []
    # Selection never narrows the accumulated output; all existing URLs are retained.
    merged = {row["project_url"]: row for row in load_existing(output) if row.get("project_url")}
    for item in plan["batches"]:
        for row in load_existing(directory / (item["id"] + ".csv")):
            merged[row["project_url"]] = row
    halted = False
    mode = plan.get("session_mode", "shared")
    transport = CollectionTransport(load_config(next(iter(configs))), mode)
    progress("PLAN_SETTINGS " + json.dumps({
        "at": diagnostics.timestamp(),
        "batch_count": len(all_ids),
        "selected_count": len(selected),
        "max_pages_per_batch": request_settings.max_pages,
        "max_projects_per_batch": request_settings.max_projects,
        "delay_min_seconds": request_settings.delay_min,
        "delay_max_seconds": request_settings.delay_max,
        "session_mode": mode,
        "cookie_state_persistence": mode == "shared",
        "challenge_cooldown_seconds": CHALLENGE_COOLDOWN_SECONDS,
        **diagnostics.network_context(transport.proxy_url),
    }, ensure_ascii=False))
    try:
        for index, item in enumerate(plan["batches"]):
            chosen = item["id"] in selected
            args = build_parser().parse_args(item["args"])
            args.output = str(directory / (item["id"] + ".csv"))
            args.resume = True
            args.checkpoint = None
            executed = False
            if not chosen or halted:
                result = {**batch_snapshot(item, directory), "stop_reason": "not_selected" if not chosen else "not_run", "stop_label": "本轮未选择，原进度保留" if not chosen else "上个批次请求失败，本批次未运行"}
            else:
                progress(f"BATCH {index + 1}/{len(plan['batches'])} {item['label']}")
                executed = True
                try:
                    result = collect_urls(args, progress, transport=transport)
                except Exception as exc:
                    result = {"complete": False, "stop_reason": "request_failed", "stop_label": "请求或断点失败", "error": type(exc).__name__ if not isinstance(exc, CollectionError) else str(exc)}
                halted = result["stop_reason"] == "request_failed"
                for row in load_existing(Path(args.output)):
                    merged[row["project_url"]] = row
            results.append({"id": item["id"], "label": item["label"], "selected": chosen, "executed": executed, **result})
            write_csv_atomic(output, list(merged.values()))
            write_json_atomic(manifest_path, {"plan": str(plan_path), "batches": results, "total_urls": len(merged)})
    finally:
        transport.close()
    summary = {"output": str(output), "manifest": str(manifest_path), "session_mode": mode, "total_urls": len(merged), "batches": results, "complete": all(x["complete"] for x in results), "selected_complete": all(x["complete"] for x in results if x["selected"]), "failed": any(x["executed"] and x["stop_reason"] == "request_failed" for x in results)}
    write_json_atomic(manifest_path, summary)
    progress("PLAN_SUMMARY " + json.dumps(summary, ensure_ascii=False))
    return summary


def build_parser():
    parser = argparse.ArgumentParser(description="Collect candidate project URLs from Kickstarter Discover")
    parser.add_argument("--discover-url", default=BASE_URL, help="可直接粘贴浏览器中的 Discover/Search URL")
    parser.add_argument("--term", default=None, help="搜索关键词")
    parser.add_argument("--category-id", type=int, help="Kickstarter 类别 ID，例如 Games=12")
    parser.add_argument("--state", dest="states", action="append", choices=("upcoming", "live", "late_pledge", "successful", "failed", "canceled"))
    parser.add_argument("--sort", default=None, choices=("newest", "magic", "popularity", "end_date", "most_funded", "most_backed"))
    parser.add_argument("--woe-id", type=int, help="地区 ID；0 表示不限")
    for field in RANGE_FIELDS:
        parser.add_argument("--" + field.replace("_", "-"), help="金额 USD；raised 为百分比；空字符串清除范围")
    parser.add_argument("--plan-file", help="控制台生成的分批计划")
    parser.add_argument("--year", dest="years", action="append", type=int, help="按 launched_at 年份保留，可重复")
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--max-projects", type=int, default=0)
    parser.add_argument("--delay-min", type=float, default=8)
    parser.add_argument("--delay-max", type=float, default=15)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--stop-after-old-pages", type=int, default=2)
    parser.add_argument("--output", default="candidate_urls.csv")
    parser.add_argument("--checkpoint")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--config", default="config.json")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.max_pages = max(1, args.max_pages)
    args.max_projects = max(0, args.max_projects)
    args.delay_min = max(0, args.delay_min)
    args.delay_max = max(args.delay_min, args.delay_max)
    try:
        if args.plan_file:
            summary = collect_plan(args.plan_file, lambda message: print(message, flush=True))
            return 2 if summary["failed"] else (0 if summary["complete"] else 3)
        summary = collect_urls(args, lambda message: print(message, flush=True))
        return 2 if summary["stop_reason"] == "request_failed" else (0 if summary["complete"] else 3)
    except (CollectionError, ValueError, json.JSONDecodeError) as exc:
        print(f"COLLECT_FAILED {exc}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
