NAMED = {"red", "green", "blue"}


def parse_color(value):
    if value not in NAMED:
        raise TypeError(f"unknown color: {value!r}")
    return value
