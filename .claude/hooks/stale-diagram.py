"""PostToolUse hook: a diagram source changed, so its SVG is now stale.

Reads the hook payload on stdin and prints a systemMessage only when the
edited file is one of ``docs/src/*.json``. It is a script rather than a
one-liner because ``jq`` is not installed here -- found by pipe-testing the
command rather than assuming it.
"""

import json
import os
import sys

try:
    payload = json.load(sys.stdin)
except Exception:  # noqa: BLE001 - a hook must not fail a tool call
    sys.exit(0)

path = (
    (payload.get("tool_input") or {}).get("file_path")
    or (payload.get("tool_response") or {}).get("filePath")
    or ""
)

# Normalise separators, then match on the last two directory segments. A
# leading-slash test like `"/docs/src/" in path` looks right and fails on a
# repo-relative path such as "docs/src/state.json".
parts = path.replace("\\", "/").split("/")
is_diagram_source = (
    len(parts) >= 3
    and parts[-2] == "src"
    and parts[-3] == "docs"
    and parts[-1].endswith(".json")
)

if is_diagram_source:
    print(json.dumps({
        "systemMessage": (
            f"{os.path.basename(path)} changed -- the SVG generated from it "
            "is now stale. Re-render with /redraw-diagrams before "
            "committing; a JSON that disagrees with its SVG has happened "
            "here before."
        )
    }))
