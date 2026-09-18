"""Run one work order: adaptive URL planning, collection, metadata, Excel."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import adaptive_planner
import excel_exporter
import metadata_batch_spider as metadata
import url_collector
import url_importer


def emit(stage, status, **details):
    print("PIPELINE_STAGE " + json.dumps({"stage": stage, "status": status, **details}, ensure_ascii=False), flush=True)


def run(args):
    plan_path = Path(args.plan_file).resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    output = Path(plan["output"]).resolve()
    excel_path = Path(args.excel_output or output.with_suffix(".xlsx")).resolve()
    summary = {"plan": str(plan_path), "output": str(output), "excel": str(excel_path), "stages": {}}
    try:
        if args.auto_split and plan.get("adaptive_status") not in ("ready", "manual_required"):
            emit("analyze", "running", safe_pages=args.safe_pages)
            analyzed = adaptive_planner.analyze_plan(plan_path, args.safe_pages, lambda x: print(x, flush=True))
            summary["stages"]["analyze"] = analyzed
            if analyzed["manual_required"]:
                emit("analyze", "manual_required", count=analyzed["manual_required"])
                summary["status"] = "manual_required"
                return 4
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            emit("analyze", "success", leaf_batches=analyzed["leaf_batches"])
        emit("collect", "running")
        collected = url_collector.collect_plan(plan_path, lambda x: print(x, flush=True))
        summary["stages"]["collect"] = {
            "total_urls": collected["total_urls"],
            "selected_complete": collected["selected_complete"],
            "failed": collected["failed"],
        }
        if collected["failed"]:
            emit("collect", "failed")
            summary["status"] = "failed"
            return_code = 2
        elif not collected["selected_complete"]:
            emit("collect", "partial", total_urls=collected["total_urls"])
            summary["status"] = "partial"
            return_code = 3
        else:
            emit("collect", "success", total_urls=collected["total_urls"])
            return_code = 0

        if return_code == 0 and args.run_metadata:
            emit("database", "initializing")
            config = metadata.load_config(args.config)
            db = metadata.connect_db(config)
            try:
                metadata.execute_schema(db, args.schema)
            finally:
                db.close()
            imported = url_importer.import_urls(output, args.config)
            summary["stages"]["import"] = imported
            emit("import", "success", **imported)
            limit = args.metadata_limit or max(1, imported["valid_urls"])
            current_plan = json.loads(plan_path.read_text(encoding="utf-8"))
            request_args = url_collector.build_parser().parse_args(current_plan["batches"][0]["args"])
            emit("metadata", "running", limit=limit, delay_min=request_args.delay_min, delay_max=request_args.delay_max)
            metadata_code = metadata.run(SimpleNamespace(
                config=args.config,
                schema=args.schema,
                init_schema=False,
                limit=limit,
                year=args.metadata_year,
                delay_min=request_args.delay_min,
                delay_max=request_args.delay_max,
                url=[],
            ))
            summary["stages"]["metadata"] = {"exit_code": metadata_code, "limit": limit}
            if metadata_code:
                emit("metadata", "failed", exit_code=metadata_code)
                summary["status"] = "failed"
                return_code = 2
            else:
                emit("metadata", "success")

        emit("excel", "running")
        exported = excel_exporter.export_workbook(output, excel_path, args.config)
        summary["stages"]["excel"] = exported
        emit("excel", "success", **exported)
        summary.setdefault("status", "success" if return_code == 0 else "partial")
        return return_code
    except Exception as exc:
        summary["status"] = "failed"
        summary["error"] = f"{type(exc).__name__}: {exc}"
        emit("pipeline", "failed", error=summary["error"])
        if "excel" not in summary["stages"]:
            try:
                exported = excel_exporter.export_workbook(output, excel_path, args.config)
                summary["stages"]["excel"] = exported
                emit("excel", "success_after_failure", **exported)
            except Exception as export_exc:
                summary["stages"]["excel"] = {"error": f"{type(export_exc).__name__}: {export_exc}"}
        return 2
    finally:
        print("PIPELINE_SUMMARY " + json.dumps(summary, ensure_ascii=False, default=str), flush=True)


def main():
    parser = argparse.ArgumentParser(description="Run a persistent Kickstarter work order")
    parser.add_argument("--plan-file", required=True)
    parser.add_argument("--auto-split", action="store_true")
    parser.add_argument("--safe-pages", type=int, default=180)
    parser.add_argument("--run-metadata", action="store_true")
    parser.add_argument("--metadata-limit", type=int, default=0)
    parser.add_argument("--metadata-year", type=int)
    parser.add_argument("--excel-output")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--schema", default="metadata_schema.sql")
    args = parser.parse_args()
    args.safe_pages = max(1, min(200, args.safe_pages))
    args.metadata_limit = max(0, args.metadata_limit)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
