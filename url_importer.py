"""把 TXT/CSV/JSON 中的 Kickstarter 项目链接去重导入任务表。"""

import argparse
import csv
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from metadata_batch_spider import connect_db, load_config


def normalize_url(value):
    value = (value or "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    parts = parsed.path.strip("/").split("/")
    if (
        parsed.scheme not in ("http", "https")
        or parsed.netloc.lower() not in ("kickstarter.com", "www.kickstarter.com")
        or len(parts) < 3
        or parts[0] != "projects"
    ):
        return None
    return f"https://www.kickstarter.com/projects/{parts[1]}/{parts[2]}"


def extract_urls(path):
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("urls") or data.get("projects") or []
        for item in data:
            if isinstance(item, str):
                yield item
            elif isinstance(item, dict):
                yield (
                    item.get("project_url")
                    or item.get("url")
                    or item.get("project_link")
                )
        return

    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if not reader.fieldnames:
                return
            candidates = ("project_url", "url", "project_link", "link")
            column = next((name for name in candidates if name in reader.fieldnames), None)
            if column is None:
                raise ValueError(
                    "CSV 需要包含 project_url、url、project_link 或 link 列"
                )
            for row in reader:
                yield row.get(column)
        return

    for line in path.read_text(encoding="utf-8-sig").splitlines():
        yield line


def import_urls(path, config_path="config.json", dry_run=False):
    path = Path(path)
    unique_urls = sorted(
        {url for value in extract_urls(path) if (url := normalize_url(value))}
    )
    result = {"valid_urls": len(unique_urls), "inserted": 0, "existing": 0}
    if dry_run or not unique_urls:
        return result
    db = connect_db(load_config(config_path))
    try:
        with db.cursor() as cursor:
            affected = cursor.executemany(
                """
                INSERT IGNORE INTO metadata_crawl_tasks (project_url)
                VALUES (%s)
                """,
                [(url,) for url in unique_urls],
            )
        db.commit()
        result.update(inserted=affected, existing=len(unique_urls) - affected)
        return result
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="导入 Kickstarter 项目 URL")
    parser.add_argument("file")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    path = Path(args.file)
    if args.dry_run:
        values = sorted({url for value in extract_urls(path) if (url := normalize_url(value))})
        print(f"有效且去重后的 URL: {len(values)}")
        for url in values:
            print(url)
        return 0
    try:
        result = import_urls(path, args.config)
    except Exception as exc:
        print(f"数据库连接或导入失败: {exc}", file=sys.stderr)
        return 3
    print(f"有效且去重后的 URL: {result['valid_urls']}")
    print(f"新增任务: {result['inserted']}；已存在或忽略: {result['existing']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
