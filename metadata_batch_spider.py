"""单线程、低频、可恢复的 Kickstarter 元数据批量采集器。"""

import argparse
import datetime
import json
import random
import sys
import time

import pymysql
from curl_cffi import requests

from project_metadata_spider import build_proxy_url, collect


NORMAL_DELAY_RANGE = (5, 15)
MAX_TASK_ATTEMPTS = 5


def load_config(path):
    with open(path, "r", encoding="utf-8") as source:
        return json.load(source)


def connect_db(config):
    db = config["db_config"]
    return pymysql.connect(
        host=db["host"],
        port=int(db["port"]),
        user=db["user"],
        password=db["password"],
        database=db["database"],
        charset="utf8mb4",
        connect_timeout=15,
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def execute_schema(db, path):
    with open(path, "r", encoding="utf-8") as source:
        statements = [part.strip() for part in source.read().split(";") if part.strip()]
    with db.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
    db.commit()


def reset_stale_tasks(db):
    with db.cursor() as cursor:
        cursor.execute(
            """
            UPDATE metadata_crawl_tasks
            SET crawl_status='retry',
                last_error='recovered_stale_processing',
                next_retry_at=NOW()
            WHERE crawl_status='processing'
              AND last_attempt_at < DATE_SUB(NOW(), INTERVAL 1 HOUR)
            """
        )
    db.commit()


def restore_year_filtered_tasks(db, requested_year):
    """换筛选年份或取消筛选时，恢复之前因年份不匹配而跳过的任务。"""
    with db.cursor() as cursor:
        if requested_year is None:
            cursor.execute(
                """
                UPDATE metadata_crawl_tasks
                SET crawl_status='pending', last_error=NULL,
                    next_retry_at=NULL
                WHERE crawl_status='filtered_year'
                """
            )
        else:
            same_filter_prefix = f"filtered_year:requested={requested_year};%"
            cursor.execute(
                """
                UPDATE metadata_crawl_tasks
                SET crawl_status='pending', last_error=NULL,
                    next_retry_at=NULL
                WHERE crawl_status='filtered_year'
                  AND (last_error IS NULL OR last_error NOT LIKE %s)
                """,
                (same_filter_prefix,),
            )
    db.commit()


def seed_tasks(db, urls):
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM information_schema.tables
            WHERE table_schema=DATABASE() AND table_name='crawling_url'
            """
        )
        if cursor.fetchone()["count"]:
            cursor.execute(
                """
                INSERT IGNORE INTO metadata_crawl_tasks (source_pid, project_url)
                SELECT pid, SUBSTRING_INDEX(project_url, '?', 1)
                FROM crawling_url
                WHERE project_url IS NOT NULL
                  AND project_url LIKE 'https://www.kickstarter.com/projects/%'
                """
            )
        if urls:
            cursor.executemany(
                """
                INSERT IGNORE INTO metadata_crawl_tasks (project_url)
                VALUES (%s)
                """,
                [(url.split("?", 1)[0],) for url in urls],
            )
    db.commit()


def claim_task(db):
    with db.cursor() as cursor:
        cursor.execute(
            """
            SELECT task_id, source_pid, project_url, attempt_count
            FROM metadata_crawl_tasks
            WHERE crawl_status IN ('pending', 'retry')
              AND attempt_count < %s
              AND (next_retry_at IS NULL OR next_retry_at <= NOW())
            ORDER BY task_id
            LIMIT 1
            FOR UPDATE
            """,
            (MAX_TASK_ATTEMPTS,),
        )
        task = cursor.fetchone()
        if not task:
            db.rollback()
            return None
        cursor.execute(
            """
            UPDATE metadata_crawl_tasks
            SET crawl_status='processing',
                attempt_count=attempt_count+1,
                last_attempt_at=NOW(),
                last_error=NULL
            WHERE task_id=%s
            """,
            (task["task_id"],),
        )
    db.commit()
    task["attempt_count"] += 1
    return task


def choose_proxy(config):
    proxy = config.get("proxy_config") or {}
    if not proxy.get("enable_proxy"):
        return None
    hosts = proxy.get("proxy_host_list") or []
    if not hosts:
        raise RuntimeError("proxy_enabled_but_no_host")
    return build_proxy_url(
        random.choice(hosts),
        proxy.get("proxy_port", 10030),
        proxy.get("proxy_username") or "",
        proxy.get("proxy_pwd") or "",
    )


def json_text(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def save_result(db, task, result):
    project = result["project"]
    creator = result.get("creator")
    collaborators = result.get("collaborators") or []
    project_id = project["project_id"]

    with db.cursor() as cursor:
        if creator:
            cursor.execute(
                """
                INSERT INTO creator_metadata (
                    creator_id, creator_name, profile_url, joined_date,
                    created_project_count, backed_project_count,
                    total_backers_across_projects, location, biography,
                    external_links, verified_identity, raw_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    creator_name=VALUES(creator_name),
                    profile_url=VALUES(profile_url),
                    joined_date=VALUES(joined_date),
                    created_project_count=VALUES(created_project_count),
                    backed_project_count=VALUES(backed_project_count),
                    total_backers_across_projects=VALUES(total_backers_across_projects),
                    location=VALUES(location),
                    biography=VALUES(biography),
                    external_links=VALUES(external_links),
                    verified_identity=VALUES(verified_identity),
                    raw_json=VALUES(raw_json)
                """,
                (
                    creator["id"], creator["name"], creator["profile_url"],
                    creator["joined_date"], creator["created_project_count"],
                    creator["backed_project_count"],
                    creator["total_backers_across_projects"],
                    creator["location"], creator["biography"],
                    json_text(creator["external_links"]),
                    int(bool(creator.get("verified_identity"))),
                    json_text(creator),
                ),
            )

        cursor.execute(
            """
            INSERT INTO project_metadata (
                project_id, source_pid, project_link, title, currency,
                goal_amount, pledged_amount, funding_start_date,
                funding_end_date, backers_count, project_status,
                creator_id, raw_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                source_pid=VALUES(source_pid),
                project_link=VALUES(project_link),
                title=VALUES(title),
                currency=VALUES(currency),
                goal_amount=VALUES(goal_amount),
                pledged_amount=VALUES(pledged_amount),
                funding_start_date=VALUES(funding_start_date),
                funding_end_date=VALUES(funding_end_date),
                backers_count=VALUES(backers_count),
                project_status=VALUES(project_status),
                creator_id=VALUES(creator_id),
                raw_json=VALUES(raw_json)
            """,
            (
                project_id, task.get("source_pid"), project["project_link"],
                project["title"], project["currency"], project["goal_amount"],
                project["pledged_amount"], project["funding_start_date"],
                project["funding_end_date"], project["backers_count"],
                project["status"], creator["id"] if creator else None,
                json_text(result),
            ),
        )

        for collaborator in collaborators:
            cursor.execute(
                """
                INSERT INTO collaborator_metadata (
                    collaborator_id, collaborator_name, profile_url, joined_date,
                    created_project_count, backed_project_count,
                    total_backers_across_projects, location, biography,
                    external_links, raw_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    collaborator_name=VALUES(collaborator_name),
                    profile_url=VALUES(profile_url),
                    joined_date=VALUES(joined_date),
                    created_project_count=VALUES(created_project_count),
                    backed_project_count=VALUES(backed_project_count),
                    total_backers_across_projects=VALUES(total_backers_across_projects),
                    location=VALUES(location),
                    biography=VALUES(biography),
                    external_links=VALUES(external_links),
                    raw_json=VALUES(raw_json)
                """,
                (
                    collaborator["id"], collaborator["name"],
                    collaborator["profile_url"], collaborator["joined_date"],
                    collaborator["created_project_count"],
                    collaborator["backed_project_count"],
                    collaborator["total_backers_across_projects"],
                    collaborator["location"], collaborator["biography"],
                    json_text(collaborator["external_links"]),
                    json_text(collaborator),
                ),
            )
            cursor.execute(
                """
                INSERT INTO project_collaborator (
                    project_id, collaborator_id, collaborator_role,
                    collaborator_link
                ) VALUES (%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    collaborator_role=VALUES(collaborator_role),
                    collaborator_link=VALUES(collaborator_link)
                """,
                (
                    project_id, collaborator["id"], collaborator.get("role"),
                    collaborator["profile_url"],
                ),
            )

        cursor.execute(
            """
            UPDATE metadata_crawl_tasks
            SET crawl_status='success', last_status_code=200,
                last_error=NULL, next_retry_at=NULL
            WHERE task_id=%s
            """,
            (task["task_id"],),
        )
    db.commit()


def mark_filtered(db, task, requested_year, actual_year):
    with db.cursor() as cursor:
        cursor.execute(
            """
            UPDATE metadata_crawl_tasks
            SET crawl_status='filtered_year', last_status_code=200,
                last_error=%s, next_retry_at=NULL
            WHERE task_id=%s
            """,
            (
                f"filtered_year:requested={requested_year};actual={actual_year}",
                task["task_id"],
            ),
        )
    db.commit()


def mark_failure(db, task, error):
    text = str(error)[:1000]
    if "http_404" in text:
        status = "not_found"
        status_code = 404
        next_retry = None
    elif task["attempt_count"] >= MAX_TASK_ATTEMPTS:
        status = "blocked"
        status_code = 403 if "security_challenge" in text else None
        next_retry = None
    else:
        status = "retry"
        status_code = 403 if "security_challenge" in text else None
        minutes = min(24 * 60, 15 * (2 ** (task["attempt_count"] - 1)))
        next_retry = datetime.datetime.now() + datetime.timedelta(minutes=minutes)

    with db.cursor() as cursor:
        cursor.execute(
            """
            UPDATE metadata_crawl_tasks
            SET crawl_status=%s, last_status_code=%s, last_error=%s,
                next_retry_at=%s
            WHERE task_id=%s
            """,
            (status, status_code, text, next_retry, task["task_id"]),
        )
    db.commit()
    return status, next_retry


def run(args):
    config = load_config(args.config)
    try:
        db = connect_db(config)
    except Exception as exc:
        print(f"数据库连接失败: {exc}", file=sys.stderr)
        return 3

    shared_session = None
    try:
        if args.init_schema:
            execute_schema(db, args.schema)
            print("数据库结构初始化完成", file=sys.stderr)
        seed_tasks(db, args.url)
        reset_stale_tasks(db)
        restore_year_filtered_tasks(db, args.year)

        processed = 0
        succeeded = 0
        filtered = 0
        failed = 0
        shared_session = requests.Session()
        while processed < args.limit:
            task = claim_task(db)
            if not task:
                print("当前没有到期的待处理任务", file=sys.stderr)
                break
            processed += 1
            print(
                f"[{processed}/{args.limit}] task={task['task_id']} "
                f"attempt={task['attempt_count']} {task['project_url']}",
                file=sys.stderr,
            )
            try:
                proxy_url = choose_proxy(config)
                result = collect(
                    task["project_url"],
                    proxy_url=proxy_url,
                    required_year=args.year,
                    session=shared_session,
                )
                if result.get("filtered_year"):
                    actual_year = result.get("actual_year")
                    mark_filtered(db, task, args.year, actual_year)
                    filtered += 1
                    print(f"年份不匹配，已跳过: {actual_year}", file=sys.stderr)
                else:
                    save_result(db, task, result)
                    succeeded += 1
                    print(
                        f"写入成功: project_id={result['project']['project_id']}",
                        file=sys.stderr,
                    )
            except Exception as exc:
                db.rollback()
                status, retry_at = mark_failure(db, task, exc)
                failed += 1
                print(
                    f"任务失败: status={status} retry_at={retry_at} error={exc}",
                    file=sys.stderr,
                )
                if "security_challenge" in str(exc):
                    print("检测到验证，停止本轮后续元数据任务", file=sys.stderr)
                    break

            if processed < args.limit:
                delay = random.uniform(args.delay_min, args.delay_max)
                print(f"等待 {delay:.1f} 秒", file=sys.stderr)
                time.sleep(delay)

        print(
            json.dumps(
                {
                    "processed": processed,
                    "succeeded": succeeded,
                    "filtered": filtered,
                    "failed": failed,
                },
                ensure_ascii=False,
            )
        )
        return 2 if failed else 0
    finally:
        if shared_session is not None:
            shared_session.close()
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Kickstarter 元数据批量采集")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--schema", default="metadata_schema.sql")
    parser.add_argument("--init-schema", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--year", type=int, help="只入库指定开始年份的项目")
    parser.add_argument("--delay-min", type=float, default=NORMAL_DELAY_RANGE[0])
    parser.add_argument("--delay-max", type=float, default=NORMAL_DELAY_RANGE[1])
    parser.add_argument(
        "--url", action="append", default=[], help="直接加入一个项目 URL，可重复"
    )
    args = parser.parse_args()
    args.limit = max(1, args.limit)
    args.delay_min = max(0, args.delay_min)
    args.delay_max = max(args.delay_min, args.delay_max)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
