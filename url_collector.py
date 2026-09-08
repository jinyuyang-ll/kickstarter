"""Low-frequency Kickstarter Discover URL collector with CSV audit trail.

This module only builds a candidate URL set.  It never writes to MySQL; use
url_importer.py after reviewing the generated CSV.
"""

from __future__ import annotations

import argparse
import base64
import math
import csv
import datetime as dt
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from curl_cffi import requests

from project_metadata_spider import build_proxy_url
from url_importer import normalize_url


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
CHALLENGE_MARKERS = ("captcha", "verify you are human", "cf-chl-", "security check")


RANGE_FIELDS = tuple(f"{kind}_{bound}" for kind in ("goal", "pledged", "raised") for bound in ("min", "max"))
COMPLETE_REASONS = {"no_more_results", "passed_requested_years"}
STOP_LABELS = {'no_more_results': '本查询结果已结束', 'passed_requested_years': '已翻过目标年份', 'max_pages': '本轮页数用完，可续跑', 'max_projects': '本轮数量用完，可续跑', 'suspected_pagination_limit': '疑似分页受限，请拆细条件', 'request_failed': '请求失败，进度已保存'}


class CollectionError(RuntimeError):
    pass


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


def request_page(session, url, proxy_url, timeout, retries):
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    last_error = "unknown"
    for attempt in range(1, retries + 1):
        try:
            response = session.get(
                url,
                headers={"accept": "application/json", "accept-language": "en-US,en;q=0.9"},
                proxies=proxies,
                timeout=timeout,
                impersonate="chrome124",
            )
            text = (response.text or "")[:20000].lower()
            challenged = response.status_code in (403, 429) or any(x in text for x in CHALLENGE_MARKERS)
            if response.status_code == 200 and not challenged:
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("projects"), list) or not isinstance(payload.get("has_more"), bool):
                    raise ValueError("invalid_discover_payload")
                return payload
            last_error = "security_challenge" if challenged else f"http_{response.status_code}"
            if challenged or response.status_code == 404:
                break
        except Exception as exc:  # network errors are intentionally bounded
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(min(20, 3 * (2 ** (attempt - 1))) + random.uniform(0, 1))
    raise CollectionError(last_error)


def write_json_atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def collect_urls(args, progress=print):
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
    proxy_url = proxy_from_config(load_config(args.config))
    session = requests.Session()
    new_count = pages_done = 0
    old_pages = int(saved.get("old_pages", 0))
    last_success = int(saved.get("last_success_page", 0))
    pending = saved.get("pending")
    reason = saved.get("stop_reason") if saved.get("complete") else "max_pages"
    error = None
    total_hits = saved.get("total_hits")

    def persist():
        write_csv_atomic(output, list(by_url.values()))
        write_json_atomic(checkpoint, {
            "version": 2, "query_signature": signature, "next_page": page,
            "output": str(output), "rows": len(by_url), "pending": pending,
            "old_pages": old_pages, "last_success_page": last_success,
            "stop_reason": reason, "complete": reason in COMPLETE_REASONS,
            "last_error": error, "total_hits": total_hits,
            "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
        })

    try:
        while not saved.get("complete") and pages_done < args.max_pages:
            page_url = build_query_url(args, page)
            progress(f"PAGE [{pages_done + 1}/{args.max_pages}] {page_url}")
            try:
                payload = pending if pending is not None else request_page(session, page_url, proxy_url, args.timeout, args.retries)
                if not isinstance(payload, dict) or not isinstance(payload.get("projects"), list) or not isinstance(payload.get("has_more"), bool):
                    raise CollectionError("invalid_discover_payload")
                if not payload["projects"] and payload["has_more"]:
                    raise CollectionError("empty_page_with_more_results")
            except Exception as exc:
                error = str(exc)
                reason = "suspected_pagination_limit" if error == "http_404" and page > 1 and last_success == page - 1 else "request_failed"
                persist()
                break
            projects = payload["projects"]
            total_hits = payload.get("total_hits", total_hits)
            collected_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            page_years = list(payload.get("page_years", []))
            accepted = 0
            remainder = []
            for index, project in enumerate(projects):
                row = project_to_row(project, page_url, page, collected_at)
                if not row:
                    continue
                year = int(row["launched_year"]) if row["launched_year"].isdigit() else None
                if year:
                    page_years.append(year)
                if years and year not in years:
                    continue
                if row["project_url"] not in by_url:
                    by_url[row["project_url"]] = row
                    new_count += 1
                    accepted += 1
                    if args.max_projects and new_count >= args.max_projects:
                        remainder = projects[index + 1:]
                        break
            pages_done += 1
            progress(f"PAGE_RESULT page={page} returned={len(projects)} accepted={accepted} total={len(by_url)}")
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
            if pages_done < args.max_pages:
                time.sleep(random.uniform(args.delay_min, args.delay_max))
    finally:
        session.close()
    summary = {
        "output": str(output), "pages_processed": pages_done, "new_urls": new_count,
        "total_urls": len(by_url), "next_page": page, "stop_reason": reason,
        "stop_label": STOP_LABELS.get(reason, reason), "complete": reason in COMPLETE_REASONS,
        "query_signature": signature, "error": error, "total_hits": total_hits,
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


def collect_plan(plan_path, progress=print):
    plan_path = Path(plan_path).resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    output = Path(plan["output"])
    directory = output.parent / (output.stem + ".batches")
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    results = []
    merged = {}
    # Only merge files belonging to this plan, never unrelated old queries.
    for item in plan["batches"]:
        part = directory / (item["id"] + ".csv")
        for row in load_existing(part):
            merged[row["project_url"]] = row
    halted = False
    for index, item in enumerate(plan["batches"]):
        args = build_parser().parse_args(item["args"])
        args.output = str(directory / (item["id"] + ".csv"))
        args.resume = True
        args.checkpoint = None
        if halted:
            result = {"complete": False, "stop_reason": "not_run", "stop_label": "上个批次请求失败，本批次未运行"}
        else:
            progress(f"BATCH {index + 1}/{len(plan['batches'])} {item['label']}")
            try:
                result = collect_urls(args, progress)
            except Exception as exc:
                result = {"complete": False, "stop_reason": "request_failed", "stop_label": "请求或断点失败", "error": str(exc)}
            halted = result["stop_reason"] == "request_failed"
            for row in load_existing(Path(args.output)):
                merged[row["project_url"]] = row
        results.append({"id": item["id"], "label": item["label"], **result})
        write_csv_atomic(output, list(merged.values()))
        write_json_atomic(manifest_path, {"plan": str(plan_path), "batches": results, "total_urls": len(merged)})
        if not halted and index + 1 < len(plan["batches"]):
            time.sleep(random.uniform(args.delay_min, args.delay_max))
    summary = {"output": str(output), "manifest": str(manifest_path), "total_urls": len(merged), "batches": results, "complete": all(x["complete"] for x in results), "failed": any(x["stop_reason"] == "request_failed" for x in results)}
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
