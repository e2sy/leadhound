"""Reddit connector tests — [Hiring] only, [For Hire] skipped, sane
guids/urls/timestamps, subreddit parsing, error surfacing. Zero network."""

from __future__ import annotations

from leadhound.connectors import reddit


def _post(pid, title, body="", flair=None, created=1700000000.0):
    d = {"id": pid, "title": title, "selftext": body, "created_utc": created,
         "permalink": f"/r/forhire/comments/{pid}/x/"}
    if flair:
        d["link_flair_text"] = flair
    return {"data": d}


def _patch_listing(monkeypatch, posts, sub="forhire"):
    class R:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"children": posts}}

    monkeypatch.setattr(
        reddit.requests, "get",
        lambda url, **kw: R() if f"/r/{sub}/" in url else (_ for _ in ()).throw(AssertionError(url)),
    )


def test_hiring_kept_forhire_skipped(monkeypatch):
    _patch_listing(monkeypatch, [
        _post("a1", "[Hiring] React dev needed — $500 budget"),
        _post("a2", "[For Hire] I build react apps"),
        _post("a3", "hiring: stripe expert (no brackets)"),
        _post("a4", "just chatting"),
    ])
    jobs, err = reddit.fetch({"subreddits": "forhire"})
    assert err is None
    titles = [j["title"] for j in jobs]
    assert "[Hiring] React dev needed — $500 budget" in titles
    assert "hiring: stripe expert (no brackets)" in titles
    assert not any("For Hire" in t for t in titles)
    assert not any("just chatting" in t for t in titles)


def test_job_shape_and_source_tagging(monkeypatch):
    _patch_listing(monkeypatch, [
        _post("b1", "[Hiring] Shopify fixes", body="<p>some html</p>", flair="Task"),
    ])
    jobs, _ = reddit.fetch({"subreddits": "forhire"})
    j = jobs[0]
    assert j["guid"] == "reddit-b1"
    assert j["source"] == "reddit/forhire"
    assert j["url"].startswith("https://www.reddit.com/r/forhire/")
    assert j["body"] == "some html"
    assert j["tags"] == ["Task"]
    assert j["posted_at"].startswith("2023-")


def test_subreddit_parsing_normalizes():
    assert reddit.parse_subreddits({"subreddits": " ForHire, hiring,, jobbit "}) == \
        ["ForHire", "hiring", "jobbit"]
    assert reddit.parse_subreddits({}) == ["forhire", "hiring", "jobbit"]
    assert reddit.parse_subreddits({"subreddits": "a,b,a,b,c,d,e"}) == ["a", "b", "c", "d", "e"]
    assert reddit.parse_subreddits({"subreddits": "x;y/../z"}) == ["xyz"]


def test_multiple_subs_tag_their_source(monkeypatch):
    class R:
        def __init__(self, items):
            self._items = items

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"children": self._items}}

    def fake_get(url, **kw):
        if "/r/forhire/" in url:
            return R([_post("c1", "[Hiring] gig one")])
        if "/r/hiring/" in url:
            return R([_post("c2", "[Hiring] gig two")])
        raise AssertionError(url)

    monkeypatch.setattr(reddit.requests, "get", fake_get)
    jobs, _ = reddit.fetch({"subreddits": "forhire,hiring"})
    assert sorted(j["source"] for j in jobs) == ["reddit/forhire", "reddit/hiring"]


def test_error_surfaced_not_swallowed(monkeypatch):
    def boom(url, **kw):
        raise ConnectionError("reddit said no")

    monkeypatch.setattr(reddit.requests, "get", boom)
    jobs, err = reddit.fetch({"subreddits": "forhire"})
    assert jobs == []
    assert err and "ConnectionError" in err["error"]


def test_registry_entry_is_wired():
    from leadhound.connectors import REGISTRY
    c = REGISTRY["reddit"]
    assert c.min_poll == 5
    assert [f.name for f in c.fields] == ["subreddits"]
