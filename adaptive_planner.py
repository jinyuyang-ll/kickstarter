"""Adaptive Discover plan analysis for the server-side result window.

The analyzer requests page 1 for selected batches, reads total_hits, and replaces
oversized numeric ranges with smaller child batches. It never requests pages
past the configured result window.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import url_collector as collector


DEFAULT_PAGE_SIZE = 12
DEFAULT_SAFE_PAGES = 180
MAX_SPLIT_DEPTH = 12
MAX_ADAPTIVE_BATCHES = 200
SPLIT_FIELDS = ("goal", "pledged", "raised")
OPEN_RANGE_CUTS = {
    "goal": (100, 250, 500, 750, 1000, 2000, 3000, 5000, 10000, 25000, 40000, 100000),
    "pledged": (500, 1000, 2500, 5000, 10000, 25000, 50000, 100000, 250000, 500000),
    "raised": (50, 100, 200, 500, 1000, 2500, 5000),
}


class SplitLimitError(RuntimeError):
    pass


def _number(value):
    if value in (None, ""):
        return None
    return float(value)


def _display(value):
    if value is None:
        return "不限"
    return str(int(value)) if float(value).is_integer() else str(value)


def replace_query(url, updates):
    parsed = urlparse(url)
    pairs = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
             if key not in updates and key.rstrip("[]") not in updates]
    for key, value in updates.items():
        if value is not None:
            pairs.append((key, _display(value)))
    return urlunparse(parsed._replace(query=urlencode(pairs, doseq=True)))


def choose_split(url):
    """Choose a deterministic numeric split and return two URL variants."""
    query = dict(parse_qsl(urlparse(url).query, keep_blank_values=True))
    for field in SPLIT_FIELDS:
        low = _number(query.get(field + "_min"))
        high = _number(query.get(field + "_max"))
        if low is not None and high is not None:
            if high - low <= 1:
                continue
            cut = low + (high - low) / 2
        elif high is not None:
            base = low if low is not None else 0
            if high - base <= 1:
                continue
            cut = base + (high - base) / 2
        else:
            cuts = [value for value in OPEN_RANGE_CUTS[field] if low is None or value > low]
            if not cuts:
                continue
            cut = cuts[0] if low is not None else cuts[len(cuts) // 2]
        left = replace_query(url, {field + "_min": low, field + "_max": cut})
        right = replace_query(url, {field + "_min": cut, field + "_max": high})
        return field, cut, left, right
    return None


def item_from_url(parent, url, suffix, depth):
    args = collector.build_parser().parse_args(parent["args"])
    args.discover_url = url
    # The canonical URL owns all filters.
    args.term = args.category_id = args.sort = args.woe_id = None
    args.states = None
    for field in collector.RANGE_FIELDS:
        setattr(args, field, None)
    argv = ["--discover-url", collector.build_query_url(args, 1), "--output", args.output,
            "--max-pages", str(args.max_pages), "--max-projects", str(args.max_projects),
            "--delay-min", str(args.delay_min), "--delay-max", str(args.delay_max),
            "--request-mode", args.request_mode]
    for year in args.years or []:
        argv += ["--year", str(year)]
    child_args = collector.build_parser().parse_args(argv)
    identity = collector.query_signature(child_args)
    return {
        "id": identity,
        "label": (parent["label"] + " · " + suffix)[:180],
        "url": collector.build_query_url(child_args, 1),
        "years": child_args.years or [],
        "args": argv,
        "parent_id": parent.get("parent_id") or parent["id"],
        "split_depth": depth,
    }


def checkpoint_preflight(item, output, payload):
    directory = output.parent / (output.stem + ".batches")
    directory.mkdir(parents=True, exist_ok=True)
    part = directory / (item["id"] + ".csv")
    checkpoint = Path(str(part) + ".checkpoint.json")
    existing = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {}
    if existing.get("query_signature") == item["id"] and (existing.get("rows", 0) == 0 or part.exists()):
        return
    collector.write_json_atomic(checkpoint, {
        "version": 2,
        "query_signature": item["id"],
        "next_page": 1,
        "output": str(part),
        "rows": 0,
        "pending": payload,
        "old_pages": 0,
        "last_success_page": 0,
        "stop_reason": "preflight_ready",
        "complete": False,
        "last_error": None,
        "error_details": {},
        "last_page_stats": None,
        "total_hits": payload.get("total_hits"),
    })


def analyze_plan(plan_path, safe_pages=DEFAULT_SAFE_PAGES, progress=print, transport=None):
    path = Path(plan_path).resolve()
    plan = json.loads(path.read_text(encoding="utf-8"))
    safe_pages = max(1, min(200, int(safe_pages)))
    max_hits = safe_pages * DEFAULT_PAGE_SIZE
    selected = set(plan.get("selected_batch_ids") or [item["id"] for item in plan["batches"]])
    output = Path(plan["output"]).resolve()
    owns_transport = transport is None
    request_mode = plan.get("request_mode", "browser")
    transport = transport or collector.CollectionTransport(
        collector.load_config(collector.build_parser().parse_args(plan["batches"][0]["args"]).config),
        plan.get("session_mode", "shared"),
        request_mode=request_mode,
    )
    session = transport.acquire()
    first_args = collector.build_parser().parse_args(plan["batches"][0]["args"])
    session._collection_policy = collector.RequestGate(first_args.delay_min, first_args.delay_max, progress)
    session._diagnostic_secrets = transport.secrets
    session._diagnostic_sink = lambda record: progress("REQUEST_DIAGNOSTIC " + json.dumps(record, ensure_ascii=False))
    session._collection_progress = progress
    queue = [(copy.deepcopy(item), int(item.get("split_depth", 0))) for item in plan["batches"] if item["id"] in selected]
    untouched = [item for item in plan["batches"] if item["id"] not in selected]
    leaves = []
    analysis = []
    try:
        while queue:
            if len(queue) + len(leaves) + len(untouched) > MAX_ADAPTIVE_BATCHES:
                raise SplitLimitError("自动拆分将超过200个批次，请缩小原始条件范围")
            item, depth = queue.pop(0)
            args = collector.build_parser().parse_args(item["args"])
            page_url = collector.build_query_url(args, 1)
            progress("PREFLIGHT " + json.dumps({"id": item["id"], "label": item["label"], "depth": depth}, ensure_ascii=False))
            payload = collector.request_page(session, page_url, transport.proxy_url, args.timeout, args.retries)
            total_hits = payload.get("total_hits")
            if not isinstance(total_hits, int) or total_hits < 0:
                raise collector.CollectionError("preflight_total_hits_missing")
            estimated_pages = math.ceil(total_hits / DEFAULT_PAGE_SIZE)
            record = {"id": item["id"], "label": item["label"], "total_hits": total_hits,
                      "estimated_pages": estimated_pages, "depth": depth}
            if estimated_pages <= safe_pages:
                item["preflight"] = {**record, "decision": "collect"}
                checkpoint_preflight(item, output, payload)
                leaves.append(item)
                analysis.append(item["preflight"])
                continue
            split = choose_split(page_url) if depth < MAX_SPLIT_DEPTH else None
            if split is None:
                item["preflight"] = {**record, "decision": "manual_split_required"}
                leaves.append(item)
                analysis.append(item["preflight"])
                continue
            field, cut, left_url, right_url = split
            record.update(decision="split", split_field=field, split_at=cut)
            analysis.append(record)
            queue.extend([
                (item_from_url(item, left_url, f"{field}≤{_display(cut)}", depth + 1), depth + 1),
                (item_from_url(item, right_url, f"{field}≥{_display(cut)}", depth + 1), depth + 1),
            ])
    finally:
        if owns_transport:
            transport.close()
    manual = [x for x in leaves if x.get("preflight", {}).get("decision") == "manual_split_required"]
    plan["version"] = max(4, int(plan.get("version", 0)))
    plan["batches"] = untouched + leaves
    plan["selected_batch_ids"] = [item["id"] for item in leaves]
    plan["adaptive_analysis"] = analysis
    plan["adaptive_safe_pages"] = safe_pages
    plan["adaptive_status"] = "manual_required" if manual else "ready"
    collector.write_json_atomic(path, plan)
    result = {"safe_pages": safe_pages, "max_hits": max_hits, "leaf_batches": len(leaves),
              "split_events": sum(1 for x in analysis if x["decision"] == "split"),
              "manual_required": len(manual), "plan": str(path)}
    progress("ADAPTIVE_SUMMARY " + json.dumps(result, ensure_ascii=False))
    return result


def main():
    parser = argparse.ArgumentParser(description="Analyze and split oversized Discover batches")
    parser.add_argument("--plan-file", required=True)
    parser.add_argument("--safe-pages", type=int, default=DEFAULT_SAFE_PAGES)
    args = parser.parse_args()
    result = analyze_plan(args.plan_file, args.safe_pages, lambda x: print(x, flush=True))
    return 4 if result["manual_required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

\n