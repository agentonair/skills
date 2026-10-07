#!/usr/bin/env python3
"""Fail if the Claude Code plugin and Gemini CLI extension manifests disagree.

Checks, with no network access:
  - every manifest parses as a JSON object; the marketplace, its single plugin
    entry, plugin.json and gemini-extension.json are all named "agentonair"
  - the Claude manifests declare no "version", so Claude Code versions the
    plugin by git commit and existing installs pick up every skill sync; the
    Gemini manifest does declare one (Gemini CLI shows it, and tracks git HEAD)
  - plugin.json, the marketplace entry and gemini-extension.json share one
    description
  - both MCP configs are exactly the public, keyless, read-only AgentOnAir
    endpoint: no headers, env, command or extra keys
  - skills/ holds at least one <name>/SKILL.md for both clients to load
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "agentonair"
MCP_URL = "https://api.agentonair.com/mcp"
CLAUDE_MCP = {"type": "http", "url": MCP_URL}
GEMINI_MCP = {"httpUrl": MCP_URL, "timeout": 30000}


def load(relative: str) -> dict:
    path = ROOT / relative
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"{relative}: {error}")
    if not isinstance(data, dict):
        raise SystemExit(f"{relative}: top level must be a JSON object")
    return data


def servers(manifest: dict, label: str, errors: list[str]) -> dict:
    value = manifest.get("mcpServers")
    if not isinstance(value, dict):
        errors.append(f"{label}: mcpServers must be an object")
        return {}
    return value


def main() -> int:
    plugin = load(".claude-plugin/plugin.json")
    marketplace = load(".claude-plugin/marketplace.json")
    gemini = load("gemini-extension.json")
    claude_mcp = load(".mcp.json")
    errors: list[str] = []

    if marketplace.get("name") != NAME:
        errors.append(f"marketplace.json: name must be '{NAME}' (install id {NAME}@{NAME})")
    raw_plugins = marketplace.get("plugins")
    plugins: list = raw_plugins if isinstance(raw_plugins, list) else []
    entries = [e for e in plugins if isinstance(e, dict)]
    if len(entries) != 1 or len(plugins) != 1 or entries[0].get("name") != NAME:
        errors.append(f"marketplace.json: plugins must hold exactly one '{NAME}' entry")
        entry: dict = {}
    else:
        entry = entries[0]
        if entry.get("source") != "./":
            errors.append("marketplace.json: the plugin source must be './' (this repo root)")

    for label, manifest in (("plugin.json", plugin), ("gemini-extension.json", gemini)):
        if manifest.get("name") != NAME:
            errors.append(f"{label}: name must be '{NAME}'")

    for label, manifest in (("plugin.json", plugin), ("marketplace.json plugin entry", entry)):
        if "version" in manifest:
            errors.append(f"{label}: remove 'version' so Claude Code tracks the git commit")
    version = gemini.get("version")
    if not isinstance(version, str) or not version:
        errors.append("gemini-extension.json: version is required")

    descriptions = [plugin.get("description"), entry.get("description"), gemini.get("description")]
    if len(set(descriptions)) != 1 or not isinstance(descriptions[0], str) or not descriptions[0]:
        errors.append("plugin.json, marketplace.json and gemini-extension.json descriptions differ")

    if servers(claude_mcp, ".mcp.json", errors) != {NAME: CLAUDE_MCP}:
        errors.append(f".mcp.json: mcpServers must be exactly {{{NAME}: {CLAUDE_MCP}}}")
    if servers(gemini, "gemini-extension.json", errors) != {NAME: GEMINI_MCP}:
        errors.append(f"gemini-extension.json: mcpServers must be exactly {{{NAME}: {GEMINI_MCP}}}")
    if "mcpServers" in plugin:
        errors.append("plugin.json: declare MCP servers in .mcp.json only")

    skills_dir = ROOT / "skills"
    skill_dirs = sorted(p.name for p in skills_dir.iterdir() if (p / "SKILL.md").is_file()) if skills_dir.is_dir() else []
    if not skill_dirs:
        errors.append("skills/ has no <name>/SKILL.md folders")

    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(f"manifests agree: {NAME} (gemini {version}), mcp {MCP_URL}, skills {', '.join(skill_dirs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
