def set_volume(level):
    if not isinstance(level, int) or not 0 <= level <= 100:
        raise ValueError("level must be an integer between 0 and 100")
    return level
