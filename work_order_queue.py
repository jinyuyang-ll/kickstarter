"""Persistent, serial work-order queue for the local control panel."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS work_orders (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    plan_path TEXT NOT NULL,
    log_path TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    next_run_at REAL NOT NULL,
    repeat_hours REAL NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 100,
    last_exit_code INTEGER,
    last_error TEXT,
    summary_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_work_orders_due
ON work_orders(status, next_run_at, created_at);
"""


class WorkOrderStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    @contextmanager
    def database(self):
        db = self.connect()
        try:
            with db:
                yield db
        finally:
            db.close()

    def initialize(self):
        with self.database() as db:
            db.executescript(SCHEMA)
            db.execute("UPDATE work_orders SET status='queued', last_error='recovered_after_restart' WHERE status='running'")

    def create(self, title, spec, plan_path, next_run_at=None, repeat_hours=0, max_attempts=100):
        now = time.time()
        identity = uuid.uuid4().hex[:12]
        log_path = self.path.parent / "work_order_logs" / (identity + ".txt")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.database() as db:
            db.execute(
                """INSERT INTO work_orders
                   (id,title,status,spec_json,plan_path,log_path,created_at,updated_at,
                    next_run_at,repeat_hours,max_attempts)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (identity, str(title)[:200], "queued", json.dumps(spec, ensure_ascii=False),
                 str(plan_path), str(log_path), now, now, float(next_run_at or now),
                 max(0, float(repeat_hours)), max(1, int(max_attempts))),
            )
        return self.get(identity)

    def row(self, value):
        if value is None:
            return None
        result = dict(value)
        result["spec"] = json.loads(result.pop("spec_json"))
        result["summary"] = json.loads(result.pop("summary_json")) if result.get("summary_json") else None
        result.pop("summary_json", None)
        result["log_url"] = "/api/work-orders/" + result["id"] + "/log"
        result["batches"] = []
        try:
            plan = json.loads(Path(result["plan_path"]).read_text(encoding="utf-8"))
            manifest_path = Path(plan["output"]).parent / (Path(plan["output"]).stem + ".batches") / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
            states = {item.get("id"): item for item in manifest.get("batches", [])}
            for item in plan.get("batches", []):
                state = states.get(item.get("id"), {})
                result["batches"].append({
                    "id": item.get("id"),
                    "label": item.get("label"),
                    "selected": item.get("id") in set(plan.get("selected_batch_ids") or [x.get("id") for x in plan.get("batches", [])]),
                    "estimated_pages": (item.get("preflight") or {}).get("estimated_pages"),
                    "decision": (item.get("preflight") or {}).get("decision"),
                    "complete": state.get("complete"),
                    "next_page": state.get("next_page", 1),
                    "total_urls": state.get("total_urls", 0),
                    "stop_reason": state.get("stop_reason"),
                })
        except (OSError, ValueError, TypeError):
            pass
        return result

    def get(self, identity):
        with self.database() as db:
            return self.row(db.execute("SELECT * FROM work_orders WHERE id=?", (identity,)).fetchone())

    def list(self, limit=200):
        with self.database() as db:
            rows = db.execute("SELECT * FROM work_orders ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self.row(row) for row in rows]

    def claim_due(self):
        now = time.time()
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM work_orders WHERE status='running' LIMIT 1").fetchone():
                db.rollback()
                return None
            row = db.execute(
                """SELECT * FROM work_orders
                   WHERE status='queued' AND next_run_at<=? AND attempts<max_attempts
                   ORDER BY next_run_at, created_at LIMIT 1""", (now,)
            ).fetchone()
            if row is None:
                db.rollback()
                return None
            changed = db.execute(
                """UPDATE work_orders SET status='running', attempts=attempts+1,
                   updated_at=?, last_error=NULL WHERE id=? AND status='queued'""",
                (now, row["id"]),
            ).rowcount
            db.commit()
            return self.get(row["id"]) if changed else None
        finally:
            db.close()

    def finish(self, identity, exit_code, summary=None, error=None):
        order = self.get(identity)
        now = time.time()
        repeat = order["repeat_hours"] * 3600
        if exit_code == 0:
            status, next_at = "success", order["next_run_at"]
        elif exit_code == 4:
            status, next_at = "needs_attention", order["next_run_at"]
        elif repeat and order["attempts"] < order["max_attempts"]:
            status, next_at = "queued", now + repeat
        else:
            status = "partial" if exit_code == 3 else "failed"
            next_at = order["next_run_at"]
        with self.database() as db:
            db.execute(
                """UPDATE work_orders SET status=?,next_run_at=?,updated_at=?,
                   last_exit_code=?,last_error=?,summary_json=? WHERE id=?""",
                (status, next_at, now, exit_code, str(error)[:1000] if error else None,
                 json.dumps(summary, ensure_ascii=False) if summary else None, identity),
            )
        return self.get(identity)

    def action(self, identity, action):
        order = self.get(identity)
        if not order:
            raise ValueError("工单不存在")
        now = time.time()
        if action == "pause" and order["status"] in ("queued", "partial", "failed"):
            status, next_at = "paused", order["next_run_at"]
        elif action in ("resume", "run_now") and order["status"] in ("paused", "partial", "failed", "needs_attention", "queued"):
            status, next_at = "queued", now
        elif action == "cancel" and order["status"] != "running":
            status, next_at = "canceled", order["next_run_at"]
        else:
            raise ValueError("当前状态不能执行该操作")
        with self.database() as db:
            db.execute("UPDATE work_orders SET status=?,next_run_at=?,updated_at=? WHERE id=?",
                       (status, next_at, now, identity))
        return self.get(identity)


class QueueWorker:
    def __init__(self, store, root):
        self.store = store
        self.root = Path(root)
        self.stop_event = threading.Event()
        self.thread = None
        self.process = None
        self.active_id = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self.loop, name="work-order-worker", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def command(self, order):
        spec = order["spec"]
        command = [sys.executable, str(self.root / "pipeline_runner.py"),
                   "--plan-file", order["plan_path"],
                   "--safe-pages", str(spec.get("safe_pages", 180)),
                   "--config", str(self.root / "config.json"),
                   "--schema", str(self.root / "metadata_schema.sql")]
        if spec.get("auto_split", True):
            command.append("--auto-split")
        if spec.get("run_metadata", False):
            command.append("--run-metadata")
            command += ["--metadata-limit", str(max(0, int(spec.get("metadata_limit", 0))))]
            if spec.get("metadata_year"):
                command += ["--metadata-year", str(int(spec["metadata_year"]))]
        if spec.get("excel_output"):
            command += ["--excel-output", str(spec["excel_output"])]
        return command

    def loop(self):
        while not self.stop_event.is_set():
            order = self.store.claim_due()
            if order is None:
                self.stop_event.wait(1)
                continue
            self.run(order)

    def run(self, order):
        self.active_id = order["id"]
        log_path = Path(order["log_path"])
        command = self.command(order)
        summary = None
        error = None
        exit_code = 2
        env = __import__("os").environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            with log_path.open("a", encoding="utf-8") as log:
                log.write("WORK_ORDER_STARTED " + json.dumps({"id": order["id"], "at": time.time(), "attempt": order["attempts"]}, ensure_ascii=False) + "\n")
                log.flush()
                self.process = subprocess.Popen(
                    command, cwd=self.root, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                    errors="replace", env=env,
                )
                for line in self.process.stdout:
                    log.write(line)
                    log.flush()
                    if line.startswith("PIPELINE_SUMMARY "):
                        try:
                            summary = json.loads(line.split(" ", 1)[1])
                        except ValueError:
                            pass
                exit_code = self.process.wait()
                log.write("WORK_ORDER_FINISHED " + json.dumps({"at": time.time(), "exit_code": exit_code}) + "\n")
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        finally:
            process = self.process
            if process is not None:
                if process.poll() is None:
                    try:
                        process.terminate()
                        process.wait(timeout=5)
                    except Exception:
                        process.kill()
                if process.stdout is not None:
                    process.stdout.close()
            self.process = None
            self.active_id = None
            self.store.finish(order["id"], exit_code, summary, error)

\n