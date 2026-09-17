"""低频采集 Kickstarter 项目、创作者和协作者元数据。

单个项目正常只发起两次 HTTP 请求：
1. 项目主页：项目 ID、金额、时间等；
2. GraphQL：创作者和项目协作者资料。
"""

import argparse
import base64
import datetime
import html
import json
import random
import re
import sys
import time
from urllib.parse import urlparse
from urllib.parse import quote

from curl_cffi import requests
from lxml import etree


IMPERSONATE = "chrome124"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
TIMEOUT = 30
MAX_RETRIES = 3
BASE_DELAY = 5
CHALLENGE_DELAY = 30

CREATOR_QUERY = """
query CreatorAndCollaborators($slug: String!) {
  project(slug: $slug) {
    id
    verifiedIdentity
    creator {
      id
      name
      url
      joinedOn
      biography
      totalBackersAcrossProjects
      backingsCount
      location { displayableName }
      launchedProjects { totalCount }
      websites { url domain }
    }
    collaborators {
      edges {
        title
        node {
          id
          name
          url
          biography
          backingsCount
          totalBackersAcrossProjects
          joinedOn
          location { displayableName }
          launchedProjects { totalCount }
          websites { url domain }
        }
      }
    }
  }
}
"""


def request_with_retry(session, method, url, **kwargs):
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"{method.upper()} [{attempt}/{MAX_RETRIES}] {url}", file=sys.stderr)
            response = session.request(
                method,
                url,
                timeout=TIMEOUT,
                impersonate=IMPERSONATE,
                **kwargs,
            )
            response.encoding = "utf-8"
            text = (response.text or "")[:20000].lower()
            challenged = response.status_code in (403, 429) or any(
                marker in text
                for marker in (
                    "captcha",
                    "verify you are human",
                    "cf-chl-",
                    "security check",
                    "人机验证",
                    "安全验证",
                )
            )
            print(f"HTTP {response.status_code} -> {response.url}", file=sys.stderr)
            if response.status_code == 200 and not challenged:
                return response
            last_error = (
                "security_challenge" if challenged else f"http_{response.status_code}"
            )
            if challenged:
                raise RuntimeError(last_error)
        except RuntimeError:
            raise
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        if attempt < MAX_RETRIES:
            delay_base = (
                CHALLENGE_DELAY * attempt
                if last_error == "security_challenge"
                else BASE_DELAY * (2 ** (attempt - 1))
            )
            delay = delay_base + random.uniform(0, 3)
            print(f"失败({last_error})，{delay:.1f} 秒后重试", file=sys.stderr)
            time.sleep(delay)
    raise RuntimeError(last_error)


def decode_global_id(value):
    if not value:
        return None
    try:
        decoded = base64.b64decode(value).decode("utf-8")
        return decoded.split("-", 1)[-1]
    except Exception:
        return value


def date_from_timestamp(value):
    if value is None:
        return None
    return datetime.datetime.fromtimestamp(
        value, tz=datetime.timezone.utc
    ).date().isoformat()


def project_slug(project_url):
    path = urlparse(project_url).path.strip("/").split("/")
    if len(path) < 3 or path[0] != "projects":
        raise ValueError(f"不是有效的 Kickstarter 项目链接: {project_url}")
    return "/".join(path[1:3])


def extract_current_project(page_text):
    match = re.search(r"window\.current_project\s*=\s*(.+?);\s*\n", page_text, re.S)
    if not match:
        raise RuntimeError("project_data_not_found")
    encoded = json.loads(match.group(1))
    return json.loads(html.unescape(encoded))


def normalize_websites(items):
    return [
        {"domain": item.get("domain"), "url": item.get("url")}
        for item in (items or [])
        if item and item.get("url")
    ]


def normalize_person(node):
    if not node:
        return None
    launched = node.get("launchedProjects") or {}
    return {
        "id": decode_global_id(node.get("id")),
        "name": node.get("name"),
        "profile_url": node.get("url"),
        "joined_date": (node.get("joinedOn") or "").split("T", 1)[0] or None,
        "created_project_count": launched.get("totalCount", 0),
        "backed_project_count": node.get("backingsCount", 0),
        "total_backers_across_projects": node.get(
            "totalBackersAcrossProjects", 0
        ),
        "location": (node.get("location") or {}).get("displayableName"),
        "biography": node.get("biography"),
        "external_links": normalize_websites(node.get("websites")),
    }


