---
description: Build or sync the distributed CLAUDE.md tree (root map + nested module files)
argument-hint: "[path] [--dry-run] [--force] [--generic] [--with-rules]"
---

Use the treecode:tree-mapper skill to build or sync the CLAUDE.md tree for this
repository. Arguments: $ARGUMENTS

- A leading path argument limits the sync to that subtree.
- `--dry-run`: present the plan only; write nothing.
- `--force`: regenerate blocks even for unchanged modules.
- `--generic`: disable stack-aware boundary detection (package markers only).
- `--with-rules`: also generate a path-scoped rule per module in
  `.claude/rules/<module>.md` (what to do when editing it), alongside the nested
  CLAUDE.md (what the module is).
