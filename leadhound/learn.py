"""profile learn — read a public GitHub profile and tune your skills list.

Uses only the public, unauthenticated GitHub API (ToS-safe, same stance as
the watchers): repos, languages and topics you already publish to the world.
"""

from __future__ import annotations

import json
import re
import urllib.request

from .watchers import UA

_TIMEOUT = 15

# GitHub language names that are noise for freelance matching, or dangerous
# substrings ("go" matches "google", "good morning"). Mapped or dropped.
_SKILL_MAP = {
    "go": "golang",
    "shell": "bash",
    "c++": "c++",
    "c#": "c#",
    "objective-c": "objective-c",
    "objective-c++": "objective-c",
    "vue": "vue.js",
    "vuejs": "vue.js",
    "nuxt": "nuxt.js",
    "nuxtjs": "nuxt.js",
    "next": "next.js",
    "nextjs": "next.js",
    "node": "node.js",
    "nodejs": "node.js",
    "react native": "react native",
}
_NOISE_LANGUAGES = {
    "html", "css", "scss", "less", "makefile", "dockerfile", "batchfile",
    "powershell", "vim script", "emacs lisp", "jupyter notebook",
    "shaderlab", "glsl", "hcl", "regex", "sed", "awk", "qml", "razor",
}

_GH_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9-]{1,39})/?$"
    r"|^([A-Za-z0-9-]{1,39})$"
)


def parse_github_target(raw: str) -> str:
    """'https://github.com/e2sy', 'github.com/e2sy' or 'e2sy' -> 'e2sy'."""
    m = _GH_RE.match(raw.strip())
    if not m:
        raise ValueError(f"not a GitHub user or profile URL: {raw!r}")
    return m.group(1) or m.group(2)


def _get_json(url: str) -> object:
    # URL is always an https://api.github.com endpoint we build ourselves.
    req = urllib.request.Request(url, headers={**UA, "Accept": "application/vnd.github+json"})  # noqa: S310
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:  # noqa: S310
        return json.loads(r.read().decode("utf-8"))


def normalize_skill(name: str, *, is_topic: bool = False) -> str | None:
    """GitHub language/topic name -> job-post skill token (or None to drop).

    Topics are hyphenated on GitHub ("react-native") but job posts write
    them with spaces, so topics get an extra hyphen->space pass.
    """
    low = name.strip().lower()
    if is_topic:
        low = low.replace("-", " ")
    if not low or low in _NOISE_LANGUAGES:
        return None
    return _SKILL_MAP.get(low, low)


def learn_skills(username: str, *, skip_forks: bool = True) -> dict:
    """Pull public repos for a user and rank the skills they imply.

    Returns {"user", "name", "bio", "languages": [top, ...], "topics": [...]}.
    """
    user = parse_github_target(username)
    profile = _get_json(f"https://api.github.com/users/{user}")
    if "message" in profile and profile.get("message") == "Not Found":
        raise ValueError(f"GitHub user not found: {user}")
    repos = _get_json(
        f"https://api.github.com/users/{user}/repos?per_page=100&sort=pushed"
    )
    if not isinstance(repos, list):
        raise ValueError("unexpected response from GitHub repos API")

    lang_counts: dict[str, int] = {}
    topic_counts: dict[str, int] = {}
    pushed = 0
    for r in repos:
        if skip_forks and r.get("fork"):
            continue
        pushed += 1
        if r.get("language"):
            tok = normalize_skill(str(r["language"]))
            if tok:
                lang_counts[tok] = lang_counts.get(tok, 0) + 1
        for t in r.get("topics") or []:
            tok = normalize_skill(str(t), is_topic=True)
            if tok:
                topic_counts[tok] = topic_counts.get(tok, 0) + 1

    languages = [k for k, _ in sorted(lang_counts.items(), key=lambda kv: -kv[1])]
    topics = [k for k, _ in sorted(topic_counts.items(), key=lambda kv: -kv[1])]
    return {
        "user": user,
        "name": profile.get("name") or user,
        "bio": profile.get("bio") or "",
        "repos_scanned": pushed,
        "languages": languages,
        "topics": topics,
    }


# ----------------------------------------------------------------- tomllib-free edit
_SKILLS_RE = re.compile(r"(?m)^skills\s*=\s*\[.*?]", re.S)


def merge_skills(existing: list[str], detected: list[str], cap: int = 16) -> list[str]:
    """User's own skills keep their order (priority); new detected ones append."""
    out = list(dict.fromkeys(existing))
    for s in detected:
        if len(out) >= cap:
            break
        if s not in out:
            out.append(s)
    return out


def update_profile_skills(profile_text: str, new_skills: list[str]) -> tuple[str, bool]:
    """Swap only the `skills = [...]` block, preserving every other line/comment.

    Returns (new_text, replaced). If no skills block exists, nothing changes.
    """
    rendered = "skills = [\n" + "".join(f'  "{s}",\n' for s in new_skills) + "]"
    new_text, n = _SKILLS_RE.subn(rendered, profile_text, count=1)
    return new_text, n == 1
