---
description: Audit drift between the documented CLAUDE.md map and the real tree (read-only, CI-friendly)
argument-hint: "[path]"
---

Run the treecode drift audit — read-only, never write anything:

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/treemap.py" --root <repo-root> check`

Print the drift table exactly as the tool reports it (columns: type, path, detail,
suggested-action) and state the exit code. Exit code 1 means drift exists: summarize
which buckets fired and what the suggested actions are. Do not fix anything unless
the user asks. Arguments: $ARGUMENTS
