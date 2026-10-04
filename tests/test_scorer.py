"""Scorer tests — the score is the product, so it gets the most coverage."""

from leadhound.engine.scorer import score_job

# Body touches all 6 profile skills -> full skill points (60)
BASE_JOB = {
    "guid": "t-1",
    "source": "test",
    "title": "React developer needed",
    "url": "https://example.com/1",
    "body": "Stack: React, TypeScript, Stripe, Node.js, Python, Next.js. Payment verified. $60/hr.",
    "tags": [],
}


class TestScoreJob:
    def test_strong_gig_scores_high(self, profile):
        total, breakdown = score_job(BASE_JOB, profile)
        # skills(60: all 6 matched) + budget(25: $60/hr >= $30 floor) + quality(12: verified)
        assert total == 97
        assert set(breakdown["skills"]["matched"]) >= {"react", "typescript", "stripe"}

    def test_breakdown_is_human_readable(self, profile):
        _, breakdown = score_job(BASE_JOB, profile)
        assert "meets your $" in breakdown["budget"]["note"]
        assert "payment verified" in breakdown["client_quality"]["signals"]

    def test_red_flag_trap_is_punished(self, profile):
        trap = dict(BASE_JOB)
        trap["body"] = BASE_JOB["body"] + " This is unpaid work, great for exposure."
        total, breakdown = score_job(trap, profile)
        assert total == 97 - 30  # two red flags, -15 each
        assert set(breakdown["red_flags"]) == {"unpaid", "for exposure"}

    def test_below_floor_hourly_scores_low(self, profile):
        cheap = dict(BASE_JOB)
        cheap["body"] = "Stack: React, TypeScript, Stripe, Node.js, Python, Next.js. $10/hr."
        total, breakdown = score_job(cheap, profile)
        assert breakdown["budget"]["points"] == 5
        assert total == 60 + 5 + 8

    def test_no_budget_is_neutral(self, profile):
        vague = dict(BASE_JOB)
        vague["body"] = "just react stuff"
        _, breakdown = score_job(vague, profile)
        assert breakdown["budget"]["note"] == "no budget stated (neutral)"

    def test_zero_skills_scores_low(self, profile):
        alien = {
            "guid": "t-2", "source": "test", "title": "COBOL migration",
            "url": "x", "body": "mainframe", "tags": [],
        }
        total, _ = score_job(alien, profile)
        assert total <= 33  # at most budget(25) + quality(8), zero skill points

    def test_score_never_exceeds_100(self, profile):
        godlike = dict(BASE_JOB)
        godlike["body"] = (
            "react typescript stripe node.js python next.js, payment verified, 20 hires, top rated, $100/hr"
        )
        total, _ = score_job(godlike, profile)
        assert total <= 100

    def test_score_never_below_zero(self, profile):
        nightmare = {
            "guid": "t-3", "source": "test", "title": "free work",
            "url": "x", "body": "unpaid for exposure unpaid", "tags": [],
        }
        total, _ = score_job(nightmare, profile)
        assert total >= 0
