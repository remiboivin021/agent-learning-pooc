import os, sys
sys.path.insert(0, os.getcwd())
from colors import parse_color

assert parse_color("red") == "red"
try:
    parse_color("pink")
except ValueError:
    pass
except Exception as err:
    raise SystemExit(f"unknown name must raise ValueError, got {type(err).__name__}")
else:
    raise SystemExit("unknown name accepted")
try:
    parse_color(5)
except TypeError:
    pass
except Exception as err:
    raise SystemExit(f"non-string must raise TypeError, got {type(err).__name__}")
else:
    raise SystemExit("non-string accepted")
