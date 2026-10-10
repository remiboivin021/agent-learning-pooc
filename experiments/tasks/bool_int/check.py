import os, sys
sys.path.insert(0, os.getcwd())
from volume import set_volume

assert set_volume(50) == 50
assert set_volume(0) == 0 and set_volume(100) == 100
for bad in (101, -1, "5", 1.5, None, True, False):
    try:
        set_volume(bad)
    except (ValueError, TypeError):
        continue
    raise SystemExit(f"accepted invalid input: {bad!r}")
