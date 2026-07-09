# treecode — project memory

Claude Code plugin that builds a distributed CLAUDE.md tree (lean root map + lazy
per-module nested files). This file is dev memory for working ON treecode; it is not
a plugin component (the plugin loader ignores a CLAUDE.md at the plugin root — PRD §12).

## Where things are

- `scripts/treemap.py` — the deterministic engine (stdlib only). All mechanical work:
  file walk, boundary detection, dependency graph, marker I/O, caps, drift.
- `skills/tree-mapper/SKILL.md` — the semantic orchestrator the model follows.
- `agents/module-cartographer.md` — read-only per-module explorer, forked in parallel.
- `commands/` — `/treecode:map-tree`, `/treecode:map-drift`.
- `hooks/` — fail-open cap-guard + opt-in InstructionsLoaded logger.
- `tests/` — `unittest` suite; `helpers.py` builds throwaway repos in temp dirs.
- `.claude-plugin/` — `plugin.json` + `marketplace.json` (keep versions in sync).
- `docs/` — PRD (Italian, internal spec) + superpowers specs/plans.

## Commands

- Run tests: `python3 -m unittest discover -s tests`
- One module: `python3 -m unittest tests.test_check -v`
- Validate the plugin: `claude plugin validate .`
- Try the engine: `python3 scripts/treemap.py --root <repo> scan --json`

## Architecture

Deterministic (`treemap.py`) vs semantic (skill) is the core split: the script never
guesses meaning, the model never writes files directly (always via `write-block`).
Subcommands: `scan`, `check`, `write-block`, `read-block`. Exit codes: 0 OK, 1
drift/cap findings (`check`), 2 usage/integrity error.

## Invariants (do not break)

1. Nested CLAUDE.md files are real files in subdirs (lazy). Never wire the tree with
   `@path` imports (they load at launch).
2. Generated content lives inside marker blocks; text outside is human-owned.
3. Idempotent: re-running produces zero diff. Root ≤ 80 lines, nested 30–60.
4. Respect `.gitignore`/`.claudeignore`; never touch ignored dirs. Never auto-commit.

## Gotchas

- **stdlib only** in `treemap.py` — no `pip install`, ever. `tests/test_acceptance.py`
  enforces it against `sys.stdlib_module_names`.
- Marker lines are exact strings; detection keys off the `<!-- BEGIN <name> ` /
  `<!-- END <name> ` prefixes, so the em-dash suffix is not load-bearing. Corrupted or
  duplicated markers → exit 2, never guess.
- Rename detection is stateless: it pairs an orphan block with the closest-matching
  detected-module block (≥60% via `difflib`), not new↔orphan (a new module has no block
  to compare).
- Dependency graph is static-analysis only; runtime/REST deps must be declared via
  `edges` in `treemap.config.json`.
- Bump `version` in BOTH `plugin.json` and `marketplace.json` together, and update
  `tests/test_manifests.py`.
