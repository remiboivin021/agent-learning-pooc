import sys
import yaml

with open("ci.yml") as fh:
    wf = yaml.safe_load(fh)
on = wf.get("on", wf.get(True))  # PyYAML parses a bare `on` key as True
if not isinstance(on, dict):
    raise SystemExit("workflow has no trigger mapping")
if "pull_request" not in on:
    raise SystemExit("pull_request trigger was removed")
push = on.get("push", "absent")
if push == "absent":
    sys.exit(0)
branches = push.get("branches") if isinstance(push, dict) else None
if not branches:
    raise SystemExit("push trigger runs on every branch: duplicate runs with pull_request")
