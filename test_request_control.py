"""Regression cases for G13 classification, cross-run pacing and year filtering."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from email.utils import formatdate

import request_control as control
import url_collector as c
from test_url_collector import args_for, project


class Clock:
    def __init__(self):
        self.now = 1000000.0
        self.waits = []
    def time(self):
        return self.now
    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


def response(status=200, payload=None, text=None, headers=None):
    r = Mock(status_code=status, text=json.dumps(payload) if text is None else text, headers=headers or {})
    r.json.return_value = payload
    return r


class ClassifierTests(unittest.TestCase):
    def test_project_keywords_in_valid_json_are_not_a_challenge(self):
        for phrase in c.CHALLENGE_MARKERS:
            payload = {"projects": [{"name": phrase}], "has_more": False}
            session = Mock()
            session.get.return_value = response(payload=payload)
            self.assertEqual(c.request_page(session, c.BASE_URL, None, 1, 1), payload)

    def test_statuses_and_html_are_distinguished_without_retry(self):
        for status, body, kind in ((403, "denied", "forbidden"), (429, "slow down", "rate_limited"), (200, "<html>verify you are human</html>", "verification_page"), (503, "<html>captcha</html>", "verification_page")):
            session = Mock()
            session.get.return_value = response(status, text=body)
            with self.subTest(status=status), self.assertRaises(c.CollectionError) as caught:
                c.request_page(session, c.BASE_URL, None, 1, 3)
            self.assertEqual(caught.exception.details["kind"], kind)
            self.assertEqual(caught.exception.details["http_status"], status)
            self.assertEqual(session.get.call_count, 1)

    def test_invalid_json_is_not_reported_as_success(self):
        session = Mock()
        session.get.return_value = response(payload={"message": "security check"})
        with self.assertRaises(c.CollectionError) as caught:
            c.request_page(session, c.BASE_URL, None, 1, 1)
        self.assertEqual(caught.exception.details["kind"], "unexpected_response")

    def test_error_details_survive_into_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp)
            with patch("url_collector.request_page", side_effect=c.CollectionError("http_429", kind="rate_limited", http_status=429, retry_after_seconds=120)):
                result = c.collect_urls(args, lambda _: None)
            saved = json.loads(Path(args.output + ".checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["error_details"]["http_status"], 429)
            self.assertEqual(result["error_details"]["retry_after_seconds"], 120)
            self.assertEqual(result["next_page"], 1)


class GateTests(unittest.TestCase):
    def test_new_instance_obeys_previous_request_interval(self):
        clock = Clock()
        with tempfile.TemporaryDirectory() as tmp, patch("request_control.time.time", side_effect=clock.time), patch("request_control.time.sleep", side_effect=clock.sleep):
            path = Path(tmp) / "gate.sqlite3"
            control.RequestGate(30, 30, lambda _: None, path).before_request()
            clock.now += 5
            control.RequestGate(30, 30, lambda _: None, path).before_request()
            self.assertEqual(sum(clock.waits), 25)
            self.assertEqual(clock.now, 1000030)

    def test_elapsed_interval_does_not_wait_twice(self):
        clock = Clock()
        with tempfile.TemporaryDirectory() as tmp, patch("request_control.time.time", side_effect=clock.time), patch("request_control.time.sleep", side_effect=clock.sleep):
            gate = control.RequestGate(30, 30, lambda _: None, Path(tmp) / "gate.sqlite3")
            gate.before_request()
            clock.now += 45
            gate.before_request()
            self.assertEqual(clock.waits, [])

    def test_retry_after_persists_and_blocks_without_sleeping(self):
        clock = Clock()
        with tempfile.TemporaryDirectory() as tmp, patch("request_control.time.time", side_effect=clock.time), patch("request_control.time.sleep", side_effect=clock.sleep):
            path = Path(tmp) / "gate.sqlite3"
            gate = control.RequestGate(30, 30, lambda _: None, path)
            gate.defer(120)
            with self.assertRaises(control.CooldownActive):
                control.RequestGate(30, 30, lambda _: None, path).before_request()
            self.assertEqual(clock.waits, [])
            clock.now += 121
            gate.before_request()

    def test_retry_after_seconds_and_http_date(self):
        self.assertEqual(control.parse_retry_after("120", now=1000), 120)
        self.assertEqual(control.parse_retry_after(formatdate(1120, usegmt=True), now=1000), 120)
        self.assertEqual(control.parse_retry_after(formatdate(900, usegmt=True), now=1000), 0)
        self.assertIsNone(control.parse_retry_after("invalid"))

    def test_two_single_page_runs_really_wait_and_resume(self):
        clock = Clock()
        with tempfile.TemporaryDirectory() as tmp, patch("request_control.time.time", side_effect=clock.time), patch("request_control.time.sleep", side_effect=clock.sleep), patch("request_control.GATE_PATH", Path(tmp) / "gate.sqlite3"):
            args = args_for(tmp, max_pages=1, resume=True, delay_min=30, delay_max=30)
            payloads = [{"projects": [project(i, 2025)], "has_more": True} for i in (1, 2)]
            with patch("url_collector.requests.Session.get", side_effect=[response(payload=p) for p in payloads]) as get:
                first = c.collect_urls(args, lambda _: None)
                second = c.collect_urls(args, lambda _: None)
            self.assertEqual(get.call_count, 2)
            self.assertEqual(first["next_page"], 2)
            self.assertEqual(second["next_page"], 3)
            self.assertEqual(second["total_urls"], 2)
            self.assertEqual(sum(clock.waits), 30)

    def test_rate_limit_prevents_next_run_from_sending_request(self):
        clock = Clock()
        with tempfile.TemporaryDirectory() as tmp, patch("request_control.time.time", side_effect=clock.time), patch("request_control.time.sleep", side_effect=clock.sleep), patch("request_control.GATE_PATH", Path(tmp) / "gate.sqlite3"):
            args = args_for(tmp, max_pages=1, resume=True, delay_min=30, delay_max=30)
            with patch("url_collector.requests.Session.get", return_value=response(429, text="slow down", headers={"retry-after": "120"})) as get:
                first = c.collect_urls(args, lambda _: None)
                second = c.collect_urls(args, lambda _: None)
            self.assertEqual(get.call_count, 1)
            self.assertEqual(first["error_details"]["http_status"], 429)
            self.assertEqual(second["error_details"]["kind"], "retry_after_active")
            self.assertEqual(second["next_page"], 1)


class FilterLogTests(unittest.TestCase):
    def test_2026_projects_are_counted_as_year_exclusions(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, years=list(range(2014, 2026)), max_pages=1)
            projects = [dict(project(i, 2025), launched_at=1767225600) for i in range(12)]
            with patch("url_collector.request_page", return_value={"projects": projects, "has_more": True}):
                result = c.collect_urls(args, lambda _: None)
            self.assertEqual(result["total_urls"], 0)
            self.assertEqual(result["last_page_stats"]["skipped_year"], 12)
            self.assertEqual(result["last_page_stats"]["observed_years"], {"2026": 12})
            self.assertEqual(result["next_page"], 2)

    def test_invalid_missing_year_duplicate_and_remainder_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, max_projects=2)
            missing = dict(project(3, 2025), launched_at=None)
            ps = [{}, missing, project(1, 2025), project(1, 2025), project(2, 2025), project(4, 2025)]
            with patch("url_collector.request_page", return_value={"projects": ps, "has_more": False}):
                result = c.collect_urls(args, lambda _: None)
            stats = result["last_page_stats"]
            self.assertEqual(stats["skipped_invalid_url"], 1)
            self.assertEqual(stats["skipped_missing_year"], 1)
            self.assertEqual(stats["skipped_duplicate"], 1)
            self.assertEqual(stats["remaining"], 1)
            self.assertEqual(stats["accepted"], 2)

    def test_g13_query_identity_still_matches_existing_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, term=None, category_id=12, years=list(range(2014,2026)))
            args.goal_min, args.goal_max = 500, 750
            args.pledged_min, args.pledged_max = 2500, 5000
            self.assertEqual(c.query_signature(args), "9cea05a2f52cc401")


if __name__ == "__main__":
    unittest.main()
