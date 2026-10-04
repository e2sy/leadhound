"""Parser tests — money, quality signals, red flags, skill matching."""

from leadhound.engine import parser


class TestExtractMoney:
    def test_hourly(self):
        lo, hi, hourly = parser.extract_money("We pay $45/hr for this role")
        assert (lo, hi, hourly) == (None, None, 45.0)

    def test_hourly_per_hour(self):
        _, _, hourly = parser.extract_money("budget is $30 per hour")
        assert hourly == 30.0

    def test_fixed_range(self):
        lo, hi, hourly = parser.extract_money("Budget: $1,500 - $3,000")
        assert (lo, hi, hourly) == (1500.0, 3000.0, None)

    def test_single_fixed(self):
        lo, hi, _ = parser.extract_money("Fixed budget $2,000")
        assert (lo, hi) == (2000.0, 2000.0)

    def test_no_money(self):
        assert parser.extract_money("no budget mentioned at all") == (None, None, None)


class TestExtractQuality:
    def test_baseline(self):
        pts, signals = parser.extract_quality("looking for a dev, nothing special")
        assert pts == 8
        assert signals == []

    def test_payment_verified(self):
        pts, signals = parser.extract_quality("payment verified on this account")
        assert pts == 12
        assert "payment verified" in signals

    def test_hires_and_rating_capped_at_15(self):
        text = "payment verified, 10+ hires, top rated plus"
        pts, signals = parser.extract_quality(text)
        assert pts == 15
        assert len(signals) == 3


class TestRedFlags:
    def test_flags_detected(self):
        flags = parser.find_red_flags(
            "This is unpaid work but great for exposure",
            ["unpaid", "for exposure", "equity only"],
        )
        assert "unpaid" in flags and "for exposure" in flags

    def test_clean_text(self):
        assert parser.find_red_flags("well-funded startup, market rate", ["unpaid"]) == []


class TestMatchSkills:
    def test_matches_are_case_insensitive(self):
        matched = parser.match_skills(
            "React Native + Stripe + TypeScript", ["react native", "stripe", "typescript"]
        )
        assert matched == ["react native", "stripe", "typescript"]

    def test_no_match(self):
        assert parser.match_skills("we need a COBOL wizard", ["react"]) == []
