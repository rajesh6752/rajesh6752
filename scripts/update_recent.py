#!/usr/bin/env python3
"""Rewrite the "Recently active" table in README.md from live GitHub data.

    GITHUB_TOKEN=... scripts/update_recent.py [--dry-run]

Lists the owner's public, non-fork, non-archived repositories ordered by last
push, minus `recent.exclude`, newer than `recent.max_age_days`, at most
`recent.limit` (all from profile.toml). Only the text between the
`<!-- recent:start -->` and `<!-- recent:end -->` markers is replaced.

Prints "changed" or "unchanged". Any API or parse failure exits non-zero:
a stale table is better than a silently emptied one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
START, END = "<!-- recent:start -->", "<!-- recent:end -->"

QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(first: 50, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes { name url description pushedAt isArchived primaryLanguage { name } }
    }
  }
}
"""


def fetch(login: str, token: str) -> list[dict]:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-readme-refresh",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"GitHub API returned HTTP {e.code}: {e.read().decode(errors='replace')[:500]}") from e
    if payload.get("errors"):
        raise SystemExit(f"GitHub API errors: {json.dumps(payload['errors'])[:500]}")
    user = (payload.get("data") or {}).get("user")
    if user is None:
        raise SystemExit(f"GitHub user {login!r} not found")
    return user["repositories"]["nodes"]


def cell(text: str | None) -> str:
    """Make arbitrary text safe inside a Markdown table cell."""
    return " ".join((text or "").split()).replace("|", "\\|") or "—"


def render(repos: list[dict], cfg: dict, now: datetime) -> str:
    rc = cfg["recent"]
    excluded = {name.lower() for name in rc.get("exclude", [])}
    cutoff = now - timedelta(days=rc["max_age_days"])
    rows = []
    for r in repos:
        pushed = datetime.fromisoformat(r["pushedAt"].replace("Z", "+00:00"))
        if r["isArchived"] or r["name"].lower() in excluded or pushed < cutoff:
            continue
        lang = (r.get("primaryLanguage") or {}).get("name")
        rows.append(
            f"| [{r['name']}]({r['url']}) | {cell(r['description'])} | {cell(lang)} | {pushed:%b %Y} |"
        )
        if len(rows) == rc["limit"]:
            break
    if not rows:
        return f"_Nothing public pushed in the last {rc['max_age_days']} days._"
    return "\n".join(["| Repository | What it is | Language | Last push |", "| --- | --- | --- | --- |", *rows])


def splice(readme: str, block: str) -> str:
    if readme.count(START) != 1 or readme.count(END) != 1 or readme.index(START) > readme.index(END):
        raise SystemExit(f"README.md must contain exactly one {START} … {END} pair, in that order")
    head, rest = readme.split(START)
    _, tail = rest.split(END)
    return f"{head}{START}\n{block}\n{END}{tail}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print the table instead of writing README.md")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("Set GITHUB_TOKEN (or GH_TOKEN) to call the GitHub API")

    cfg = tomllib.loads((ROOT / "profile.toml").read_text(encoding="utf-8"))
    block = render(fetch(cfg["login"], token), cfg, datetime.now(UTC))
    if args.dry_run:
        print(block)
        return 0

    before = README.read_text(encoding="utf-8")
    after = splice(before, block)
    if after == before:
        print("unchanged")
    else:
        README.write_text(after, encoding="utf-8")
        print("changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
