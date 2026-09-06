#!/usr/bin/env python3
"""Validate the generated Grok marketplace catalog against sources.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES_PATH = ROOT / "sources.json"
MARKETPLACE_PATH = ROOT / ".grok-plugin" / "marketplace.json"
INDEX_PATH = ROOT / ".grok-plugin" / "plugin-index.json"
PLUGINS_DIR = ROOT / "plugins"


def error(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)


def main() -> int:
    errors: list[str] = []

    try:
        sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        error(f"sources.json: {exc}")
        return 1

    try:
        marketplace = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        error(f"marketplace.json: {exc}")
        return 1

    try:
        index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        error(f"plugin-index.json: {exc}")
        return 1

    declared = [p.get("name") for p in sources.get("plugins") or [] if p.get("name")]
    catalog = [p.get("name") for p in marketplace.get("plugins") or [] if p.get("name")]
    indexed = list((index.get("plugins") or {}).keys())

    if sorted(catalog) != sorted(declared):
        errors.append(
            f"marketplace plugins {catalog} do not match sources.json {declared}"
        )
    if sorted(indexed) != sorted(declared):
        errors.append(
            f"plugin-index plugins {indexed} do not match sources.json {declared}"
        )

    seen: set[str] = set()
    for name in declared:
        if name in seen:
            errors.append(f"duplicate plugin name {name!r}")
        seen.add(name)
        plugin_dir = PLUGINS_DIR / name
        skills = plugin_dir / "skills"
        if not skills.is_dir():
            errors.append(f"plugin {name!r}: missing {skills.relative_to(ROOT)}")
            continue
        skill_mds = list(skills.glob("*/SKILL.md"))
        if not skill_mds:
            errors.append(f"plugin {name!r}: no skills/*/SKILL.md")
        index_skills = (
            (index.get("plugins") or {})
            .get(name, {})
            .get("components", {})
            .get("skills")
            or []
        )
        on_disk = sorted(p.parent.name for p in skill_mds)
        in_index = sorted(s.get("name") for s in index_skills if s.get("name"))
        if on_disk != in_index:
            errors.append(
                f"plugin {name!r}: index skills {in_index} != disk {on_disk}"
            )
        source_meta = plugin_dir / "SOURCE.json"
        if source_meta.is_file():
            try:
                meta = json.loads(source_meta.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"plugin {name!r}: SOURCE.json: {exc}")
            else:
                sha = meta.get("sha")
                if not isinstance(sha, str) or len(sha) != 40:
                    errors.append(f"plugin {name!r}: SOURCE.json sha is not a full sha")

    if errors:
        for msg in errors:
            error(msg)
        return 1

    print(
        f"Catalog OK ({len(declared)} plugins: {', '.join(declared)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
