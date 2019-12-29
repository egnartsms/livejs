import functools

from live.gstate import ws_handler


def be_interaction(func):
    """Decorator that makes func receive responses where it yields.

    The decorated function always returns None.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if ws_handler.cont is None:
            ws_handler.install_cont(func(*args, **kwargs))

        return None

    return wrapper
