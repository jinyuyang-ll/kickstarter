"""Offline regression tests. No external requests or database writes."""
import argparse
import csv
import json
import tempfile
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from urllib.parse import parse_qs, urlparse

import url_collector as c
import web_app as web
from test_url_collector import args_for, project


class ResumeTests(unittest.TestCase):
    def run_collection(self, args, payload):
        with patch("url_collector.request_page", return_value=payload), patch("url_collector.time.sleep"):
            return c.collect_urls(args, lambda _: None)

    def test_mid_page_resume_keeps_actual_remaining_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, max_projects=1, resume=True)
            payload = {"projects": [project(i, 2025) for i in (1, 2, 3)], "has_more": False}
            first = self.run_collection(args, payload)
            self.assertEqual(first["next_page"], 1)
            self.assertFalse(first["complete"])
            with patch("url_collector.request_page", side_effect=AssertionError("must use cached remainder")):
                second = c.collect_urls(args, lambda _: None)
                third = c.collect_urls(args, lambda _: None)
            self.assertEqual(second["total_urls"], 2)
            self.assertTrue(third["complete"])
            self.assertEqual(third["total_urls"], 3)
            self.assertEqual(third["next_page"], 2)

    def test_completed_checkpoint_does_not_request_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, resume=True)
            self.run_collection(args, {"projects": [project(1, 2025)], "has_more": False})
            with patch("url_collector.request_page") as request:
                result = c.collect_urls(args, lambda _: None)
            request.assert_not_called()
            self.assertTrue(result["complete"])

    def test_year_change_rejects_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, resume=True)
            self.run_collection(args, {"projects": [], "has_more": False})
            args.years = [2024]
            with self.assertRaisesRegex(c.CollectionError, "checkpoint_query_mismatch"):
                c.collect_urls(args)

    def test_deleted_csv_does_not_silently_skip_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, resume=True)
            self.run_collection(args, {"projects": [project(1, 2025)], "has_more": False})
            Path(args.output).unlink()
            with self.assertRaisesRegex(c.CollectionError, "checkpoint_output_missing"):
                c.collect_urls(args)

    def test_404_after_success_preserves_progress_and_marks_suspected_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, resume=True)
            c.write_json_atomic(Path(args.output + ".checkpoint.json"), {"query_signature": c.query_signature(args), "next_page": 200})
            with patch("url_collector.request_page", side_effect=[{"projects": [project(1, 2025)], "has_more": True}, c.CollectionError("http_404")]), patch("url_collector.time.sleep"):
                result = c.collect_urls(args, lambda _: None)
            self.assertEqual(result["stop_reason"], "suspected_pagination_limit")
            self.assertEqual(result["next_page"], 201)
            self.assertEqual(len(c.load_existing(Path(args.output))), 1)
            self.assertFalse(result["complete"])

    def test_first_page_404_is_not_claimed_to_be_pagination_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("url_collector.request_page", side_effect=c.CollectionError("http_404")):
                result = c.collect_urls(args_for(tmp), lambda _: None)
            self.assertEqual(result["stop_reason"], "request_failed")

    def test_bad_payload_never_marks_complete(self):
        for payload in ({}, {"projects": [], "has_more": True}, {"projects": [], "has_more": "false"}):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as tmp:
                result = self.run_collection(args_for(tmp), payload)
                self.assertEqual(result["stop_reason"], "request_failed")
                self.assertFalse(result["complete"])

    def test_effective_url_sort_controls_year_early_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, sort=None, discover_url=c.BASE_URL + "?sort=most_funded", max_pages=3)
            result = self.run_collection(args, {"projects": [project(1, 2024)], "has_more": True})
            self.assertEqual(result["pages_processed"], 3)
            self.assertEqual(result["stop_reason"], "max_pages")

    def test_last_item_limit_advances_page_but_not_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, max_projects=1)
            result = self.run_collection(args, {"projects": [project(1, 2025)], "has_more": True})
            self.assertEqual(result["next_page"], 2)
            self.assertEqual(result["stop_reason"], "max_projects")


