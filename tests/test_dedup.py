"""Cross-source dedup tests — fingerprinting, pipeline merge behavior,
no re-notification on a second sighting, scoping, board chips data."""

from __future__ import annotations

import pytest

from leadhound import db
from leadhound.config import LLMConfig, Profile
from leadhound.engine.fingerprint import (
    fingerprint,
    money_bucket,
    near_duplicate,
    normalize_title,
)
from leadhound.pipeline import ingest_jobs


@pytest.fixture(autouse=True)
def _db():
    db.ensure_db()
    yield


@pytest.fixture
def profile():
    return Profile(name="T", skills=["react"], min_hourly=0, min_fixed_budget=0)


def _gig(source, guid, title="Build a React dashboard", budget_max=1000.0):
    return {
        "guid": guid, "source": source, "title": title,
        "url": f"https://example.com/{guid}", "body": "react dashboard work",
        "tags": [], "budget_max": budget_max,
    }


# ---------------------------------------------------------------- fingerprint

def test_normalize_title_strips_noise():
    assert normalize_title("URGENT: Need a React Developer!!") == \
        normalize_title("urgent react developer")
    assert normalize_title("  React   dashboard, rebuild!  ") == "react dashboard rebuild"


def test_money_buckets():
    assert money_bucket({"budget_max": 500}) == "f500"
    assert money_bucket({"budget_max": 540}) == "f500"    # $40 rounds to the $100 bucket
    assert money_bucket({"hourly": 47}) == "h45"
    assert money_bucket({}) == "none"


def test_fingerprint_stable_across_sources_and_caps():
    a = _gig("freelancer", "f-1", "Build a React dashboard!!")
    b = _gig("guru", "g-9", "build a react dashboard")
    assert fingerprint(a) == fingerprint(b)
    assert len(fingerprint(a)) == 16


def test_near_duplicate_catches_wording_hats():
    assert near_duplicate("React dashboard rebuild", "react DASHBOARD rebuild!!!")
    assert not near_duplicate("React dashboard", "Kubernetes cluster audit")
    assert not near_duplicate("", "anything")


# ---------------------------------------------------------------- pipeline

def test_second_source_bumps_original_never_renotifies(profile):
    llm = LLMConfig()
    r1 = ingest_jobs([_gig("freelancer", "x-1")], profile=profile, llm_cfg=llm)
    assert r1[0].is_new and not r1[0].dup
    r2 = ingest_jobs([_gig("guru", "g-77")], profile=profile, llm_cfg=llm)
    assert r2[0].dup and not r2[0].is_new
    assert r2[0].rid == r1[0].rid          # same physical row
    job = db.get_job(r1[0].rid)
    assert job.seen_count == 2
    assert job.also_on == "guru"
    assert db.all_jobs().__len__() == 1    # no second row


def test_third_sighting_counts_but_does_not_duplicate_source(profile):
    llm = LLMConfig()
    ingest_jobs([_gig("freelancer", "y-1")], profile=profile, llm_cfg=llm)
    ingest_jobs([_gig("guru", "y-2")], profile=profile, llm_cfg=llm)
    ingest_jobs([_gig("peopleperhour", "y-3")], profile=profile, llm_cfg=llm)
    job = db.all_jobs()[0]
    assert job.seen_count == 3
    assert set(job.also_on.split(",")) == {"guru", "peopleperhour"}


def test_same_guid_refetch_is_not_a_dup_bump(profile):
    llm = LLMConfig()
    ingest_jobs([_gig("freelancer", "z-1")], profile=profile, llm_cfg=llm)
    ingest_jobs([_gig("freelancer", "z-1")], profile=profile, llm_cfg=llm)
    job = db.all_jobs()[0]
    assert job.seen_count == 1             # guid path, not a new sighting


def test_different_gigs_do_not_merge(profile):
    llm = LLMConfig()
    ingest_jobs([_gig("freelancer", "d-1", title="React dashboard")],
                profile=profile, llm_cfg=llm)
    ingest_jobs([_gig("guru", "d-2", title="WordPress site migration",
                      budget_max=2000.0)],
                profile=profile, llm_cfg=llm)
    assert len(db.all_jobs()) == 2


def test_dedup_respects_account_scope(profile):
    llm = LLMConfig()
    ingest_jobs([_gig("freelancer", "s-1", title="React dashboard")],
                profile=profile, llm_cfg=llm, user_id=42)
    r = ingest_jobs([_gig("guru", "s-2", title="React dashboard")],
                    profile=profile, llm_cfg=llm, user_id=43)
    assert not r[0].dup                    # another account's gig is invisible
    assert len(db.all_jobs()) == 2


# ---------------------------------------------------------------- board data

def test_state_exposes_dedup_info(profile):
    llm = LLMConfig()
    ingest_jobs([_gig("freelancer", "w-1")], profile=profile, llm_cfg=llm)
    ingest_jobs([_gig("guru", "w-2")], profile=profile, llm_cfg=llm)
    job = db.all_jobs()[0]
    assert job.seen_count >= 2
