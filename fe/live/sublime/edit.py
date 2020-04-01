"""When we need to perform some operation on a Sublime buffer (view), we have to run a
TextCommand.  This is the only way to get an Edit object necessary for modifications."""

import functools
import inspect
import sublime
import sublime_api
import sublime_plugin

from live.common.misc import args_extractor


__all__ = ['LivejsCallWithEditTokenCommand']


edit_callback = None
edit_callback_result = None
edit_callback_exc = None


def call_with_edit_token(view, callback):
    global edit_callback, edit_callback_result, edit_callback_exc

    edit_callback = callback
    
    try:
        view.run_command('livejs_call_with_edit_token')
        if edit_callback_exc is not None:
            raise edit_callback_exc
        else:
            return edit_callback_result
    finally:
        edit_callback = None
        edit_callback_result = None
        edit_callback_exc = None


def call_with_edit(view, callback):
    def outer_callback(edit_token):
        edit = sublime.Edit(edit_token)
        try:
            return callback(edit)
        finally:
            edit.edit_token = 0

    return call_with_edit_token(view, outer_callback)


class LivejsCallWithEditTokenCommand(sublime_plugin.TextCommand):
    def run_(self, edit_token, args):
        global edit_callback_result, edit_callback_exc

        sublime_api.view_begin_edit(self.view.id(), edit_token,
                                    'livejs_call_with_edit_token', None)
        try:
            edit_callback_result = edit_callback(edit_token)
        except Exception as e:
            edit_callback_exc = e
        finally:
            sublime_api.view_end_edit(self.view.id(), edit_token)

    def run(self, edit):
        raise NotImplementedError


class ViewKeyedDict:
    def __init__(self):
        self._dict = {}

    def __contains__(self, view):
        return view.id() in self._dict

    def __getitem__(self, view):
        return self._dict[view.id()]

    def __setitem__(self, view, value):
        self._dict[view.id()] = value

    def __delitem__(self, view):
        del self._dict[view.id()]

    def get(self, view):
        return self._dict.get(view.id())


edit_for = ViewKeyedDict()


def call_ensuring_edit_for(view, thunk):
    if view in edit_for:
        return thunk()

    def callback(edit):
        edit_for[view] = edit
        try:
            return thunk()
        finally:
            del edit_for[view]

    return call_with_edit(view, callback)


def edits_view(view_getter):
    view_getter = args_extractor(view_getter)

    def wrapper(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            return call_ensuring_edit_for(
                view_getter(fn, args, kwargs), lambda: fn(*args, **kwargs)
            )

        return wrapped

    return wrapper


edits_self_view = edits_view(lambda self: self.view)


edits_view_arg = edits_view(lambda view: view)
