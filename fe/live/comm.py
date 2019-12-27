import functools

from live.gstate import ws_handler


def communicates_with_be(func):
    """Decorator that makes func receive responses where it yields.

    The decorated function always returns None.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        ws_handler.install_cont(func(*args, **kwargs))
        return None

    return wrapper
