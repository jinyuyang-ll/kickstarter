"""Small, redacted request records. Never store response bodies or cookie headers."""
import datetime as dt
import html
import os
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

SAFE_QUERY = {"page", "sort", "category_id", "category_id[]", "state", "state[]", "woe_id", "goal", "goal[]", "pledged", "pledged[]", "goal_min", "goal_max", "pledged_min", "pledged_max", "raised_min", "raised_max"}
SAFE_HEADERS = ("server", "via", "cf-ray", "cf-mitigated", "x-request-id", "x-correlation-id", "retry-after")
ERROR_PHRASES = ("access denied", "request blocked", "forbidden", "too many requests", "verify you are human", "enable javascript", "enable cookies", "just a moment", "security check", "captcha", "proxy authentication required")


def timestamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def redact(text, secrets=(), limit=400, opaque=True):
    if not isinstance(text, str):
        return ""
    text = html.unescape(text)
    for secret in sorted(set(x for x in secrets if isinstance(x, str) and x), key=len, reverse=True):
        text = text.replace(secret, "[redacted]")
    text = re.sub(r"https?://[^\s<>]+", "[url]", text, flags=re.I)
    text = re.sub(r"(?i)(?:authorization|cookie|password|token|secret|api[_-]?key)\s*[:=]\s*[^\s<;]+", "[redacted]", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", text)
    text = re.sub(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", "[ip]", text)
    text = re.sub(r"(?i)(?<![\w:])(?:[0-9a-f]{0,4}:){2,}[0-9a-f:]{0,20}(?![\w:])", "[ip]", text)
    if opaque:
        text = re.sub(r"[A-Za-z0-9_+/=-]{24,}", "[opaque]", text)
    return " ".join(text.split())[:limit]


def safe_url(value):
    if not isinstance(value, str):
        return ""
    parsed = urlparse(value)
    host = parsed.hostname or ""
    if host not in ("kickstarter.com", "www.kickstarter.com"):
        return parsed.scheme + "://[other-host]"
    pairs = [(k, v if k in SAFE_QUERY and re.fullmatch(r"[A-Za-z0-9_.+-]{0,80}", v) else "[redacted]") for k, v in parse_qsl(parsed.query)]
    path = parsed.path if parsed.path.startswith("/discover") else "/[other-path]"
    return urlunparse((parsed.scheme, host, path, "", urlencode(pairs), ""))


def configuration_secrets(config):
    found = []
    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if any(word in key.lower() for word in ("password", "pwd", "username", "token", "secret")) and isinstance(item, str) and item:
                    found.append(item)
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(config)
    return found


def cookie_secrets(session):
    try:
        return [cookie.value for cookie in session.cookies.jar]
    except (AttributeError, TypeError):
        return []


def response_details(response, secrets=()):
    headers = getattr(response, "headers", {})
    selected = {}
    for key in SAFE_HEADERS:
        value = headers.get(key)
        if isinstance(value, str):
            selected[key] = redact(value, secrets, limit=150, opaque=key not in ("cf-ray", "x-request-id", "x-correlation-id"))
    body = response.text if isinstance(response.text, str) else ""
    match = re.search(r"<title\b[^>]*>(.*?)</title>", body[:100000], flags=re.I | re.S)
    title = re.sub(r"<[^>]+>", " ", match.group(1)) if match else ""
    # Only known diagnostic phrases are retained from body text, never arbitrary excerpts.
    visible = re.sub(r"<(script|style|form|noscript)\b[^>]*>.*?</\1>", " ", body[:100000], flags=re.I | re.S)
    visible = html.unescape(re.sub(r"<[^>]+>", " ", visible)).lower()
    return {"response_headers": selected, "error_title": redact(title, secrets, 180), "error_hints": [phrase for phrase in ERROR_PHRASES if phrase in visible]}


def network_context(proxy_url):
    env_names = sorted(name for name in os.environ if name.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy"))
    return {"configured_proxy": bool(proxy_url), "proxy_environment_variables": env_names, "vpn_or_system_route": "not_detected"}
