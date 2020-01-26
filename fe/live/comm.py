import sublime
import sublime_api
import sublime_plugin
import contextlib
import functools
import inspect
import operator

from live.gstate import ws_handler
from live.sublime_util.edit import call_ensuring_edit_for
from live.sublime_util.edit import call_with_edit_token
from live.sublime_util.edit import edit_for
from live.util.misc import mapping_key_set


class BackendError(Exception):
    def __init__(self, name, info):
        self.name = name
        self.info = info


def supply_edit_on_each_send(view, gtor):
    x = None
    while True:
        x = yield call_ensuring_edit_for(view, lambda: gtor.send(x))


def interacts_with_be(edits_view=None):
    """Decorator that makes func receive responses where it yields.

    The decorated function always returns None.
    """
    if edits_view:
        param, *attrs = edits_view.split('.', maxsplit=1)
        if attrs:
            view_getter = operator.attrgetter(attrs[0])
        else:
            view_getter = lambda x: x  # noqa

    def wrapper(func):
        funcsig = inspect.signature(func)
        assert not edits_view or param in funcsig.parameters

        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            if not ws_handler.is_connected:
                sublime.status_message("BE not connected")
                return

            if ws_handler.cont is not None:
                print("Ignored invocation of {}: another BE interaction is active"
                      .format(func))
                return
            
            gtor = func(*args, **kwargs)
            if edits_view:
                view = view_getter(funcsig.bind(*args, **kwargs).arguments[param])
                gtor = supply_edit_on_each_send(view, gtor)

            ws_handler.install_cont(gtor)

            return None

        return wrapped

    return wrapper
