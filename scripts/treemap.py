#!/usr/bin/env python3
"""treemap.py — deterministic engine for the treecode plugin.

Stdlib only (Python 3.11+). Subcommands: scan, check, write-block, read-block.
Exit codes: 0 OK, 1 drift/cap findings (check), 2 usage/integrity error.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULTS = {
    "caps": {"root": 80, "nested": 60, "hard_max": 200},
    "boundaries": {
        "min_sources": 3,
        "max_depth": 4,
        "package_markers": ["pyproject.toml", "package.json", "go.mod", "Cargo.toml", "pom.xml"],
        "framework_dirs": ["src/routes", "src/lib", "app/api", "src/app"],
        "monorepo_globs": ["packages/*", "apps/*", "libs/*"],
    },
    "ignore_globs": ["**/node_modules/**", "**/.venv/**", "**/dist/**",
                     "**/build/**", "**/__pycache__/**"],
    "markers": {"module": "treecode", "root": "treecode:map"},
    "generated_language": "en",
    "hooks": {"cap_guard": "warn", "instructions_loaded_log": False},
    "stack_aware": True,
}


class UsageError(Exception):
    """Bad invocation or unreadable config — exit 2."""


def deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            out[key] = deep_merge(base[key], value)
        else:
            out[key] = value
    return out


def load_config(root: Path) -> dict:
    path = root / "treemap.config.json"
    if not path.is_file():
        return deep_merge(DEFAULTS, {})
    try:
        user = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UsageError(f"cannot read {path}: {exc}") from exc
    if not isinstance(user, dict):
        raise UsageError(f"{path}: top-level value must be an object")
    return deep_merge(DEFAULTS, user)


class MarkerError(Exception):
    """Corrupted or duplicated marker block — refuse to write, exit 2."""


def begin_line(name: str, kind: str) -> str:
    if kind == "module":
        return f"<!-- BEGIN {name} (auto) — do not edit inside this block -->"
    return f"<!-- BEGIN {name} (auto) -->"


def end_line(name: str) -> str:
    return f"<!-- END {name} (auto) -->"


def find_block(text: str, name: str) -> tuple[int, int] | None:
    """Return (begin_idx, end_idx) line indices, None if absent.

    Matches on the `<!-- BEGIN <name> ` / `<!-- END <name> ` prefixes so the
    em-dash suffix is not load-bearing. Raises MarkerError on imbalance or
    duplicate blocks.
    """
    begins, ends = [], []
    for i, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if stripped.startswith(f"<!-- BEGIN {name} "):
            begins.append(i)
        elif stripped.startswith(f"<!-- END {name} "):
            ends.append(i)
    if not begins and not ends:
        return None
    if len(begins) != 1 or len(ends) != 1 or ends[0] < begins[0]:
        raise MarkerError(f"corrupted or duplicated '{name}' marker block")
    return begins[0], ends[0]


def read_block_body(text: str, name: str) -> str | None:
    span = find_block(text, name)
    if span is None:
        return None
    lines = text.splitlines()
    return "\n".join(lines[span[0] + 1:span[1]])


def replace_block(text: str, name: str, kind: str, body: str) -> str:
    block = [begin_line(name, kind), *body.strip("\n").splitlines(), end_line(name)]
    lines = text.splitlines()
    span = find_block(text, name)
    if span is None:
        if text.strip():
            new = lines + [""] + block          # append after human text
        else:
            new = block                          # fresh file: block only
    else:
        new = lines[:span[0]] + block + lines[span[1] + 1:]
    return "\n".join(new) + "\n"


def match_any(rel: str, patterns: list[str]) -> bool:
    for pat in patterns:
        candidates = {pat}
        if pat.startswith("**/"):
            candidates.add(pat[3:])            # also match at repo top level
        if pat.endswith("/"):
            candidates = {c + "**" for c in candidates} | {c + "*" for c in candidates}
        if any(fnmatch.fnmatch(rel, c) for c in candidates):
            return True
    return False


def _read_pattern_file(path: Path) -> list[str]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def _git_files(root: Path) -> list[Path] | None:
    if not (root / ".git").exists():
        return None
    try:
        res = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=root, capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if res.returncode != 0:
        return None
    return [Path(line) for line in res.stdout.splitlines() if line]


def _walk_files(root: Path, gitignore: list[str]) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        dirnames[:] = [
            d for d in dirnames
            if d != ".git"
            and not match_any((rel_dir / d).as_posix(), gitignore)
            and not match_any((rel_dir / d).as_posix() + "/", gitignore)
        ]
        for fname in filenames:
            rel = (rel_dir / fname).as_posix().removeprefix("./")
            if not match_any(rel, gitignore):
                out.append(Path(rel))
    return out


def list_files(root: Path, cfg: dict) -> list[Path]:
    files = _git_files(root)
    if files is None:
        files = _walk_files(root, _read_pattern_file(root / ".gitignore"))
    claudeignore = _read_pattern_file(root / ".claudeignore")
    extra = list(cfg["ignore_globs"]) + claudeignore
    kept = []
    for rel in files:
        if match_any(rel.as_posix(), extra):
            continue
        abs_path = root / rel
        try:
            if not abs_path.resolve().is_relative_to(root):
                continue                       # symlink escaping the repo
        except OSError:
            continue
        if abs_path.is_file():
            kept.append(rel)
    return sorted(kept)


def cmd_scan(args, cfg: dict) -> int:
    return 0  # implemented in Task 7


def cmd_check(args, cfg: dict) -> int:
    return 0  # implemented in Task 8


def _marker_name(cfg: dict, kind: str) -> str:
    return cfg["markers"]["root"] if kind == "root-map" else cfg["markers"]["module"]


def _cap_for(cfg: dict, target: Path, root: Path) -> int:
    return cfg["caps"]["root"] if target.parent == root else cfg["caps"]["nested"]


def cmd_write_block(args, cfg: dict) -> int:
    root: Path = args.root_path
    target = (root / args.path / "CLAUDE.md").resolve()
    if not target.is_relative_to(root):
        raise UsageError(f"--path escapes the repo root: {args.path}")
    if args.content_file:
        body = Path(args.content_file).read_text(encoding="utf-8")
    else:
        body = sys.stdin.read()
    name = _marker_name(cfg, args.kind)
    old = target.read_text(encoding="utf-8") if target.is_file() else ""
    try:
        new = replace_block(old, name, args.kind, body)
    except MarkerError as exc:
        print(f"error: {target}: {exc}", file=sys.stderr)
        return 2
    if new != old:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new, encoding="utf-8")
    lines = new.count("\n")
    cap = _cap_for(cfg, target, root)
    if lines > cap:
        print(f"warning: {target} is {lines} lines (cap {cap})", file=sys.stderr)
    return 0


def cmd_read_block(args, cfg: dict) -> int:
    root: Path = args.root_path
    target = root / args.path / "CLAUDE.md"
    if not target.is_file():
        return 0
    try:
        body = read_block_body(target.read_text(encoding="utf-8"),
                               _marker_name(cfg, args.kind))
    except MarkerError as exc:
        print(f"error: {target}: {exc}", file=sys.stderr)
        return 2
    if body is not None:
        print(body)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="treemap.py", description=__doc__)
    parser.add_argument("--root", default=".", help="target repo root (default: cwd)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="discover modules and their status")
    p_scan.add_argument("--json", action="store_true")
    p_scan.add_argument("--generic", action="store_true",
                        help="disable stack-aware detection")
    p_scan.set_defaults(func=cmd_scan)

    p_check = sub.add_parser("check", help="report drift and cap violations")
    p_check.add_argument("--json", action="store_true")
    p_check.add_argument("--cap-only", action="store_true")
    p_check.add_argument("--path", help="restrict cap check to one file")
    p_check.set_defaults(func=cmd_check)

    p_write = sub.add_parser("write-block", help="idempotently write a marker block")
    p_write.add_argument("--path", required=True, help="module dir (or . for root map)")
    p_write.add_argument("--kind", choices=["module", "root-map"], default="module")
    p_write.add_argument("--content-file", help="block body file (default: stdin)")
    p_write.set_defaults(func=cmd_write_block)

    p_read = sub.add_parser("read-block", help="print the current block body")
    p_read.add_argument("--path", default=".")
    p_read.add_argument("--kind", choices=["module", "root-map"], default="module")
    p_read.set_defaults(func=cmd_read_block)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = Path(args.root).resolve()
        if not root.is_dir():
            raise UsageError(f"--root {args.root}: not a directory")
        cfg = load_config(root)
        args.root_path = root
        return args.func(args, cfg)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
