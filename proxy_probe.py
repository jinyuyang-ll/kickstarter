import json
import socket
import sys
import time

from curl_cffi import requests


PROXY_HOSTS = [
    "http-dynamic.xiaoxiangdaili.com",
    "http-dynamic-S02.xiaoxiangdaili.com",
    "http-dynamic-S03.xiaoxiangdaili.com",
    "http-dynamic-S04.xiaoxiangdaili.com",
]
PROXY_PORT = 10030
TARGET_URL = "https://www.kickstarter.com/projects/uchibacoyapiece/rosalie"
IP_CHECK_URL = "https://api.ipify.org?format=json"
TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def probe_host(host):
    result = {
        "host": host,
        "dns": [],
        "tcp": False,
        "proxy_ip": None,
        "ip_check_status": None,
        "kickstarter_status": None,
        "kickstarter_final_url": None,
        "error": None,
    }

    try:
        result["dns"] = sorted(
            {item[4][0] for item in socket.getaddrinfo(host, PROXY_PORT)}
        )
    except Exception as exc:
        result["error"] = f"DNS: {type(exc).__name__}: {exc}"
        return result

    try:
        with socket.create_connection((host, PROXY_PORT), timeout=TIMEOUT):
            result["tcp"] = True
    except Exception as exc:
        result["error"] = f"TCP: {type(exc).__name__}: {exc}"
        return result

    proxy_url = f"http://{host}:{PROXY_PORT}"
    proxies = {"http": proxy_url, "https": proxy_url}
    session = requests.Session()

    try:
        response = session.get(
            IP_CHECK_URL,
            proxies=proxies,
            timeout=TIMEOUT,
            impersonate="chrome124",
        )
        result["ip_check_status"] = response.status_code
        if response.status_code == 200:
            try:
                result["proxy_ip"] = response.json().get("ip")
            except Exception:
                result["proxy_ip"] = response.text.strip()[:100]
        else:
            result["error"] = f"IP check returned HTTP {response.status_code}"
            return result
    except Exception as exc:
        result["error"] = f"Proxy request: {type(exc).__name__}: {exc}"
        return result

    try:
        response = session.get(
            TARGET_URL,
            headers={"user-agent": USER_AGENT, "accept-language": "en-US,en;q=0.9"},
            proxies=proxies,
            timeout=TIMEOUT,
            impersonate="chrome124",
            allow_redirects=True,
        )
        result["kickstarter_status"] = response.status_code
        result["kickstarter_final_url"] = str(response.url)
        lower_text = (response.text or "")[:20000].lower()
        if any(
            marker in lower_text
            for marker in ("captcha", "verify you are human", "cf-chl-", "安全验证")
        ):
            result["error"] = "Kickstarter security challenge detected"
    except Exception as exc:
        result["error"] = f"Kickstarter: {type(exc).__name__}: {exc}"

    return result


def main():
    results = []
    for index, host in enumerate(PROXY_HOSTS, 1):
        print(f"[{index}/{len(PROXY_HOSTS)}] 探测 {host}:{PROXY_PORT}", flush=True)
        result = probe_host(host)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if index < len(PROXY_HOSTS):
            time.sleep(2)

    working = [
        item
        for item in results
        if item["proxy_ip"] and item["kickstarter_status"] == 200
    ]
    print(
        json.dumps(
            {"summary": {"tested": len(results), "fully_working": len(working)}},
            ensure_ascii=False,
        )
    )
    return 0 if working else 2


if __name__ == "__main__":
    sys.exit(main())
