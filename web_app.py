"""Local-only visual control panel for the Kickstarter collection workflow."""

from __future__ import annotations

import argparse
import copy
import math
import json
import os
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import url_collector as collector


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
JOBS = {}
LOCK = threading.Lock()
LOCATION_LOCK = threading.Lock()
LOCATION_CACHE = {}
LAST_LOCATION_REQUEST = 0.0
ALLOWED_SCRIPTS = {"collect": "url_collector.py", "import": "url_importer.py", "batch": "metadata_batch_spider.py", "smoke": "smoke_test.py", "proxy": "proxy_probe.py"}


def safe_workspace_file(value, suffixes=None):
    path = (ROOT / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    if ROOT not in path.parents and path != ROOT:
        raise ValueError("文件必须位于项目目录内")
    if suffixes and path.suffix.lower() not in suffixes:
        raise ValueError("不支持的文件类型")
    return path


def public_job(job):
    return {k: v for k, v in job.items() if k != "process"}


def run_job(job_id, command):
    with LOCK:
        job = JOBS[job_id]
        job["status"] = "running"
        job["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except Exception as exc:
        with LOCK:
            job.update(status="failed", exit_code=2, finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
            job["log"].append(str(exc))
        return
    with LOCK:
        job["process"] = process
    for line in process.stdout:
        with LOCK:
            job["log"].append(line.rstrip())
            if line.startswith(("SUMMARY ", "PLAN_SUMMARY ")):
                try:
                    job["summary"] = json.loads(line.split(" ", 1)[1])
                except ValueError:
                    pass
            job["log"] = job["log"][-1000:]
    code = process.wait()
    with LOCK:
        job["exit_code"] = code
        job["status"] = "success" if code == 0 else ("partial" if code == 3 and job["kind"] == "collect" else "failed")
        job["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        job.pop("process", None)


def start_job(kind, args):
    script = ALLOWED_SCRIPTS[kind]
    command = [sys.executable, str(ROOT / script), *args]
    job_id = uuid.uuid4().hex[:10]
    job = {"id": job_id, "kind": kind, "status": "queued", "command": [script, *args], "log": [], "exit_code": None, "created_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    with LOCK:
        if kind == "collect" and any(x["kind"] == "collect" and x["status"] in ("queued", "running") for x in JOBS.values()):
            raise ValueError("已有采集任务运行中，请等待完成后再提交，避免覆盖断点和输出")
        JOBS[job_id] = job
    threading.Thread(target=run_job, args=(job_id, command), daemon=True).start()
    return public_job(job)


def collect_args(data):
    output = safe_workspace_file(data.get("output") or "candidate_urls.csv", {".csv"})
    args = ["--output", str(output), "--max-pages", str(max(1, min(500, int(data.get("max_pages", 3)))))]
    if data.get("discover_url"):
        args += ["--discover-url", str(data["discover_url"])]
    for attr in ("term", "sort"):
        if attr in data and (attr != "sort" or data[attr]):
            args += ["--" + attr, str(data[attr] or "")]
    for attr in ("category_id", "woe_id"):
        if attr in data:
            value = int(data[attr] or 0)
            if value < 0:
                raise ValueError("类别和地区 ID 必须为非负整数")
            args += ["--" + attr.replace("_", "-"), str(value)]
    for field in collector.RANGE_FIELDS:
        if field in data:
            args += ["--" + field.replace("_", "-"), str(data[field]) if data[field] is not None else ""]
    states = data.get("states") or []
    for state in states:
        if state not in ("upcoming", "live", "late_pledge", "successful", "failed", "canceled"):
            raise ValueError("无效项目状态")
        args += ["--state", state]
    for year in data.get("years") or []:
        if str(year).strip():
            args += ["--year", str(int(year))]
    args += ["--max-projects", str(max(0, int(data.get("max_projects") or 0)))]
    low, high = float(data.get("delay_min", 8)), float(data.get("delay_max", 15))
    if not all(math.isfinite(x) for x in (low, high)):
        raise ValueError("等待时间必须是有限数值")
    low = max(8, low)
    high = max(low, high)
    args += ["--delay-min", str(low), "--delay-max", str(high)]
    if data.get("resume"):
        args.append("--resume")
    # Canonicalize URL after applying controls, including explicit clear of states.
    if data.get("sort") not in (None, "", "newest", "magic", "popularity", "end_date", "most_funded", "most_backed"):
        raise ValueError("无效排序")
    parsed = collector.build_parser().parse_args(args)
    if "states" in data:
        parsed.states = states
    canonical = collector.build_query_url(parsed, 1)
    # Canonical URL owns all filters; only execution options and years stay separate.
    result = ["--discover-url", canonical, "--output", str(output), "--max-pages", str(parsed.max_pages), "--max-projects", str(parsed.max_projects), "--delay-min", str(low), "--delay-max", str(high)]
    for year in parsed.years or []:
        result += ["--year", str(year)]
    if parsed.resume:
        result.append("--resume")
    return result


def make_plan(data):
    output = safe_workspace_file(data.get("output") or "candidate_urls.csv", {".csv"})
    if output.exists() and not (output.parent / (output.stem + ".batches")).exists():
        raise ValueError("该 CSV 已存在且不是批次汇总文件，请使用新的输出文件名")
    groups = data.get("groups") or [data]
    if not isinstance(groups, list) or not 1 <= len(groups) <= 100:
        raise ValueError("每次计划应包含 1 至 100 组筛选条件")
    batches = {}
    for group_number, group in enumerate(groups, 1):
        settings = {**data, **group, "output": str(output)}
        settings.pop("groups", None)
        base_args = collect_args(settings)
        parsed = collector.build_parser().parse_args(base_args)
        query = parse_qs(urlparse(collector.build_query_url(parsed, 1)).query)
        states = query.get("state[]", query.get("state", [])) or [None]
        for state in states:
            item = copy.deepcopy(settings)
            item["states"] = [state] if state else []
            argv = collect_args(item)
            args = collector.build_parser().parse_args(argv)
            identity = collector.query_signature(args)
            url = collector.build_query_url(args, 1)
            label = str(group.get("label") or f"条件组 {group_number}")[:100] + " · " + (state or "不限状态")
            batches[identity] = {"id": identity, "label": label, "url": url, "years": args.years or [], "args": argv}
    if len(batches) > 200:
        raise ValueError("一次计划最多 200 个批次，请减少条件")
    return {"version": 1, "output": str(output), "batches": list(batches.values())}


def cached_locations(term):
    global LAST_LOCATION_REQUEST
    with LOCATION_LOCK:
        now = time.monotonic()
        if term in LOCATION_CACHE and now - LOCATION_CACHE[term][0] < 3600:
            return LOCATION_CACHE[term][1]
        if now - LAST_LOCATION_REQUEST < 8:
            raise ValueError("地区搜索请求过快，请等待 8 秒再试")
        LAST_LOCATION_REQUEST = now
        result = collector.search_locations(term, str(ROOT / "config.json"))
        LOCATION_CACHE[term] = (now, result)
        return result


def import_args(data):
    path = safe_workspace_file(data.get("file") or "candidate_urls.csv", {".csv", ".txt", ".json"})
    args = [str(path)]
    if data.get("dry_run", True):
        args.append("--dry-run")
    return args


def batch_args(data):
    args = ["--limit", str(max(1, min(10000, int(data.get("limit", 3)))))]
    if data.get("year"):
        args += ["--year", str(int(data["year"]))]
    return args


class Handler(BaseHTTPRequestHandler):
    server_version = "KickstarterControl/1.0"

    def log_message(self, fmt, *args):
        return

    def send_json(self, data, status=200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/locations":
            try:
                term = parse_qs(parsed.query).get("term", [""])[0].strip()
                self.send_json({"locations": cached_locations(term)})
            except Exception as exc:
                self.send_json({"error": str(exc)}, 400)
            return
        if parsed.path == "/api/health":
            files = []
            for pattern in ("*.csv", "*.txt", "*.json"):
                files.extend({"name": p.name, "size": p.stat().st_size, "modified": int(p.stat().st_mtime)} for p in ROOT.glob(pattern) if p.name != "config.json")
            self.send_json({"ok": True, "python": sys.version.split()[0], "root": str(ROOT), "files": sorted(files, key=lambda x: x["modified"], reverse=True)[:50]})
            return
        if parsed.path == "/api/jobs":
            with LOCK:
                self.send_json([public_job(x) for x in reversed(list(JOBS.values()))])
            return
        if parsed.path.startswith("/api/jobs/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            with LOCK:
                job = JOBS.get(job_id)
                self.send_json(public_job(job) if job else {"error": "job_not_found"}, 200 if job else 404)
            return
        name = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
        path = (WEB_DIR / name).resolve()
        if WEB_DIR not in path.parents or not path.is_file():
            self.send_error(404)
            return
        content = path.read_bytes()
        ctype = "text/html; charset=utf-8" if path.suffix == ".html" else "text/plain; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        try:
            data = self.read_json()
            route = self.path.rstrip("/")
            if route == "/api/plan/preview":
                self.send_json(make_plan(data))
                return
            if route == "/api/jobs/collect":
                plan = make_plan(data)
                path = ROOT / ".collection" / (uuid.uuid4().hex + ".json")
                collector.write_json_atomic(path, plan)
                job = start_job("collect", ["--plan-file", str(path)])
            elif route == "/api/jobs/import":
                job = start_job("import", import_args(data))
            elif route == "/api/jobs/batch":
                job = start_job("batch", batch_args(data))
            elif route == "/api/jobs/smoke":
                job = start_job("smoke", [])
            elif route == "/api/jobs/proxy":
                job = start_job("proxy", [])
            else:
                self.send_json({"error": "not_found"}, 404)
                return
            self.send_json(job, HTTPStatus.ACCEPTED)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 400)


def main():
    parser = argparse.ArgumentParser(description="Kickstarter local visual control panel")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost"):
        print("警告：界面包含任务执行能力，默认只应绑定本机 127.0.0.1。", file=sys.stderr)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"Kickstarter 控制台已启动: {url}", flush=True)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
