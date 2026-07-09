# treecode

Build and maintain a distributed CLAUDE.md tree — a lean root map plus lazy,
per-module nested CLAUDE.md files — so Claude Code starts each session already
knowing your codebase structure instead of re-exploring it.

## Why

Nested `CLAUDE.md` files load **lazily**, only when Claude reads a file in that
subdirectory. A single fat root file loads on **every** session and burns context.
treecode architects the tree the right way: an ~18-line root map that points to
per-module files, each generated inside marker blocks so your hand-written text is
never touched. It **complements** `claude-md-management` (which audits prose quality)
and never duplicates auto memory (which tracks volatile learnings).

## The 7 invariants

1. Real nested CLAUDE.md files in subdirectories (lazy, loaded on access).
2. Never wire the tree with `@path` imports from the root (imports load at launch).
3. Idempotency via marker blocks; text outside markers is human-owned and never touched.
4. Root = map, not listing; the root file stays under 80 lines.
5. Nested = 30–60 descriptive lines; no file listings.
6. Respect `.gitignore` / `.claudeignore`; never write into ignored/generated dirs.
7. The root survives compaction; nested files do not — never assume they are in context.

## Install

```
/plugin marketplace add iu3qez/treecode
/plugin install treecode@iu3qez-tools
```

## Commands

| Command | What it does |
|---------|--------------|
| `/treecode:map-tree [path] [--dry-run] [--force] [--generic] [--with-rules]` | Build or sync the tree. Idempotent. `--dry-run` plans only; `--force` regenerates unchanged modules; `--generic` disables stack-aware detection; `--with-rules` also emits per-module rules. |
| `/treecode:map-drift [path]` | Read-only drift audit. Prints the drift table and exits non-zero when drift exists (CI-friendly). |

## Before / after

A fat root that loads every session:

```
# CLAUDE.md  (200+ lines)
- src/api/app.py — FastAPI app
- src/api/routes/users.py — user routes
- src/api/routes/orders.py — order routes
- ... 190 more lines listing every file ...
```

becomes a lean map plus lazy per-module files:

```
# CLAUDE.md
<!-- BEGIN treecode:map (auto) -->
## Codebase map
- `src/api/`  — HTTP handlers        → src/api/CLAUDE.md
- `src/core/` — domain logic          → src/core/CLAUDE.md
<!-- END treecode:map (auto) -->
```

```
# src/api/CLAUDE.md
<!-- BEGIN treecode (auto) — do not edit inside this block -->
# api — HTTP request handling

Responsibility: routing, validation, serialization. No business logic.
Key abstractions: Router, RequestModel, dependency injection
Depends on: src/core
Used by: (entrypoint)
Gotchas: auth runs in middleware, not per-route.
<!-- END treecode (auto) -->
```

## Configuration

Optional `treemap.config.json` at the repo root (defaults shown):

```json
{
  "caps": { "root": 80, "nested": 60, "hard_max": 200 },
  "boundaries": {
    "min_sources": 3,
    "max_depth": 4,
    "package_markers": ["pyproject.toml", "package.json", "go.mod", "Cargo.toml", "pom.xml"],
    "build_markers": ["CMakeLists.txt", "meson.build"],
    "framework_dirs": ["src/routes", "src/lib", "app/api", "src/app"],
    "monorepo_globs": ["packages/*", "apps/*", "libs/*", "components/*"],
    "subdir_exclude": ["tests", "test", "docs", "doc", "examples", "example", "scripts", "bin"]
  },
  "ignore_globs": ["**/node_modules/**", "**/.venv/**", "**/dist/**", "**/build/**", "**/__pycache__/**"],
  "markers": { "module": "treecode", "root": "treecode:map", "rule": "treecode:rule" },
  "edges": {},
  "generated_language": "en",
  "hooks": { "cap_guard": "warn", "instructions_loaded_log": false },
  "stack_aware": true
}
```

### Module discovery

A directory becomes a module when it (1) contains a package marker, (2) matches a
monorepo glob, or (3) is a framework dir / a populated dir directly under `src/`.
Extra tiers cover layouts the base heuristic misses:

- **Monolithic app** (`pyproject.toml` at the root, code in `backend/`): the root
  `pyproject.toml` is parsed (stdlib `tomllib`) and any declared package directory is
  adopted; as a fallback, when the root has a package marker, populated top-level
  directories are promoted — minus `subdir_exclude` (and `src/` itself).
- **CMake / ESP-IDF / Zephyr**: a directory with a `build_markers` file
  (`CMakeLists.txt`, `meson.build`) becomes a module when the repo root has the same
  build file — so each `components/*` and `main/` is detected out of the box.
  `components/*` is also a default monorepo glob.

`--generic` disables all stack-aware tiers (package markers only).

### Dependency graph and its limits

`depends_on` / `used_by` are derived from **static analysis**: Python `ast`, JS/TS
import regex, and — for CMake / ESP-IDF — the `REQUIRES` / `PRIV_REQUIRES` of
`idf_component_register()` and the deps of `target_link_libraries()` (the authoritative
component-dependency declaration, mapped by directory basename). This still cannot see a
dependency that only exists at runtime — a frontend that calls a backend over REST
imports nothing from it, so no edge is inferred. Declare such edges once and the scan
merges them into the graph (and thus into every regenerated CLAUDE.md):

```json
{ "edges": { "frontend": ["backend"] } }
```

Unknown endpoints are ignored; declared edges are deduped against import-derived ones.

## Per-module rules (`--with-rules`)

The nested CLAUDE.md says *what* a module is. A **rule** says *how* to touch it —
recurring do/don't directives for edits. `/treecode:map-tree --with-rules` also
generates a path-scoped `.claude/rules/<module>.md` per module, marker-delimited and
idempotent just like the CLAUDE.md blocks. Off by default.

## Parallel exploration

On repos with many modules, the `tree-mapper` skill dispatches one
`module-cartographer` subagent per module — a read-only explorer that reads that
module's sources in an isolated context and returns its compiled template, so the main
session's context never fills up with every module's internals. For one or two modules
it just works inline.

## How generated content stays safe

- All generated text lives inside marker blocks. Anything outside a marker is yours
  and is never modified.
- treecode never auto-commits — it writes files, prints what changed, and suggests a
  commit. You stay in control.
- Drift detection is report-only: it never deletes or moves files, only tells you what
  diverged and what it suggests.
- The `cap_guard` hook warns (never blocks) when a CLAUDE.md grows past its line cap.

## License

MIT — see [LICENSE](LICENSE).
