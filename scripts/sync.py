#!/usr/bin/env python3
"""Vendor plugin payloads from upstream git repos into plugins/.

Source of truth for *what* to sync is sources.json. Humans add a plugin
by appending an entry there; this script copies skills + manifest +
license, then regenerates .grok-plugin/marketplace.json and
.grok-plugin/plugin-index.json.

Usage:
  python3 scripts/sync.py
  python3 scripts/sync.py --only rab
  python3 scripts/sync.py --only rab --from-local /path/to/rab
  python3 scripts/sync.py --local-map rab=/path/to/rab,csi=/path/to/csi
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES_PATH = ROOT / "sources.json"
PLUGINS_DIR = ROOT / "plugins"
MARKETPLACE_PATH = ROOT / ".grok-plugin" / "marketplace.json"
INDEX_PATH = ROOT / ".grok-plugin" / "plugin-index.json"

DEFAULT_COPY = [
    {"from": "skills", "to": "skills"},
    {"from": ".claude-plugin/plugin.json", "to": "plugin.json"},
    {"from": ".grok-plugin/plugin.json", "to": "plugin.json"},
    {"from": "LICENSE", "to": "LICENSE"},
]

SKIP_NAMES = {".DS_Store", "__pycache__", ".git"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_DESC = 120
CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def load_sources() -> dict:
    return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))


def parse_local_map(raw: str | None) -> dict[str, Path]:
    if not raw:
        return {}
    out: dict[str, Path] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise SystemExit(f"--local-map entry must be name=/path, got {part!r}")
        name, path = part.split("=", 1)
        out[name.strip()] = Path(path).expanduser().resolve()
    return out


def run_git(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()


def clone_source(repo: str, ref: str, dest: Path) -> str:
    url = f"https://github.com/{repo}.git"
    run_git(["clone", "--quiet", "--depth", "1", "--branch", ref, "--", url, str(dest)])
    sha = run_git(["rev-parse", "HEAD"], cwd=dest)
    if not SHA_RE.match(sha):
        raise RuntimeError(f"{repo}: unexpected sha {sha!r}")
    return sha


def local_sha(path: Path) -> str:
    sha = run_git(["rev-parse", "HEAD"], cwd=path)
    if not SHA_RE.match(sha):
        raise RuntimeError(f"{path}: unexpected sha {sha!r}")
    return sha


def copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        src,
        dest,
        ignore=shutil.ignore_patterns(*SKIP_NAMES),
        dirs_exist_ok=False,
    )


def copy_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def copy_payload(src_root: Path, dest_root: Path, copy_rules: list[dict]) -> list[str]:
    """Copy listed paths. Later rules for the same `to` only apply if dest missing."""
    copied: list[str] = []
    for rule in copy_rules:
        src = src_root / rule["from"]
        dest = dest_root / rule["to"]
        if not src.exists():
            continue
        if dest.exists() and rule["to"] in copied:
            continue
        if src.is_dir():
            copy_tree(src, dest)
        else:
            copy_file(src, dest)
        copied.append(rule["to"])
    return copied


def clean_plugin_dir(dest_root: Path) -> None:
    if dest_root.exists():
        shutil.rmtree(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)


def parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    i = 1
    while i < len(lines):
        line = lines[i]
        if line.strip() in ("---", "..."):
            break
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, value = m.group(1), m.group(2).strip()
        if re.match(r"^[|>][+-]?$", value):
            block: list[str] = []
            j = i + 1
            while j < len(lines) and (
                lines[j].startswith((" ", "\t")) or not lines[j].strip()
            ):
                if lines[j].strip():
                    block.append(lines[j].strip())
                j += 1
            value = " ".join(block)
            i = j
        else:
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            i += 1
        fields[key] = value
    return fields


def clean_desc(text: str) -> str:
    text = re.sub(r"\s+", " ", CONTROL_CHARS_RE.sub("", text)).strip()
    if len(text) > MAX_DESC:
        text = text[: MAX_DESC - 1].rstrip() + "…"
    return text


def extract_skills(plugin_dir: Path) -> list[dict[str, str]]:
    skills_root = plugin_dir / "skills"
    if not skills_root.is_dir():
        return []
    items: list[dict[str, str]] = []
    for skill_md in sorted(skills_root.glob("*/SKILL.md")):
        fm = parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
        name = fm.get("name") or skill_md.parent.name
        desc = fm.get("description") or ""
        items.append({"name": name, "description": clean_desc(desc)})
    return items


def load_plugin_manifest(plugin_dir: Path) -> dict:
    path = plugin_dir / "plugin.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def render_marketplace(cfg: dict) -> dict:
    plugins_out: list[dict] = []
    for entry in cfg.get("plugins", []):
        name = entry["name"]
        plugin_dir = PLUGINS_DIR / name
        if not (plugin_dir / "skills").is_dir():
            continue
        manifest = load_plugin_manifest(plugin_dir)
        item: dict = {
            "name": name,
            "description": manifest.get("description") or entry.get("description") or "",
            "category": entry.get("category") or "development",
            "source": {"type": "local", "path": f"./plugins/{name}"},
        }
        homepage = entry.get("homepage") or manifest.get("homepage")
        if homepage:
            item["homepage"] = homepage
        if entry.get("keywords"):
            item["keywords"] = entry["keywords"]
        if entry.get("domains"):
            item["domains"] = entry["domains"]
        version = manifest.get("version")
        if version:
            item["version"] = version
        plugins_out.append(item)
    market = cfg.get("marketplace") or {}
    return {
        "name": market.get("name") or "ximing-grok-plugins",
        "description": market.get("description") or "",
        "owner": market.get("owner") or {"name": "ximing"},
        "plugins": plugins_out,
    }


def render_index(cfg: dict) -> dict:
    plugins_out: dict[str, dict] = {}
    for entry in cfg.get("plugins", []):
        name = entry["name"]
        plugin_dir = PLUGINS_DIR / name
        if not (plugin_dir / "skills").is_dir():
            continue
        manifest = load_plugin_manifest(plugin_dir)
        source_meta_path = plugin_dir / "SOURCE.json"
        record: dict = {}
        if source_meta_path.is_file():
            try:
                meta = json.loads(source_meta_path.read_text(encoding="utf-8"))
                sha = meta.get("sha")
                if isinstance(sha, str) and SHA_RE.match(sha):
                    record["sha"] = sha
            except json.JSONDecodeError:
                pass
        if manifest.get("version"):
            record["version"] = manifest["version"]
        components: dict[str, list] = {}
        skills = extract_skills(plugin_dir)
        if skills:
            components["skills"] = skills
        record["components"] = components
        plugins_out[name] = record
    return {
        "version": 1,
        "plugins": {name: plugins_out[name] for name in sorted(plugins_out)},
    }


def existing_sha(dest: Path) -> str | None:
    meta_path = dest / "SOURCE.json"
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    sha = meta.get("sha")
    if isinstance(sha, str) and SHA_RE.match(sha):
        return sha
    return None


def sync_one(
    entry: dict,
    *,
    from_local: Path | None,
) -> str:
    name = entry["name"]
    repo = entry["repo"]
    ref = entry.get("ref") or "master"
    copy_rules = entry.get("copy") or DEFAULT_COPY
    dest = PLUGINS_DIR / name

    if from_local is not None:
        if not from_local.is_dir():
            raise RuntimeError(f"{name}: local path does not exist: {from_local}")
        sha = local_sha(from_local)
        src_root = from_local
        tmp: tempfile.TemporaryDirectory | None = None
    else:
        tmp = tempfile.TemporaryDirectory(prefix=f"grok-plugins-{name}-")
        src_root = Path(tmp.name) / "src"
        sha = clone_source(repo, ref, src_root)

    try:
        if existing_sha(dest) == sha and (dest / "skills").is_dir():
            print(f"{name} already at {sha[:12]}, skip copy")
            return sha
        clean_plugin_dir(dest)
        copied = copy_payload(src_root, dest, copy_rules)
        if "skills" not in copied:
            raise RuntimeError(
                f"{name}: upstream {repo} has no skills/ directory to copy"
            )
        write_json(
            dest / "SOURCE.json",
            {
                "repo": repo,
                "url": f"https://github.com/{repo}.git",
                "ref": ref,
                "sha": sha,
                "synced_at": datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
            },
        )
        return sha
    finally:
        if tmp is not None:
            tmp.cleanup()


def write_catalogs(cfg: dict) -> None:
    write_json(MARKETPLACE_PATH, render_marketplace(cfg))
    write_json(INDEX_PATH, render_index(cfg))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="Sync a single plugin name")
    parser.add_argument(
        "--from-local",
        help="Use this checkout instead of cloning (requires --only)",
    )
    parser.add_argument(
        "--local-map",
        help="Comma-separated name=/path overrides, e.g. rab=/src/rab,csi=/src/csi",
    )
    args = parser.parse_args()

    if args.from_local and not args.only:
        print("ERROR: --from-local requires --only", file=sys.stderr)
        return 2

    cfg = load_sources()
    entries: list[dict] = list(cfg.get("plugins") or [])
    if not entries:
        print("ERROR: sources.json has no plugins", file=sys.stderr)
        return 1

    local_map = parse_local_map(args.local_map)
    if args.only:
        entries = [e for e in entries if e.get("name") == args.only]
        if not entries:
            print(f"ERROR: plugin {args.only!r} not in sources.json", file=sys.stderr)
            return 1

    for entry in entries:
        name = entry["name"]
        local = None
        if args.only and args.from_local:
            local = Path(args.from_local).expanduser().resolve()
        elif name in local_map:
            local = local_map[name]
        sha = sync_one(entry, from_local=local)
        origin = str(local) if local else f"https://github.com/{entry['repo']}.git"
        print(f"synced {name} @ {sha[:12]} from {origin}")

    write_catalogs(cfg)
    print(f"wrote {MARKETPLACE_PATH.relative_to(ROOT)}")
    print(f"wrote {INDEX_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
