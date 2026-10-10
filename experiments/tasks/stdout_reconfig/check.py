import os, sys
sys.path.insert(0, os.getcwd())
import textout

calls = []


class Stream:
    encoding = "cp1252"

    def reconfigure(self, **kwargs):
        calls.append(kwargs)

    def write(self, text):
        return len(text)

    def flush(self):
        pass


sys.stdout, sys.stderr = Stream(), Stream()
init = getattr(textout, "init_output", None)
if init is not None:
    init()
sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
if calls:
    raise SystemExit("library reconfigured the application's standard streams")
