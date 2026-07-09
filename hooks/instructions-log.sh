#!/usr/bin/env bash
# Optional InstructionsLoaded logger. No-op unless enabled in treemap.config.json.
set -u
TREECODE_HOOK_INPUT="$(cat)"
export TREECODE_HOOK_INPUT
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
python3 - "$ROOT" <<'PY'
import datetime, json, os, sys
from pathlib import Path
root = Path(sys.argv[1])
cfg_path = root / "treemap.config.json"
enabled = False
try:
    enabled = bool(json.loads(cfg_path.read_text())
                   .get("hooks", {}).get("instructions_loaded_log", False))
except Exception:
    pass
if not enabled:
    sys.exit(0)
try:
    data = json.loads(os.environ.get("TREECODE_HOOK_INPUT", ""))
except Exception:
    data = {}
log = root / ".claude" / "treecode-instructions.log"
log.parent.mkdir(parents=True, exist_ok=True)
stamp = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
with log.open("a", encoding="utf-8") as fh:
    fh.write(f"{stamp} {data.get('load_reason', '?')} {data.get('file_path', '?')}\n")
PY
exit 0