class FilterTests(unittest.TestCase):
    def query(self, **data):
        args = c.build_parser().parse_args(web.collect_args(data))
        return parse_qs(urlparse(c.build_query_url(args, 1)).query)

    def test_controls_override_pasted_url(self):
        q = self.query(discover_url=c.BASE_URL + "?category_id=12&state=live&sort=magic&goal=2&woe_id=99", category_id=34, states=["failed"], sort="newest", goal_min="1000", goal_max="5000", woe_id=23424977)
        self.assertEqual(q["category_id"], ["34"])
        self.assertEqual(q["state[]"], ["failed"])
        self.assertNotIn("state", q)
        self.assertNotIn("goal", q)
        self.assertEqual(q["woe_id"], ["23424977"])
        self.assertEqual(q["goal_max"], ["5000"])

    def test_explicit_blank_clears_url_filters(self):
        q = self.query(discover_url=c.BASE_URL + "?category_id=34&state=live&goal_min=10&woe_id=99&term=old", category_id="", states=[], goal_min="", goal_max="", woe_id=0, term="")
        for key in ("category_id", "state", "state[]", "goal_min", "woe_id", "term"):
            self.assertNotIn(key, q)

    def test_unspecified_control_inherits_link(self):
        q = self.query(discover_url=c.BASE_URL + "?category_id=34&sort=magic&goal_min=0")
        self.assertEqual(q["category_id"], ["34"])
        self.assertEqual(q["sort"], ["magic"])
        self.assertEqual(q["goal_min"], ["0"])

    def test_zero_open_ended_and_percent_values(self):
        q = self.query(goal_min="0", goal_max="", raised_min="100", raised_max="500")
        self.assertEqual(q["goal_min"], ["0"])
        self.assertNotIn("goal_max", q)
        self.assertEqual(q["raised_min"], ["100"])

    def test_invalid_ranges_rejected(self):
        for fields in ({"goal_min": "-1"}, {"goal_min": "nan"}, {"raised_max": "inf"}, {"pledged_min": "10", "pledged_max": "5"}, {"goal_min": "5", "goal_max": "5"}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.query(**fields)

    def test_year_is_not_sent_to_server(self):
        self.assertNotIn("year", self.query(years=[2020]))

    def test_page_and_quantity_limits_do_not_change_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(c.query_signature(args_for(tmp, max_pages=1)), c.query_signature(args_for(tmp, max_pages=200, max_projects=10)))


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(web, "ROOT", self.root)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.temp.cleanup()

    def plan(self, **kwargs):
        return web.make_plan({"output": "merged.csv", "max_pages": 1, "max_projects": 0, "request_mode": "http", **kwargs})

    def test_states_split_and_duplicate_groups_deduped(self):
        group = {"category_id": 34, "states": ["successful", "failed"]}
        plan = self.plan(groups=[group, group])
        self.assertEqual(len(plan["batches"]), 2)
        for item in plan["batches"]:
            self.assertEqual(len(parse_qs(urlparse(item["url"]).query)["state[]"]), 1)

    def test_multiple_ranges_and_states_create_independent_identities(self):
        plan = self.plan(groups=[{"states": ["failed", "successful"], "goal_min": 0, "goal_max": 1000}, {"states": ["failed", "successful"], "goal_min": 1000, "goal_max": ""}])
        self.assertEqual(len({b["id"] for b in plan["batches"]}), 4)

    def test_merge_dedupes_and_resume_skips_complete_batches(self):
        plan = self.plan(groups=[{"states": ["successful"]}, {"states": ["failed"]}])
        path = self.root / "plan.json"
        c.write_json_atomic(path, plan)
        pages = [{"projects": [project(1, 2025), project(2, 2025)], "has_more": False}, {"projects": [project(2, 2025), project(3, 2025)], "has_more": False}]
        with patch("url_collector.request_page", side_effect=pages), patch("url_collector.time.sleep"):
            summary = c.collect_plan(path, lambda _: None)
        self.assertTrue(summary["complete"])
        self.assertEqual(summary["total_urls"], 3)
        self.assertEqual(len(list((self.root / "merged.batches").glob("*.checkpoint.json"))), 2)
        with patch("url_collector.request_page") as request, patch("url_collector.time.sleep"):
            c.collect_plan(path, lambda _: None)
        request.assert_not_called()

    def test_security_failure_stops_remaining_batches(self):
        plan = self.plan(groups=[{"states": ["successful", "failed"]}])
        path = self.root / "plan.json"
        c.write_json_atomic(path, plan)
        with patch("url_collector.request_page", side_effect=c.CollectionError("security_challenge")) as request, patch("url_collector.time.sleep"):
            result = c.collect_plan(path, lambda _: None)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(result["batches"][1]["stop_reason"], "not_run")
        self.assertFalse(result["complete"])
        self.assertTrue(result["failed"])

    def test_existing_unmanaged_csv_is_not_overwritten(self):
        (self.root / "merged.csv").write_text("important data")
        with self.assertRaises(ValueError):
            self.plan(states=["failed"])
        self.assertEqual((self.root / "merged.csv").read_text(), "important data")

    def test_paths_outside_workspace_rejected(self):
        with self.assertRaises(ValueError):
            self.plan(output=str(self.root.parent / "outside.csv"))

    def test_concurrent_collections_rejected(self):
        with patch.dict(web.JOBS, {"existing": {"kind": "collect", "status": "queued"}}, clear=True):
            with self.assertRaises(ValueError):
                web.start_job("collect", [])

    def test_child_start_failure_releases_job(self):
        with patch.dict(web.JOBS, {"x": {"kind": "collect", "status": "queued", "log": []}}, clear=True), patch("web_app.subprocess.Popen", side_effect=OSError("no executable")):
            web.run_job("x", ["missing"])
            self.assertEqual(web.JOBS["x"]["status"], "failed")


class RequestTests(unittest.TestCase):
    def test_404_is_not_retried(self):
        session = Mock()
        session.get.return_value = Mock(status_code=404, text="missing")
        with self.assertRaisesRegex(c.CollectionError, "http_404"):
            c.request_page(session, c.BASE_URL, None, 1, 3)
        self.assertEqual(session.get.call_count, 1)

    def test_location_ids_are_decoded(self):
        context = MagicMock()
        session = context.__enter__.return_value
        session.get.return_value = Mock(status_code=200, text='<meta name="csrf-token" content="test-token">')
        session.post.return_value = Mock(status_code=200)
        session.post.return_value.json.return_value = {"data": {"locations": {"edges": [{"node": {"id": "TG9jYXRpb24tMjM0MjQ5Nzc=", "displayableName": "United States"}}]}}}
        with patch("url_collector.requests.Session", return_value=context), patch("url_collector.load_config", return_value={}):
            result = c.search_locations("United States")
        self.assertEqual(result, [{"id": "23424977", "name": "United States"}])


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(web, "ROOT", self.root)
        self.root_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.root_patch.stop()
        self.temp.cleanup()

    def post(self, route, body):
        request = Request(self.url + route, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.load(response)
        except HTTPError as response:
            return response.code, json.load(response)

    def test_preview_returns_separate_states_without_starting_job(self):
        with patch("web_app.start_job") as start:
            status, data = self.post("/api/plan/preview", {"category_id": 34, "states": ["failed", "successful"]})
        self.assertEqual(status, 200)
        self.assertEqual(len(data["batches"]), 2)
        start.assert_not_called()

    def test_bad_range_and_sort_return_400(self):
        for data in ({"goal_min": 100, "goal_max": 10}, {"sort": "invalid"}, {"raised_max": "nan"}):
            status, payload = self.post("/api/plan/preview", data)
            self.assertEqual(status, 400)
            self.assertIn("error", payload)

    def test_collect_writes_reviewed_plan_and_returns_job(self):
        with patch("web_app.start_job", return_value={"id": "test"}) as start:
            status, payload = self.post("/api/jobs/collect", {"states": ["failed", "successful"]})
        self.assertEqual(status, 202)
        argv = start.call_args.args[1]
        plan = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        self.assertEqual(len(plan["batches"]), 2)
        self.assertEqual(argv[0], "--plan-file")

    def test_location_endpoint_returns_selectable_options(self):
        with patch("web_app.cached_locations", return_value=[{"id": "23424977", "name": "United States"}]):
            with urlopen(self.url + "/api/locations?term=United%20States") as response:
                self.assertEqual(json.load(response)["locations"][0]["id"], "23424977")

    def test_exit_three_is_partial_and_parses_summary(self):
        process = Mock(stdout=['PLAN_SUMMARY {"complete": false, "total_urls": 3}\n'])
        process.wait.return_value = 3
        with patch.dict(web.JOBS, {"x": {"kind": "collect", "status": "queued", "log": []}}, clear=True), patch("web_app.subprocess.Popen", return_value=process):
            web.run_job("x", ["test"])
            self.assertEqual(web.JOBS["x"]["status"], "partial")
            self.assertFalse(web.JOBS["x"]["summary"]["complete"])


if __name__ == "__main__":
    unittest.main()
