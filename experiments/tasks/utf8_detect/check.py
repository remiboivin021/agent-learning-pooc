import os, sys
sys.path.insert(0, os.getcwd())
from detect import supports_utf8


class Stream:
    def __init__(self, encoding):
        self.encoding = encoding


real = sys.stdout
try:
    sys.stdout = Stream("utf-8")
    assert supports_utf8() is True, "utf-8 stream reported as unsupported"
    sys.stdout = Stream("UTF-8")
    assert supports_utf8() is True, "UTF-8 spelling not handled"
    sys.stdout = Stream("cp1252")
    assert supports_utf8() is False, "cp1252 stream reported as utf-8"
    sys.stdout = Stream(None)
    assert supports_utf8() is False, "missing encoding reported as utf-8"
finally:
    sys.stdout = real
