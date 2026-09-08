"""Low-frequency Kickstarter Discover URL collector with CSV audit trail.

This module only builds a candidate URL set.  It never writes to MySQL; use
url_importer.py after reviewing the generated CSV.
"""

from __future__ import annotations

import argparse
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
    keys = {key for key, _ in pairs}
    if args.term and "term" not in keys:
        pairs.append(("term", args.term))
    if args.category_id and "category_id" not in keys and "category_id[]" not in keys:
        pairs.append(("category_id", str(args.category_id)))
    if "sort" not in keys:
        pairs.append(("sort", args.sort))
    if args.states and "state" not in keys and "state[]" not in keys:
        pairs.extend(("state[]", state) for state in args.states)
    pairs.append(("page", str(page)))
    return urlunparse(parsed._replace(query=urlencode(pairs, doseq=True)))


def query_signature(args):
    url = build_query_url(args, 1)
    parsed = urlparse(url)
    pairs = sorted((k, v) for k, v in parse_qsl(parsed.query) if k != "page")
    raw = urlunparse(parsed._replace(query=urlencode(pairs, doseq=True)))
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
                return response.json()
            last_error = "security_challenge" if challenged else f"http_{response.status_code}"
            if challenged:
                break
        except Exception as exc:  # network errors are intentionally bounded
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(min(20, 3 * (2 ** (attempt - 1))) + random.uniform(0, 1))
    raise CollectionError(last_error)


def collect_urls(args, progress=print):
    output = Path(args.output).resolve()
    checkpoint = Path(args.checkpoint or (str(output) + ".checkpoint.json"))
    signature = query_signature(args)
    start_page = 1
    if args.resume and checkpoint.exists():
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        if saved.get("query_signature") != signature:
            raise CollectionError("checkpoint_query_mismatch")
        start_page = max(1, int(saved.get("next_page", 1)))

    rows = load_existing(output)
    by_url = {row.get("project_url"): row for row in rows if row.get("project_url")}
    years = set(args.years or [])
    config = load_config(args.config)
    proxy_url = proxy_from_config(config)
    session = requests.Session()
    new_count = 0
    pages_done = 0
    consecutive_old_pages = 0
    stop_reason = "max_pages"

    for page in range(start_page, start_page + args.max_pages):
        page_url = build_query_url(args, page)
        progress(f"PAGE [{pages_done + 1}/{args.max_pages}] {page_url}")
        try:
            payload = request_page(session, page_url, proxy_url, args.timeout, args.retries)
        except Exception as exc:
            checkpoint.write_text(json.dumps({
                "query_signature": signature,
                "next_page": page,
                "output": str(output),
                "last_error": str(exc),
                "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            write_csv_atomic(output, list(by_url.values()))
            raise

        projects = payload.get("projects") or []
        collected_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        page_years = []
        accepted = 0
        for project in projects:
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
                    stop_reason = "max_projects"
                    break

        pages_done += 1
        write_csv_atomic(output, list(by_url.values()))
        checkpoint.write_text(json.dumps({
            "query_signature": signature,
            "next_page": page + 1,
            "output": str(output),
            "rows": len(by_url),
            "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        progress(f"PAGE_RESULT page={page} returned={len(projects)} accepted={accepted} total={len(by_url)}")

        if args.max_projects and new_count >= args.max_projects:
            break
        if not payload.get("has_more") or not projects:
            stop_reason = "no_more_results"
            break
        if years and args.sort == "newest" and page_years and max(page_years) < min(years):
            consecutive_old_pages += 1
            if consecutive_old_pages >= args.stop_after_old_pages:
                stop_reason = "passed_requested_years"
                break
        else:
            consecutive_old_pages = 0
        if page < start_page + args.max_pages - 1:
            time.sleep(random.uniform(args.delay_min, args.delay_max))

    summary = {
        "output": str(output),
        "pages_processed": pages_done,
        "new_urls": new_count,
        "total_urls": len(by_url),
        "next_page": start_page + pages_done,
        "stop_reason": stop_reason,
        "query_signature": signature,
    }
    progress("SUMMARY " + json.dumps(summary, ensure_ascii=False))
    return summary


def build_parser():
    parser = argparse.ArgumentParser(description="Collect candidate project URLs from Kickstarter Discover")
    parser.add_argument("--discover-url", default=BASE_URL, help="可直接粘贴浏览器中的 Discover/Search URL")
    parser.add_argument("--term", default="", help="搜索关键词")
    parser.add_argument("--category-id", type=int, help="Kickstarter 类别 ID，例如 Games=12")
    parser.add_argument("--state", dest="states", action="append", choices=("upcoming", "live", "late_pledge", "successful", "failed", "canceled"))
    parser.add_argument("--sort", default="newest", choices=("newest", "magic", "popularity", "end_date", "most_funded", "most_backed"))
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
        collect_urls(args, lambda message: print(message, flush=True))
        return 0
    except (CollectionError, ValueError, json.JSONDecodeError) as exc:
        print(f"COLLECT_FAILED {exc}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
