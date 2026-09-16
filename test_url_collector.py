import argparse
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import url_collector


def args_for(tmp, **overrides):
    values = dict(
        discover_url=url_collector.BASE_URL,
        term="board game",
        category_id=12,
        states=["successful"],
        sort="newest",
        years=[2025],
        max_pages=3,
        max_projects=0,
        delay_min=0,
        delay_max=0,
        timeout=1,
        retries=1,
        request_mode="http",
        stop_after_old_pages=2,
        output=str(Path(tmp) / "candidate.csv"),
        checkpoint=None,
        resume=False,
        config=str(Path(tmp) / "missing.json"),
    )
    values.update(overrides)
    return argparse.Namespace(**values)


def project(pid, year):
    return {
        "id": pid,
        "name": f"Project {pid}",
        "launched_at": 1735689600 if year == 2025 else 1704067200,
        "state": "successful",
        "country": "US",
        "category": {"name": "Tabletop Games", "parent_name": "Games"},
        "urls": {"web": {"project": f"https://www.kickstarter.com/projects/user/p-{pid}?ref=x"}},
    }


class CollectorTests(unittest.TestCase):
    def test_build_url_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp)
            url = url_collector.build_query_url(args, 7)
            self.assertIn("page=7", url)
            self.assertIn("sort=newest", url)
            self.assertIn("category_id=12", url)
            self.assertIn("state%5B%5D=successful", url)
            with self.assertRaises(ValueError):
                url_collector.validate_discover_url("https://example.com/discover")

    def test_year_filter_dedupe_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, max_pages=1)
            payload = {"projects": [project(1, 2025), project(1, 2025), project(2, 2024)], "has_more": True}
            with patch("url_collector.request_page", return_value=payload):
                summary = url_collector.collect_urls(args, lambda _: None)
            self.assertEqual(summary["new_urls"], 1)
            self.assertEqual(summary["total_urls"], 1)
            with Path(args.output).open(encoding="utf-8-sig") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(rows[0]["launched_year"], "2025")
            checkpoint = json.loads(Path(args.output + ".checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["next_page"], 2)

    def test_resume_starts_at_saved_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = args_for(tmp, max_pages=1, resume=True)
            signature = url_collector.query_signature(args)
            Path(args.output + ".checkpoint.json").write_text(
                json.dumps({"query_signature": signature, "next_page": 4}), encoding="utf-8"
            )
            seen = []
            def fake_page(session, url, proxy_url, timeout, retries):
                seen.append(url)
                return {"projects": [], "has_more": False}
            with patch("url_collector.request_page", side_effect=fake_page):
                url_collector.collect_urls(args, lambda _: None)
            self.assertIn("page=4", seen[0])


if __name__ == "__main__":
    unittest.main()
