"""When we need to perform some operation on a Sublime buffer (view), we have to run a
TextCommand.  This is the only way to get an Edit object necessary for modifications."""

import sublime
import sublime_plugin
import sublime_api


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
