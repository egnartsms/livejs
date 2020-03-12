import sublime_plugin

from live.sublime.edit import edit_for
from live.common.method import call_next
from live.common.method import method
from live.common.misc import mapping_key_set


class TextCommand(sublime_plugin.TextCommand):
    @method.around
    def run(self, edit, **args):
        with mapping_key_set(edit_for, self.view, edit):
            yield call_next(**args)
