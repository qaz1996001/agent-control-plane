"""PostToolUse hook: a diagram source changed, so its SVG is now stale.

Reads the hook payload on stdin and prints a systemMessage only when the
edited file is one of docs/src/*.json. jq is not installed on this
machine, which is why this is a script rather than a one-liner.
"""
import json
import os
import sys

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

path = (
    (payload.get("tool_input") or {}).get("file_path")
    or (payload.get("tool_response") or {}).get("filePath")
    or ""
)
path = path.replace("\\", "/")

# Match whether the payload carried an absolute path or a repo-relative one:
# a leading-slash test fails on "docs/src/state.json".
parts = path.split("/")
if len(parts) >= 2 and parts[-2] == "src" and parts[-3:-2] == ["docs"]         and path.endswith(".json"):
    name = os.path.basename(path)
    print(json.dumps({
        "systemMessage": (
            f"{name} changed -- the SVG generated from it is now stale. "
            "Re-render with /redraw-diagrams before committing; a JSON that "
            "disagrees with its SVG has happened here before."
        )
    }))
