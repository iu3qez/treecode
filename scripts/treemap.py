#!/usr/bin/env python3
"""treemap.py — deterministic engine for the treecode plugin.

Stdlib only (Python 3.11+). Subcommands: scan, check, write-block, read-block.
Exit codes: 0 OK, 1 drift/cap findings (check), 2 usage/integrity error.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import fnmatch
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULTS = {
    "caps": {"root": 80, "nested": 60, "hard_max": 200},
    "boundaries": {
        "min_sources": 3,
        "max_depth": 4,
        "package_markers": ["pyproject.toml", "package.json", "go.mod", "Cargo.toml", "pom.xml"],
        "build_markers": ["CMakeLists.txt", "meson.build"],
        "framework_dirs": ["src/routes", "src/lib", "app/api", "src/app"],
        "monorepo_globs": ["packages/*", "apps/*", "libs/*", "components/*"],
        "subdir_exclude": ["tests", "test", "docs", "doc", "examples",
                           "example", "scripts", "bin"],
    },
    "ignore_globs": ["**/node_modules/**", "**/.venv/**", "**/dist/**",
                     "**/build/**", "**/__pycache__/**"],
    "markers": {"module": "treecode", "root": "treecode:map", "rule": "treecode:rule"},
    "edges": {},
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
    if kind in ("module", "rule"):
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


SOURCE_EXTS = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx", ".svelte", ".go", ".rs", ".java",
    ".rb", ".php", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".kt", ".swift",
})


@dataclass
class Module:
    path: str
    kind: str
    source_count: int = 0
    depends_on: list[str] = field(default_factory=list)
    used_by: list[str] = field(default_factory=list)


def _subtree_sources(files: list[Path]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in files:
        if f.suffix not in SOURCE_EXTS:
            continue
        for parent in f.parents:
            if parent == Path("."):
                break
            counts[parent.as_posix()] = counts.get(parent.as_posix(), 0) + 1
    return counts


def _declared_package_dirs(root: Path) -> set[str]:
    """Best-effort: top-level dirs a root pyproject.toml declares as packages.

    Reads the common setuptools/poetry/hatch keys via stdlib tomllib. Returns
    only the first path segment of each declared package that exists on disk.
    """
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return set()
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return set()
    tool = data.get("tool", {}) if isinstance(data.get("tool"), dict) else {}
    names: list[str] = []
    # poetry: packages = [{ include = "svc" }, ...]
    for entry in _dig(tool, "poetry", "packages") or []:
        if isinstance(entry, dict) and isinstance(entry.get("include"), str):
            names.append(entry["include"])
    # setuptools: packages = ["myapp", ...]  /  package-dir = {"": "src"}
    for entry in _dig(tool, "setuptools", "packages") or []:
        if isinstance(entry, str):
            names.append(entry)
    pkg_dir = _dig(tool, "setuptools", "package-dir")
    if isinstance(pkg_dir, dict):
        names += [v for v in pkg_dir.values() if isinstance(v, str)]
    # hatch: [tool.hatch.build.targets.wheel] packages = ["backend"]
    for entry in _dig(tool, "hatch", "build", "targets", "wheel", "packages") or []:
        if isinstance(entry, str):
            names.append(entry)
    out = set()
    for name in names:
        top = name.replace(".", "/").split("/")[0].strip("/")
        if top and (root / top).is_dir():
            out.add(top)
    return out


def _dig(data, *keys):
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def find_modules(root: Path, files: list[Path], cfg: dict,
                 stack_aware: bool | None = None) -> list[Module]:
    if stack_aware is None:
        stack_aware = cfg["stack_aware"]
    bounds = cfg["boundaries"]
    sources = _subtree_sources(files)
    candidates: dict[str, str] = {}
    has_root_marker = any(
        f.parent == Path(".") and f.name in bounds["package_markers"]
        for f in files)
    build_markers = bounds.get("build_markers", [])
    exclude = set(bounds.get("subdir_exclude", []))
    # build markers (CMakeLists.txt, meson.build) only count when the same file
    # sits at the repo root — the signal that this is a build-system-rooted
    # project (e.g. CMake/ESP-IDF), where each per-dir build file is a component.
    root_builds = {f.name for f in files
                   if f.parent == Path(".") and f.name in build_markers}

    # 1. package markers (highest priority)
    for f in files:
        parent = f.parent.as_posix()
        if parent == ".":
            continue
        if f.name in bounds["package_markers"]:
            candidates[parent] = "package"
        elif f.name in root_builds and not (set(parent.split("/")) & exclude):
            candidates.setdefault(parent, "package")

    # 1b. root manifest declares a package dir in a subdirectory (Tier A)
    for d in _declared_package_dirs(root):
        candidates.setdefault(d, "package")

    # 2. monorepo globs
    for d in sources:
        if d not in candidates and match_any(d, bounds["monorepo_globs"]):
            candidates[d] = "monorepo-member"

    # 3. framework dirs + populated children of any src/ dir
    if stack_aware:
        for d in sources:
            if d in candidates:
                continue
            parts = d.split("/")
            is_framework = match_any(d, bounds["framework_dirs"]) or \
                d in bounds["framework_dirs"]
            # only *top-level* src children are modules; a deep <pkg>/src/<x> is
            # an internal source folder, not a module boundary.
            is_src_child = len(parts) == 2 and parts[0] == "src"
            if is_framework or is_src_child:
                candidates[d] = "framework-dir"

    # 3b. fallback: a repo with a root package marker but code parked in a
    # top-level subdir (e.g. backend/) — the de-facto monolithic-app layout.
    # Promote populated top-level dirs, minus the common non-module ones.
    if stack_aware and has_root_marker:
        exclude = set(bounds.get("subdir_exclude", [])) | {"src"}
        for d in sources:
            if d in candidates or "/" in d or d in exclude or d.startswith("."):
                continue
            if sources.get(d, 0) < bounds["min_sources"]:
                continue
            if any(c.startswith(d + "/") for c in candidates):
                continue                          # contains an already-found module
            candidates[d] = "framework-dir"

    # 4. merge: non-package candidates below min_sources collapse away
    # 5. depth cap
    # 6. absorption into ancestor candidates (packages resist absorption)
    selected: dict[str, str] = {}
    for d, kind in sorted(candidates.items()):
        if kind != "package" and sources.get(d, 0) < bounds["min_sources"]:
            continue
        if len(d.split("/")) > bounds["max_depth"]:
            continue
        ancestor = next((a for a in selected
                         if d != a and d.startswith(a + "/")), None)
        if ancestor is not None and kind != "package":
            continue
        selected[d] = kind

    return [Module(path=d, kind=kind, source_count=sources.get(d, 0))
            for d, kind in sorted(selected.items())]


_JS_IMPORT_RE = re.compile(
    r"""(?:import\s[^'"]*?from\s*|import\s*\(\s*|require\s*\(\s*)['"]([^'"]+)['"]""")
_JS_EXTS = {".ts", ".tsx", ".js", ".jsx", ".svelte"}


def _owner(rel: str, module_paths: list[str]) -> str | None:
    best = None
    for m in module_paths:
        if rel == m or rel.startswith(m + "/"):
            if best is None or len(m) > len(best):
                best = m
    return best


def build_dep_graph(root: Path, modules: list[Module], files: list[Path],
                    cfg: dict | None = None) -> None:
    root_abs = root.resolve()
    paths = [m.path for m in modules]
    path_set = set(paths)
    edges: set[tuple[str, str]] = set()

    # runtime/network deps that static import analysis can't see (e.g. a
    # frontend calling the backend over REST) — declared once in the config.
    if cfg:
        for src, dsts in (cfg.get("edges") or {}).items():
            if src not in path_set:
                continue
            for dst in dsts:
                if dst in path_set and dst != src:
                    edges.add((src, dst))
    for f in files:
        src_mod = _owner(f.as_posix(), paths)
        if src_mod is None:
            continue
        targets: list[str] = []
        try:
            text = (root / f).read_text(encoding="utf-8", errors="replace")
            if f.suffix == ".py":
                tree = ast.parse(text)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        targets += [a.name.replace(".", "/") for a in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        targets.append(node.module.replace(".", "/"))
            elif f.suffix in _JS_EXTS:
                for spec in _JS_IMPORT_RE.findall(text):
                    if not spec.startswith("."):
                        continue
                    resolved = (root / f.parent / spec).resolve()
                    if resolved.is_relative_to(root_abs):
                        targets.append(resolved.relative_to(root_abs).as_posix())
        except (SyntaxError, ValueError, OSError):
            continue                              # best-effort: skip file
        for rel_t in targets:
            dst_mod = _owner(rel_t, paths)
            if dst_mod and dst_mod != src_mod:
                edges.add((src_mod, dst_mod))
    by_path = {m.path: m for m in modules}
    for src, dst in sorted(edges):
        by_path[src].depends_on.append(dst)
        by_path[dst].used_by.append(src)


_MAP_ENTRY_RE = re.compile(r"^\s*-\s*`(?P<path>[^`]+?)/?`.*?→\s*(?P<pointer>\S+CLAUDE\.md)\s*$")


def parse_root_map(body: str) -> list[dict]:
    entries = []
    for line in body.splitlines():
        m = _MAP_ENTRY_RE.match(line)
        if m:
            entries.append({"path": m.group("path").rstrip("/"),
                            "pointer": m.group("pointer")})
    return entries


def scan_data(root: Path, cfg: dict, stack_aware: bool | None = None) -> dict:
    files = list_files(root, cfg)
    modules = find_modules(root, files, cfg, stack_aware=stack_aware)
    build_dep_graph(root, modules, files, cfg)
    caps = cfg["caps"]
    mod_marker = cfg["markers"]["module"]
    out_modules = []
    for m in modules:
        claude = root / m.path / "CLAUDE.md"
        block_present = has_manual = over_cap = False
        if claude.is_file():
            text = claude.read_text(encoding="utf-8")
            try:
                body = read_block_body(text, mod_marker)
                span = find_block(text, mod_marker) if body is not None else None
            except MarkerError as exc:
                raise MarkerError(f"{claude}: {exc}") from exc
            block_present = body is not None
            outside = text
            if span is not None:
                lines = text.splitlines()
                outside = "\n".join(lines[:span[0]] + lines[span[1] + 1:])
            has_manual = bool(outside.strip())
            n = text.count("\n")
            over_cap = n > caps["nested"] or n > caps["hard_max"]
        out_modules.append({**asdict(m), "has_manual_content": has_manual,
                            "block_present": block_present, "over_cap": over_cap})
    root_claude = root / "CLAUDE.md"
    root_map = {"present": False, "entries": []}
    if root_claude.is_file():
        try:
            body = read_block_body(root_claude.read_text(encoding="utf-8"),
                                   cfg["markers"]["root"])
        except MarkerError as exc:
            raise MarkerError(f"{root_claude}: {exc}") from exc
        if body is not None:
            root_map = {"present": True, "entries": parse_root_map(body)}
    ignored = sorted({g for g in cfg["ignore_globs"]})
    return {"root": str(root), "modules": out_modules,
            "root_map": root_map, "ignored": ignored}


def cmd_scan(args, cfg: dict) -> int:
    try:
        data = scan_data(args.root_path, cfg,
                         stack_aware=False if args.generic else None)
    except MarkerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        for m in data["modules"]:
            state = "block" if m["block_present"] else "no block"
            print(f"{m['path']:<40} {m['kind']:<16} {m['source_count']:>4} src  [{state}]")
        print(f"{len(data['modules'])} module(s) detected")
    return 0


def _cap_violations(root: Path, cfg: dict, only: str | None = None) -> list[dict]:
    caps = cfg["caps"]
    out = []
    if only:
        p = Path(only)
        targets = [p if p.is_absolute() else root / p]
    else:
        targets = [root / f for f in list_files(root, cfg) if f.name == "CLAUDE.md"]
        root_claude = root / "CLAUDE.md"
        if root_claude.is_file() and root_claude not in targets:
            targets.append(root_claude)
    for t in targets:
        if not t.is_file():
            continue
        n = t.read_text(encoding="utf-8").count("\n")
        cap = caps["root"] if t.parent == root else caps["nested"]
        cap = min(cap, caps["hard_max"])
        if n > cap:
            rel = t.relative_to(root).as_posix() if t.is_relative_to(root) else str(t)
            out.append({"path": rel, "detail": f"{n} lines (cap {cap})",
                        "suggested_action": "shorten the file or raise caps in treemap.config.json"})
    return out


def compute_drift(root: Path, cfg: dict, cap_only: bool = False,
                  only_path: str | None = None) -> dict:
    empty = {"new": [], "renamed": [], "removed": [], "dead_pointers": [],
             "orphan_nested": [], "cap_violations": []}
    if cap_only:
        empty["cap_violations"] = _cap_violations(root, cfg, only=only_path)
        return {"drift": empty}
    data = scan_data(root, cfg)
    detected = {m["path"] for m in data["modules"]}
    mod_marker = cfg["markers"]["module"]

    with_block: dict[str, str] = {}          # dir -> block body
    for f in list_files(root, cfg):
        if f.name != "CLAUDE.md" or f.parent == Path("."):
            continue
        body = read_block_body((root / f).read_text(encoding="utf-8"), mod_marker)
        if body is not None:
            with_block[f.parent.as_posix()] = body

    new = sorted(detected - set(with_block))
    orphans = sorted(set(with_block) - detected)
    detected_with_block = {d: with_block[d] for d in detected if d in with_block}

    # rename: pair an orphan block with the detected module whose block content
    # is the closest match (>= 60%). Paired orphans leave the orphan bucket.
    renamed = []
    for old in list(orphans):
        best, best_ratio = None, 0.0
        for cand, cbody in detected_with_block.items():
            ratio = difflib.SequenceMatcher(None, with_block[old], cbody).ratio()
            if ratio > best_ratio:
                best, best_ratio = cand, ratio
        if best and best_ratio >= 0.6:
            renamed.append({"path": old, "from": old, "to": best,
                            "detail": f"content match {best_ratio:.0%}",
                            "suggested_action": f"move {old}/CLAUDE.md content into {best}/CLAUDE.md and remove {old}/CLAUDE.md"})
            orphans.remove(old)

    rename_targets = {r["to"] for r in renamed}
    dead, removed = [], []
    for entry in data["root_map"]["entries"]:
        if not (root / entry["pointer"]).is_file():
            dead.append({"path": entry["path"],
                         "detail": f"map points to missing {entry['pointer']}",
                         "suggested_action": "remove the entry or regenerate the map"})
        if entry["path"] not in detected and entry["path"] not in rename_targets:
            removed.append({"path": entry["path"],
                            "detail": "mapped module no longer detected",
                            "suggested_action": "regenerate the root map"})

    drift = {
        "new": [{"path": p, "detail": "module without nested CLAUDE.md block",
                 "suggested_action": "run /treecode:map-tree"} for p in new],
        "renamed": renamed,
        "removed": removed,
        "dead_pointers": dead,
        "orphan_nested": [{"path": p, "detail": "nested block but no module detected",
                           "suggested_action": f"review and remove {p}/CLAUDE.md manually"}
                          for p in orphans],
        "cap_violations": _cap_violations(root, cfg),
    }
    return {"drift": drift}


def cmd_check(args, cfg: dict) -> int:
    try:
        result = compute_drift(args.root_path, cfg, cap_only=args.cap_only,
                               only_path=args.path)
    except MarkerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    drift = result["drift"]
    has_drift = any(drift.values())
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{'type':<14} {'path':<32} {'detail':<40} suggested-action")
        labels = {"new": "new", "renamed": "renamed", "removed": "removed",
                  "dead_pointers": "dead-pointer", "orphan_nested": "orphan",
                  "cap_violations": "cap"}
        for bucket, rows in drift.items():
            for row in rows:
                print(f"{labels[bucket]:<14} {row['path']:<32} {row['detail']:<40} "
                      f"{row['suggested_action']}")
        if not has_drift:
            print("(no drift)")
    return 1 if has_drift else 0


def _marker_name(cfg: dict, kind: str) -> str:
    if kind == "root-map":
        return cfg["markers"]["root"]
    if kind == "rule":
        return cfg["markers"]["rule"]
    return cfg["markers"]["module"]


def _slug(path: str) -> str:
    return path.strip("/").replace("/", "-") or "root"


def _target_file(root: Path, path: str, kind: str) -> Path:
    if kind == "rule":
        return root / ".claude" / "rules" / f"{_slug(path)}.md"
    return root / path / "CLAUDE.md"


def _cap_for(cfg: dict, target: Path, root: Path) -> int:
    return cfg["caps"]["root"] if target.parent == root else cfg["caps"]["nested"]


def cmd_write_block(args, cfg: dict) -> int:
    root: Path = args.root_path
    target = _target_file(root, args.path, args.kind).resolve()
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
    if args.kind != "rule":                      # rules are behavioral, not capped
        lines = new.count("\n")
        cap = _cap_for(cfg, target, root)
        if lines > cap:
            print(f"warning: {target} is {lines} lines (cap {cap})", file=sys.stderr)
    return 0


def cmd_read_block(args, cfg: dict) -> int:
    root: Path = args.root_path
    target = _target_file(root, args.path, args.kind)
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
    p_write.add_argument("--kind", choices=["module", "root-map", "rule"], default="module")
    p_write.add_argument("--content-file", help="block body file (default: stdin)")
    p_write.set_defaults(func=cmd_write_block)

    p_read = sub.add_parser("read-block", help="print the current block body")
    p_read.add_argument("--path", default=".")
    p_read.add_argument("--kind", choices=["module", "root-map", "rule"], default="module")
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
