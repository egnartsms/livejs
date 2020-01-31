import contextlib
import functools
import inspect
import operator
import re
import sublime
import sublime_api
import sublime_plugin

from live.gstate import ws_handler
from live.sublime_util.edit import call_ensuring_edit_for
from live.sublime_util.edit import call_with_edit_token
from live.sublime_util.edit import edit_for
from live.util.misc import mapping_key_set


class BackendError(Exception):
    def __init__(self, message, **attrs):
        self.message = message
        self.__dict__.update(attrs)

    @classmethod
    def make(cls, info):
        def camel_to_underscore(s):
            return re.sub(r'(?<![A-Z])[A-Z]', lambda m: '_' + m.group().lower(), s)

        return cls(**{camel_to_underscore(k): v for k, v in info.items()})


class GenericError(BackendError):
    name = 'generic'


class DuplicateKeyError(BackendError):
    name = 'duplicate_key'


class GetterThrewError(BackendError):
    name = 'getter_threw'


be_errors = {sub.name: sub for sub in BackendError.__subclasses__()}


def be_error(name, info):
    return be_errors[name].make(info)


def supply_edit_on_each_send(view, gtor):
    resp = resp_exc = None

    def thunk():
        if resp_exc is None:
            return gtor.send(resp)
        else:
            return gtor.throw(resp_exc)

    while True:
        request = call_ensuring_edit_for(view, thunk)

        try:
            resp = yield request
            resp_exc = None
        except Exception as e:
            resp = None
            resp_exc = e


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
