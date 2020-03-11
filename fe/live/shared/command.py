import sublime_plugin

from live.sublime_util.edit import edit_for
from live.util.method import call_next
from live.util.method import method
from live.util.misc import mapping_key_set


class TextCommand(sublime_plugin.TextCommand):
    @method.around
    def run(self, edit, **args):
        with mapping_key_set(edit_for, self.view, edit):
            yield call_next(**args)
