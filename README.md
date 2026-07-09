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
| `/treecode:map-tree [path] [--dry-run] [--force] [--generic]` | Build or sync the tree. Idempotent. `--dry-run` plans only; `--force` regenerates unchanged modules; `--generic` disables stack-aware detection. |
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
    "framework_dirs": ["src/routes", "src/lib", "app/api", "src/app"],
    "monorepo_globs": ["packages/*", "apps/*", "libs/*"]
  },
  "ignore_globs": ["**/node_modules/**", "**/.venv/**", "**/dist/**", "**/build/**", "**/__pycache__/**"],
  "markers": { "module": "treecode", "root": "treecode:map" },
  "generated_language": "en",
  "hooks": { "cap_guard": "warn", "instructions_loaded_log": false },
  "stack_aware": true
}
```

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
