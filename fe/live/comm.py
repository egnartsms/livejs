import sublime
import sublime_api
import sublime_plugin

import contextlib
import functools

from live.gstate import ws_handler
from live.sublime_util.edit import call_ensuring_edit_for
from live.sublime_util.edit import call_with_edit_token
from live.sublime_util.edit import edit_for
from live.util.misc import mapping_key_set


class BackendError(Exception):
    def __init__(self, name, info):
        self.name = name
        self.info = info


def interacts_with_be(func):
    """Decorator that makes func receive responses where it yields.

    The decorated function always returns None.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not ws_handler.is_connected:
            sublime.status_message("BE not connected")
            return

        if ws_handler.cont is not None:
            print("Ignored invocation of {}: another BE interaction is active"
                  .format(func))
            return
        
        ws_handler.install_cont(func(*args, **kwargs))

        return None

    return wrapper


def run_method_interacts_with_be(run):
    @functools.wraps(run)
    def decorated(self, edit, *args, **kwargs):
        if not ws_handler.is_connected:
            sublime.status_message("BE not connected")
            return

        if ws_handler.cont is not None:
            print("Ignored invocation of {}: another BE interaction is active"
                  .format(self.name()))
            return

        def supply_edit_on_each_send(gtor):
            x = None
            while True:
                x = yield call_ensuring_edit_for(self.view, lambda: gtor.send(x))

        gtor = run(self, *args, **kwargs)
        gtor = supply_edit_on_each_send(gtor)

        with mapping_key_set(edit_for, self.view, edit):
            ws_handler.install_cont(gtor)

        return None

    return decorated


# class TextCommandInteractingWithBe(sublime_plugin.TextCommand):
#     def run_(self, edit_token, args):
#         if not ws_handler.is_connected:
#             sublime.status_message("BE not connected")
#             return

#         if ws_handler.cont is not None:
#             print("Ignored command {}: another BE interaction is active"
#                   .format(self.name()))
#             return

#         args = self.filter_args(args)
#         edit = sublime.Edit(0)
#         cont = self._invoke_handling_missing_input(lambda: self.run(edit, **(args or {})))
#         if cont is None:
#             return

#         def scenario():
#             def send(jsval, edit_token):
#                 edit.edit_token = edit_token
#                 try:
#                     return cont.send(jsval)
#                 finally:
#                     edit.edit_token = 0

#             # On initial run the edit object can reuse the value of 'edit_token' from
#             # initial command invocation. For subsequent runs, we generate new tokens.
#             x0 = yield send(None, edit_token)

#             while True:
#                 x0 = yield call_with_edit_token(self.view, functools.partial(send, x0))

#         ws_handler.install_cont(scenario())

#     def _invoke_handling_missing_input(self, callme):
#         try:
#             return callme()
#         except (TypeError) as e:
#             if 'required positional argument' in str(e):
#                 if sublime_api.view_can_accept_input(self.view.id(), self.name(), args):
#                     sublime_api.window_run_command(
#                         sublime_api.view_window(self.view.id()),
#                         'show_overlay',
#                         {
#                             'overlay': 'command_palette',
#                             'command': self.name(),
#                             'args': args
#                         }
#                     )
#                     return None
#             raise

#     def run(self, edit, **args):
#         raise NotImplementedError