def build_proxy_url(host, port, username="", password=""):
    if not host:
        return None
    if username or password:
        auth = f"{quote(username)}:{quote(password)}@"
    else:
        auth = ""
    return f"http://{auth}{host}:{int(port)}"


def normalize_project(project, page_url):
    return {
        "project_id": project.get("id"),
        "project_link": str(page_url).split("?", 1)[0],
        "title": project.get("name"),
        "currency": project.get("currency"),
        "goal_amount": project.get("goal"),
        "pledged_amount": project.get("pledged"),
        "funding_start_date": date_from_timestamp(project.get("launched_at")),
        "funding_end_date": date_from_timestamp(project.get("deadline")),
        "backers_count": project.get("backers_count"),
        "status": project.get("state"),
    }


def collect(project_url, proxy_url=None, required_year=None, session=None):
    session = session or requests.Session()
    proxies = (
        {"http": proxy_url, "https": proxy_url}
        if proxy_url
        else None
    )
    headers = {
        "user-agent": USER_AGENT,
        "accept-language": "en-US,en;q=0.9",
        "accept": "text/html,application/xhtml+xml",
    }
    page = request_with_retry(
        session, "get", project_url, headers=headers, proxies=proxies
    )
    project = extract_current_project(page.text)
    normalized_project = normalize_project(project, page.url)
    start_date = normalized_project.get("funding_start_date")
    actual_year = int(start_date[:4]) if start_date else None
    if required_year is not None and actual_year != required_year:
        return {
            "project": normalized_project,
            "creator": None,
            "collaborators": [],
            "request_count": 1,
            "filtered_year": True,
            "requested_year": required_year,
            "actual_year": actual_year,
        }

    tree = etree.HTML(page.text)
    csrf_nodes = tree.xpath('//meta[@name="csrf-token"]/@content')
    csrf_token = csrf_nodes[0] if csrf_nodes else ""
    graph_headers = {
        "user-agent": USER_AGENT,
        "accept": "application/json",
        "content-type": "application/json",
        "referer": str(page.url),
    }
    if csrf_token:
        graph_headers["x-csrf-token"] = csrf_token

    payload = [
        {
            "operationName": "CreatorAndCollaborators",
            "variables": {"slug": project_slug(str(page.url))},
            "query": CREATOR_QUERY,
        }
    ]
    graph = request_with_retry(
        session,
        "post",
        "https://www.kickstarter.com/graph",
        headers=graph_headers,
        json=payload,
        proxies=proxies,
    )
    graph_json = graph.json()
    if not isinstance(graph_json, list) or not graph_json:
        raise RuntimeError(f"unexpected_graphql_response: {graph_json}")
    if graph_json[0].get("errors"):
        raise RuntimeError(
            "graphql_errors: " + json.dumps(graph_json[0]["errors"], ensure_ascii=False)
        )
    graph_project = (graph_json[0].get("data") or {}).get("project") or {}

    collaborators = []
    edges = ((graph_project.get("collaborators") or {}).get("edges") or [])
    for edge in edges:
        person = normalize_person(edge.get("node"))
        if person:
            person["role"] = edge.get("title")
            collaborators.append(person)

    creator = normalize_person(graph_project.get("creator"))
    if creator:
        creator["verified_identity"] = bool(graph_project.get("verifiedIdentity"))

    return {
        "project": normalized_project,
        "creator": creator,
        "collaborators": collaborators,
        "request_count": 2,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--output", help="保存 JSON；默认输出到终端")
    parser.add_argument("--proxy", help="可选代理，例如 http://user:pass@host:10030")
    args = parser.parse_args()
    try:
        result = collect(args.url, proxy_url=args.proxy)
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        return 2

    text = json.dumps(
        {"success": True, **result}, ensure_ascii=False, indent=2, default=str
    )
    if args.output:
        with open(args.output, "w", encoding="utf-8") as output:
            output.write(text)
            output.write("\n")
        print(f"已保存: {args.output}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
