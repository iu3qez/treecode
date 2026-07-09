#!/usr/bin/env bash
# Fail-open cap guard: warn when an edited CLAUDE.md exceeds line caps.
# Never blocks (always exit 0).
set -u
INPUT="$(cat)"
FILE="$(printf '%s' "$INPUT" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("tool_input", {}).get("file_path", ""))
except Exception:
    pass
')"
case "$FILE" in
  */CLAUDE.md|CLAUDE.md) ;;
  *) exit 0 ;;
esac
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/treemap.py" --root "$ROOT" \
  check --cap-only --path "$FILE" --json 2>/dev/null | python3 -c '
import json, sys
try:
    rows = json.load(sys.stdin)["drift"]["cap_violations"]
except Exception:
    rows = []
for r in rows:
    print("treecode cap-guard: " + r["path"] + " — " + r["detail"])
'
exit 0
