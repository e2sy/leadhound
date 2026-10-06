"""Board RSS connector tests (Guru / PeoplePerHour shared plumbing) —
XML parsing, HTML bot-wall honesty, malformed feeds. Zero network."""

from __future__ import annotations

import pytest

from leadhound.connectors import REGISTRY, board_rss, guru, pph

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Guru job one — $500 fixed</title>
    <link>https://www.guru.com/p/1</link>
    <guid>guru-1</guid>
    <description>Budget $500. &lt;b&gt;React&lt;/b&gt; work.</description>
    <pubDate>Thu, 01 Oct 2026 10:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Guru job two</title>
    <link>https://www.guru.com/p/2</link>
  </item>
</channel></rss>"""

HTML_WALL = (
    "<html><head><META NAME=\"ROBOTS\" CONTENT=\"NOINDEX\">"
    "<script src=\"/_Incapsula_Resource?x\"></script></head><body>blocked</body></html>"
)


class Resp:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


def test_rss_entries_become_jobs(monkeypatch):
    monkeypatch.setattr(board_rss.requests, "get", lambda url, **kw: Resp(RSS.encode()))
    jobs, err = guru.fetch({})
    assert err is None
    assert [j["guid"] for j in jobs][:1] == ["guru-1"]
    assert jobs[0]["source"] == "guru"
    assert jobs[0]["title"] == "Guru job one — $500 fixed"
    assert "React" in jobs[0]["body"] and "<b>" not in jobs[0]["body"]
    assert jobs[0]["posted_at"] and jobs[0]["posted_at"].startswith("2026-")
    assert jobs[1]["url"].endswith("/p/2")


def test_html_bot_wall_becomes_honest_error(monkeypatch):
    monkeypatch.setattr(board_rss.requests, "get", lambda url, **kw: Resp(HTML_WALL.encode()))
    jobs, err = guru.fetch({})
    assert jobs == []
    assert err and "bot protection" in err["error"] and "guru" in err["error"]


def test_garbage_xml_becomes_error_not_crash(monkeypatch):
    monkeypatch.setattr(
        board_rss.requests, "get", lambda url, **kw: Resp(b"this is not xml at all <<<>>>")
    )
    jobs, err = pph.fetch({})
    assert jobs == []
    assert err and "parse" in err["error"]


def test_pph_source_tagging(monkeypatch):
    monkeypatch.setattr(board_rss.requests, "get", lambda url, **kw: Resp(RSS.encode()))
    jobs, err = pph.fetch({})
    assert err is None
    assert all(j["source"] == "peopleperhour" for j in jobs)


def test_registry_wired():
    for cid in ("guru", "peopleperhour"):
        c = REGISTRY[cid]
        assert c.min_poll == 5
        assert c.kind == "public"
        assert c.fetch is not None
    assert guru.FEED_URL.startswith("https://www.guru.com/")
    assert pph.FEED_URL.startswith("https://www.peopleperhour.com/")


def test_http_error_propagates(monkeypatch):
    class Boom:
        def raise_for_status(self):
            raise ConnectionError("403")

    monkeypatch.setattr(board_rss.requests, "get", lambda url, **kw: Boom())
    with pytest.raises(ConnectionError):
        guru.fetch({})
