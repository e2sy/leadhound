"""Client intel tests — token extraction + poster history cross-reference."""

from leadhound import config, db
from leadhound.engine import intel


def _seed(guid: str, score: int, body: str) -> int:
    rid, _ = db.upsert_job(
        {
            "guid": guid, "source": "remoteok", "title": f"Gig {guid}",
            "url": f"https://example.com/{guid}", "body": body, "tags": [],
        },
        score, {}, "",
    )
    return rid


class TestClientToken:
    def test_email_domain_wins(self):
        assert intel.client_token("contact us at hr@acme-corp.com today") == "acme-corp.com"

    def test_url_domain_fallback(self):
        assert intel.client_token("apply at https://jobs.fintech.io/careers now") == "jobs.fintech.io"

    def test_job_board_domains_ignored(self):
        body = "apply https://remoteok.com/x or mail jobs@remoteok.com"
        assert intel.client_token(body) is None

    def test_nothing_extractable(self):
        assert intel.client_token("no contact info here, sorry") is None

    def test_email_beats_url(self):
        body = "https://linktr.ee/me or sarah@zoolabs.io"
        assert intel.client_token(body) == "zoolabs.io"


class TestPosterHistory:
    def test_counts_and_averages_prior_gigs(self):
        config.init_files()
        _seed("a1", 30, "hiring@lowballs.io pay $5")
        _seed("a2", 40, "hiring@lowballs.io pay $8 again")
        rid = _seed("a3", 90, "hiring@lowballs.io pay $10 third time")
        n, avg = intel.poster_history("lowballs.io", exclude_id=rid)
        assert n == 2
        assert avg == 35.0

    def test_excludes_current_gig_from_history(self):
        config.init_files()
        rid = _seed("b1", 70, "boss@fresh.io hello")
        n, _ = intel.poster_history("fresh.io", exclude_id=rid)
        assert n == 0


class TestIntelFor:
    def test_repeat_lowballer_flagged(self):
        config.init_files()
        _seed("c1", 20, "hr@sweatshop.io unpaid internship")
        _seed("c2", 30, "hr@sweatshop.io again")
        rid = _seed("c3", 55, "hr@sweatshop.io yet again")
        job = db.get_job(rid)
        tip = intel.intel_for(job)
        assert tip and "repeat lowballer" in tip and "sweatshop.io" in tip

    def test_healthy_poster_flagged_neutral(self):
        config.init_files()
        _seed("d1", 85, "talent@whales.io great budget")
        rid = _seed("d2", 90, "talent@whales.io another one")
        tip = intel.intel_for(db.get_job(rid))
        assert tip and "avg 85" in tip
        assert "lowballer" not in tip

    def test_first_time_poster_gets_no_intel(self):
        config.init_files()
        rid = _seed("e1", 80, "ceo@onestartup.io hello")
        assert intel.intel_for(db.get_job(rid)) is None

    def test_unidentifiable_poster_gets_no_intel(self):
        config.init_files()
        rid = _seed("f1", 80, "no contact info")
        assert intel.intel_for(db.get_job(rid)) is None
