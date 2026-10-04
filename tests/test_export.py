"""export tests — CSV/JSON round-trips against a seeded temp database."""

import csv
import io
import json

import pytest

from leadhound import config, exporter
from leadhound.exporter import export_csv, export_json


def _seed(guid: str, score: int, title: str, status: str = "pending",
          outcome: str | None = None) -> int:
    from leadhound import db

    rid, _ = db.upsert_job(
        {
            "guid": guid,
            "source": "remoteok",
            "title": title,
            "url": f"https://example.com/{guid}",
            "body": f"Body of {title}",
            "tags": ["react", "stripe"],
            "hourly": 60,
        },
        score,
        {
            "budget": {"hourly": 60, "fixed_min": None},
            "skills": {"matched": ["react"]},
            "red_flags": ["unpaid trial"] if score < 50 else [],
        },
        f"Draft for {title}",
    )
    if status != "pending":
        db.set_status(rid, status)
    if outcome:
        db.set_outcome(rid, outcome)
    return rid


@pytest.fixture(autouse=False)
def seeded():
    config.init_files()
    _seed("x1", 92, "Great gig", status="sent", outcome="won")
    _seed("x2", 71, "Okay gig", status="approved")
    _seed("x3", 45, "Meh gig", status="rejected")
    _seed("x4", 30, "Bad gig")


class TestJson:
    def test_all_rows_roundtrip(self, seeded):
        rows = json.loads(export_json())
        assert len(rows) == 4
        assert [r["score"] for r in rows] == sorted(
            (r["score"] for r in rows), reverse=True
        )
        top = rows[0]
        assert top["title"] == "Great gig"
        assert top["outcome"] == "won"
        assert top["matched_skills"] == "react"
        assert top["draft"] == "Draft for Great gig"

    def test_status_and_score_filters(self, seeded):
        rows = json.loads(export_json(status="sent"))
        assert [r["title"] for r in rows] == ["Great gig"]
        rows = json.loads(export_json(min_score=70))
        assert [r["title"] for r in rows] == ["Great gig", "Okay gig"]

    def test_bad_status_raises(self, seeded):
        with pytest.raises(ValueError):
            export_json(status="banana")


class TestCsv:
    def test_header_and_rows(self, seeded):
        reader = csv.DictReader(io.StringIO(export_csv()))
        assert reader.fieldnames == list(exporter.CSV_COLUMNS)
        rows = list(reader)
        assert len(rows) == 4
        assert rows[0]["title"] == "Great gig"
        assert rows[0]["hourly"] == "60.0"  # SQLite REAL column

    def test_semicolons_keep_csv_clean(self, seeded):
        rows = list(csv.DictReader(io.StringIO(export_csv())))
        assert rows[0]["matched_skills"] == "react"
        assert rows[3]["tags"] == "react;stripe"  # comma inside a field would break naive parsers

    def test_csv_filter_matches_json(self, seeded):
        # csv and json must agree per status
        n_csv = len(list(csv.DictReader(io.StringIO(export_csv(status="rejected")))))
        n_json = len(json.loads(export_json(status="rejected")))
        assert n_csv == n_json == 1


class TestFileExport:
    def test_write_to_file(self, seeded, tmp_path):
        for fmt, name in (("csv", "p.csv"), ("json", "p.json")):
            p = tmp_path / name
            n = exporter.export_to_file(fmt, str(p))
            assert n == 4
            text = p.read_text(encoding="utf-8")
            if fmt == "json":
                assert len(json.loads(text)) == 4
            else:
                assert text.splitlines()[0].startswith("id,score,status")

    def test_file_counts_respect_filters(self, seeded, tmp_path):
        p = tmp_path / "s.csv"
        n = exporter.export_to_file("csv", str(p), status="sent")
        assert n == 1
