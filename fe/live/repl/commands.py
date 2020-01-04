import sublime_plugin

from live.code.cursor import Cursor
from live.code.common import make_js_value_inserter
from .operations import find_repl, new_repl, insert_js_value, BE_RESPONSE


__all__ = ['LivejsOpenReplCommand', 'LivejsReplSendCommand']


class LivejsOpenReplCommand(sublime_plugin.WindowCommand):
    def run(self):
        repl = find_repl(self.window)
        if repl is None:
            repl = new_repl(self.window)
        
        self.window.focus_view(repl)


class LivejsReplSendCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        cur = Cursor(self.view.size(), self.view, edit)
        cur.insert('\n> ')
        insert_js_value(
            self.view,
            make_js_value_inserter(cur, BE_RESPONSE, 0)
        )
