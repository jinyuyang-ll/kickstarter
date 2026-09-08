"""Local-only visual control panel for the Kickstarter collection workflow."""

from __future__ import annotations

import argparse
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


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
JOBS = {}
LOCK = threading.Lock()
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
    with LOCK:
        job["process"] = process
    for line in process.stdout:
        with LOCK:
            job["log"].append(line.rstrip())
            job["log"] = job["log"][-1000:]
    code = process.wait()
    with LOCK:
        job["exit_code"] = code
        job["status"] = "success" if code == 0 else "failed"
        job["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        job.pop("process", None)


def start_job(kind, args):
    script = ALLOWED_SCRIPTS[kind]
    command = [sys.executable, str(ROOT / script), *args]
    job_id = uuid.uuid4().hex[:10]
    job = {"id": job_id, "kind": kind, "status": "queued", "command": [script, *args], "log": [], "exit_code": None, "created_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    with LOCK:
        JOBS[job_id] = job
    threading.Thread(target=run_job, args=(job_id, command), daemon=True).start()
    return public_job(job)


def collect_args(data):
    output = safe_workspace_file(data.get("output") or "candidate_urls.csv", {".csv"})
    args = ["--output", str(output), "--max-pages", str(max(1, min(500, int(data.get("max_pages", 3)))))]
    if data.get("discover_url"):
        args += ["--discover-url", str(data["discover_url"])]
    if data.get("term"):
        args += ["--term", str(data["term"])]
    if data.get("category_id"):
        args += ["--category-id", str(int(data["category_id"]))]
    args += ["--sort", str(data.get("sort") or "newest")]
    for state in data.get("states") or []:
        args += ["--state", str(state)]
    for year in data.get("years") or []:
        if str(year).strip():
            args += ["--year", str(int(year))]
    if data.get("max_projects"):
        args += ["--max-projects", str(max(0, int(data["max_projects"])))]
    args += ["--delay-min", str(max(0, float(data.get("delay_min", 8)))), "--delay-max", str(max(0, float(data.get("delay_max", 15))))]
    if data.get("resume"):
        args.append("--resume")
    return args


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
            if route == "/api/jobs/collect":
                job = start_job("collect", collect_args(data))
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
