import contextlib


@contextlib.contextmanager
def attr_set(obj, attr, to_value):
    old_value = getattr(obj, attr)
    setattr(obj, attr, to_value)
    try:
        yield
    finally:
        setattr(obj, attr, old_value)
