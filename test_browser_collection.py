"""Offline tests for the visible Edge collection mode."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import url_collector as c
import web_app as web


class BrowserModeTests(unittest.TestCase):
    def test_console_plans_default_to_browser_mode(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(web, "ROOT", Path(tmp)):
            plan = web.make_plan({"output": "browser.csv", "states": ["successful"]})
        self.assertEqual(plan["request_mode"], "browser")
        args = c.build_parser().parse_args(plan["batches"][0]["args"])
        self.assertEqual(args.request_mode, "browser")
        with self.assertRaises(ValueError):
            web.make_plan({"request_mode": "invalid"})

    def test_rendered_json_requires_listing_shape(self):
        payload = {"projects": [], "has_more": False, "total_hits": 12}
        self.assertEqual(c.browser_json_payload(json.dumps(payload)), payload)
        for invalid in ("", "<html>Just a moment...</html>", '{"projects":[]}', '{"projects":[],"has_more":"false"}'):
            with self.subTest(invalid=invalid):
                self.assertIsNone(c.browser_json_payload(invalid))

    def test_proxy_translation_keeps_credentials_out_of_server(self):
        proxy = c.browser_proxy("http://user%40mail:p%40ss@proxy.example:8080")
        self.assertEqual(proxy["server"], "http://proxy.example:8080")
        self.assertEqual(proxy["username"], "user@mail")
        self.assertEqual(proxy["password"], "p@ss")

    def test_browser_request_returns_rendered_json_and_emits_safe_diagnostic(self):
        payload = {"projects": [{"id": 1}], "has_more": False}
        session = Mock()
        session._collection_policy = None
        session._diagnostic_sink = Mock()
        session._collection_progress = Mock()
        session._diagnostic_session_id = "browser-test"
        session.proxy_url = None
        session.verification_timeout = 30
        session.page.goto.return_value.status = 200
        session.page.goto.return_value.headers = {"content-type": "application/json"}
        session.page.locator.return_value.inner_text.return_value = json.dumps(payload)
        session.page.url = c.BASE_URL
        session.page.title.return_value = ""
        session.cookie_count.return_value = 2
        result = c.request_browser_page(session, c.BASE_URL, 1)
        self.assertEqual(result, payload)
        record = session._diagnostic_sink.call_args.args[0]
        self.assertEqual(record["kind"], "listing_json")
        self.assertEqual(record["request_mode"], "browser")
        self.assertNotIn("profile_path", record)

    def test_challenge_prompts_once_then_continues_after_user_verification(self):
        payload = {"projects": [], "has_more": False}
        session = Mock()
        session._collection_policy = None
        session._diagnostic_sink = Mock()
        session._collection_progress = Mock()
        session._diagnostic_session_id = "browser-test"
        session.proxy_url = None
        session.verification_timeout = 30
        session.page.goto.return_value.status = 403
        session.page.goto.return_value.headers = {"cf-mitigated": "challenge"}
        session.page.locator.return_value.inner_text.side_effect = [
            "Just a moment... verify you are human",
            json.dumps(payload),
        ]
        session.page.url = c.BASE_URL
        session.page.title.return_value = ""
        session.cookie_count.return_value = 1
        with patch("url_collector.time.sleep"):
            result = c.request_browser_page(session, c.BASE_URL, 1)
        self.assertEqual(result, payload)
        session._collection_progress.assert_called_once()
        self.assertIn("手动完成", session._collection_progress.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
