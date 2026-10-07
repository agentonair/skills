#!/usr/bin/env python3
"""Mirror the skills published at agentonair.com into skills/<name>/SKILL.md.

The site's Agent Skills discovery index is the source of truth:
https://agentonair.com/.well-known/agent-skills/index.json

  --check  exit 1 if this checkout differs from the live index (no writes)
  (default) rewrite skills/ to match the live index

Every downloaded file must match the sha256 digest the index declares, or the
script exits non-zero without writing anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import urllib.request
from pathlib import Path

SITE = "https://agentonair.com"
INDEX_URL = f"{SITE}/.well-known/agent-skills/index.json"
SKILL_BASE = f"{SITE}/.well-known/agent-skills/"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
USER_AGENT = "agentonair-skills-mirror/1.0 (+https://github.com/agentonair/skills)"


def fetch(url: str) -> bytes:
    if not url.startswith(SKILL_BASE) and url != INDEX_URL:
        raise SystemExit(f"refusing to fetch outside {SKILL_BASE}: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise SystemExit(f"{url} returned HTTP {response.status}")
        return response.read()


def load_live() -> dict[str, bytes]:
    index = json.loads(fetch(INDEX_URL))
    entries = index.get("skills")
    if not isinstance(entries, list) or not entries:
        raise SystemExit("index has no skills; refusing to mirror an empty set")
    live: dict[str, bytes] = {}
    for entry in entries:
        name = entry.get("name", "")
        if not NAME_RE.match(name):
            raise SystemExit(f"invalid skill name in index: {name!r}")
        if name in live:
            raise SystemExit(f"duplicate skill name in index: {name}")
        if entry.get("type") != "skill-md":
            raise SystemExit(f"{name}: unsupported type {entry.get('type')!r}")
        if entry.get("url") != f"{name}/SKILL.md":
            raise SystemExit(f"{name}: unexpected url {entry.get('url')!r}")
        digest = entry.get("digest", "")
        if not digest.startswith("sha256:"):
            raise SystemExit(f"{name}: missing sha256 digest")
        body = fetch(SKILL_BASE + entry["url"])
        actual = "sha256:" + hashlib.sha256(body).hexdigest()
        if actual != digest:
            raise SystemExit(f"{name}: digest mismatch (index {digest}, file {actual})")
        if not body.startswith(b"---\n") or f"\nname: {name}\n".encode() not in body:
            raise SystemExit(f"{name}: SKILL.md frontmatter does not declare name: {name}")
        live[name] = body
    return live


def local_state() -> dict[str, bytes]:
    if not SKILLS_DIR.is_dir():
        return {}
    state: dict[str, bytes] = {}
    for path in sorted(SKILLS_DIR.iterdir()):
        if path.is_dir():
            skill_md = path / "SKILL.md"
            state[path.name] = skill_md.read_bytes() if skill_md.is_file() else b""
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail on drift, write nothing")
    args = parser.parse_args()

    live = load_live()
    local = local_state()
    drift = sorted(name for name in set(live) | set(local) if live.get(name) != local.get(name))
    for name, body in sorted(live.items()):
        print(f"{name}: sha256:{hashlib.sha256(body).hexdigest()} {len(body)} bytes")

    if not drift:
        print("in sync with", INDEX_URL)
        return 0
    if args.check:
        print("drift from", INDEX_URL, "in:", ", ".join(drift), file=sys.stderr)
        return 1

    for name in drift:
        target = SKILLS_DIR / name
        if name in live:
            target.mkdir(parents=True, exist_ok=True)
            (target / "SKILL.md").write_bytes(live[name])
            print("updated", name)
        else:
            shutil.rmtree(target)
            print("removed", name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
