"""Small helper library used by several applications."""
import sys


def init_output():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def greet(name):
    print(f"héllo {name}")
