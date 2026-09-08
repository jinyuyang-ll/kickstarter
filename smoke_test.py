"""对多个真实项目执行低频冒烟测试，并检查核心字段。"""

import argparse
import json
import sys
import time
from pathlib import Path

from project_metadata_spider import collect
from url_importer import normalize_url


REQUIRED_PROJECT_FIELDS = (
    "project_id",
    "project_link",
    "funding_start_date",
    "funding_end_date",
    "goal_amount",
    "pledged_amount",
)
REQUIRED_CREATOR_FIELDS = (
    "id",
    "name",
    "created_project_count",
    "backed_project_count",
    "joined_date",
    "total_backers_across_projects",
    "external_links",
)


def validate(result):
    missing = []
    project = result.get("project") or {}
    creator = result.get("creator") or {}
    for field in REQUIRED_PROJECT_FIELDS:
        if project.get(field) in (None, ""):
            missing.append(f"project.{field}")
    for field in REQUIRED_CREATOR_FIELDS:
        # external_links 允许是空列表，但字段必须存在。
        if field not in creator or creator.get(field) is None:
            missing.append(f"creator.{field}")
    if not isinstance(result.get("collaborators"), list):
        missing.append("collaborators")
    return missing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--urls", default="sample_urls.txt")
    parser.add_argument("--output", default="smoke_test_results.json")
    parser.add_argument("--delay", type=float, default=10)
    args = parser.parse_args()

    urls = []
    for line in Path(args.urls).read_text(encoding="utf-8-sig").splitlines():
        url = normalize_url(line)
        if url and url not in urls:
            urls.append(url)

    results = []
    for index, url in enumerate(urls, 1):
        print(f"[{index}/{len(urls)}] {url}", file=sys.stderr, flush=True)
        try:
            data = collect(url)
            missing = validate(data)
            item = {
                "url": url,
                "success": not missing,
                "missing_required_fields": missing,
                "data": data,
            }
        except Exception as exc:
            item = {"url": url, "success": False, "error": str(exc)}
        results.append(item)
        if index < len(urls):
            time.sleep(max(0, args.delay))

    summary = {
        "total": len(results),
        "passed": sum(1 for item in results if item["success"]),
        "failed": sum(1 for item in results if not item["success"]),
    }
    Path(args.output).write_text(
        json.dumps(
            {"summary": summary, "results": results},
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["failed"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
