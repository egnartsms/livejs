import functools
import inspect
import sublime
import sublime_plugin

from live.coroutine import co_driver
from live.projects.operations import validate_window_project_loaded
from live.shared.command import TextCommand
from live.sublime.edit import call_ensuring_edit_for
from live.util.method import method
from live.util.misc import wrap_gtor
from live.ws_handler import MAIN_CHANNEL
from live.ws_handler import ws_handler


def validate_be_interaction(attempting_entity):
    if not ws_handler.is_connected:
        sublime.status_message("BE not connected")
        return False

    if co_driver.is_occupied(MAIN_CHANNEL):
        print("Ignored invocation of {}: another BE interaction is active".format(
            attempting_entity
        ))
        return False

    return True


def is_interaction_possible():
    return ws_handler.is_connected and co_driver.is_free(MAIN_CHANNEL)


def wrap_in_edit_view(gtor, view_getter):
    return wrap_gtor(gtor, lambda thunk: call_ensuring_edit_for(view_getter(), thunk))


class BackendInteractingTextCommand(TextCommand):
    @method.around
    def run(self, **args):
        if not validate_be_interaction(self):
            return
        if not self.validate():
            return

        gtor = yield
        gtor = wrap_in_edit_view(gtor, lambda: self.view)
        co_driver.add_coroutine(gtor, MAIN_CHANNEL)

    def validate(self):
        return validate_window_project_loaded(self.view.window())


class BackendInteractingWindowCommand(sublime_plugin.WindowCommand):
    @method.around
    def run(self, **args):
        if not validate_be_interaction(self):
            return
        if not self.validate():
            return

        gtor = yield
        co_driver.add_coroutine(gtor, MAIN_CHANNEL)

    def validate(self):
        return validate_window_project_loaded(self.window)


def interacts_with_backend(edits_view=None):
    if edits_view:
        sig = inspect.signature(edits_view)
        assert all(p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
                   for p in sig.parameters.values())
        view_getter_params = list(sig.parameters)

    def wrapper(fn):
        if edits_view:
            fn_sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            if not validate_be_interaction(fn):
                return

            gtor = fn(*args, **kwargs)
            if edits_view:
                ba = fn_sig.bind(*args, **kwargs)
                view_getter_args = {param: ba[param] for param in view_getter_params}
                view_getter = lambda: edits_view(**view_getter_args)
                gtor = wrap_in_edit_view(gtor, view_getter)
            co_driver.add_coroutine(gtor, MAIN_CHANNEL)


        return wrapped

    return wrapper
