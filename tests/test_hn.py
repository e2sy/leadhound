"""HN watcher tests — pure parsing against saved fixture JSON, zero network."""

from leadhound.watchers import hn

SEARCH_HITS = [
    {"objectID": "111", "title": "Who is hiring? (January 2025)"},
    {"objectID": "222", "title": "Freelancer? Seeking freelancer? (January 2025)"},
    {"objectID": "333", "title": "Ask HN: how to price work"},
]

THREAD = {
    "id": 222,
    "title": "Freelancer? Seeking freelancer? (January 2025)",
    "children": [
        {
            "id": 9001,
            "created_at": "2025-01-02T10:00:00Z",
            "text": "<p>Looking for a <b>React Native</b> dev, $70/hr, 3-month project.</p>",
            "children": [
                {"id": 9999, "text": "<p>DM me</p>", "children": []},
            ],
        },
        {
            "id": 9002,
            "created_at": "2025-01-02T11:00:00Z",
            "text": "Studio needs a Next.js contractor for a fintech dashboard. Remote.",
            "children": [],
        },
        {"id": 9003, "created_at": "2025-01-02T12:00:00Z", "text": "", "children": []},
    ],
}


class TestPickThread:
    def test_picks_freelancer_thread_newest_first(self):
        assert hn.pick_thread(SEARCH_HITS)["objectID"] == "222"

    def test_returns_none_when_absent(self):
        assert hn.pick_thread([{"objectID": "1", "title": "Show HN: thing"}]) is None


class TestParseThread:
    def test_top_level_comments_become_gigs(self):
        gigs = hn.parse_thread(THREAD)
        assert len(gigs) == 2  # reply + empty comment excluded

    def test_guid_source_url_shape(self):
        g = hn.parse_thread(THREAD)[0]
        assert g["guid"] == "hn-9001"
        assert g["source"] == "hackernews"
        assert g["url"] == "https://news.ycombinator.com/item?id=9001"
        assert g["posted_at"] == "2025-01-02T10:00:00Z"

    def test_html_is_stripped_and_entities_unescaped(self):
        g = hn.parse_thread(THREAD)[0]
        assert "<b>" not in g["body"]
        assert "React Native" in g["body"]
        assert "$70/hr" in g["body"]

    def test_title_is_first_sentence(self):
        gigs = hn.parse_thread(THREAD)
        assert gigs[1]["title"].startswith("Studio needs a Next.js contractor")
