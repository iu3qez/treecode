---
name: tree-mapper
description: Build and sync a distributed CLAUDE.md tree — lean root map plus lazy per-module nested files. Use when asked to map the codebase tree, generate module CLAUDE.md files, or sync/repair the codebase map.
---

# Tree Mapper

Generate and maintain a distributed CLAUDE.md tree: a lean root map (< 80 lines)
plus one nested CLAUDE.md per module (30–60 lines), all generated content inside
marker blocks. The deterministic engine is `${CLAUDE_PLUGIN_ROOT}/scripts/treemap.py`;
you only fill the semantic fields and always write through it.

## Hard rules

- Never write `@path` imports to wire the tree — imports load at launch and defeat
  lazy loading. Nested files in subdirectories are the only mechanism.
- Never edit CLAUDE.md files directly; always go through `treemap.py write-block`.
  Text outside marker blocks is human-owned.
- Never commit. Report the modified files and suggest a commit.
- Root map = where things are + pointers. No file listings anywhere.

## Workflow

1. **Scan.** Run:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/treemap.py" --root <repo> scan --json`
   (add `--generic` if the user passed it). Read modules, `block_present`,
   `over_cap`, and the current root map.
2. **Plan.** List modules to create/update with counts. If more than 15 files would
   be touched, present the plan and ask for confirmation first. With `--dry-run`,
   stop here. Without `--force`, skip modules whose block is present and whose
   sources are unchanged since the block content still describes them.
3. **Per module:** read the key sources (entrypoints, largest files, exports), then
   fill this template — semantic fields only, in the config's `generated_language`:

   ```markdown
   # <module-name> — <one-line purpose>

   Responsibility: <what this module owns; what it must NOT do>
   Key abstractions: <classes/interfaces/entrypoints that matter>
   Depends on: <from scan depends_on>
   Used by: <from scan used_by>
   External deps of note: <libs with non-obvious usage>
   Conventions: <module-local rules>
   Gotchas: <non-obvious behaviors, footguns>
   ```

   Aim for the **middle of the 30–60 line range** — the caps are maxima, not
   targets. A 20-line nested file is under-documented: prefer substance
   (real gotchas, non-obvious conventions, why decisions were made) over
   brevity. Fill `Depends on:`/`Used by:` from the scan's `depends_on`/`used_by`
   (which now include any config-declared `edges`), not from guesswork. Zero
   file listings. Write it with:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/treemap.py" --root <repo> write-block --path <module-dir> --content-file <tmp>`
4. **Root map.** Build the map body (one line per module:
   `` - `src/api/`  — HTTP handlers  → src/api/CLAUDE.md ``) and write it with
   `write-block --path . --kind root-map`.
5. **Verify.** Run `treemap.py --root <repo> check`. Report: files written, caps OK,
   residual drift.
6. **Hand off.** Never commit. Print the modified-file set and suggest a commit
   message.

## Error handling

- `write-block` exit 2 (corrupted/duplicated markers): stop for that file, report it,
  ask the user to fix the markers manually. Never guess.
- Cap warnings from `write-block`: shorten the block body and rewrite.
- Orphan/renamed drift from `check`: report with the suggested action; never delete
  files yourself.
