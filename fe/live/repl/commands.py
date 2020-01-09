import sublime
import sublime_plugin

from live.comm import TextCommandInteractingWithBe
from live.code.cursor import Cursor
from live.code.common import make_js_value_inserter
from .operations import find_repl, new_repl, insert_js_value


__all__ = ['LivejsOpenReplCommand', 'LivejsReplSendCommand']


class LivejsOpenReplCommand(sublime_plugin.WindowCommand):
    def run(self):
        repl = find_repl(self.window)
        if repl is None:
            repl = new_repl(self.window)
        
        self.window.focus_view(repl)


class LivejsReplSendCommand(TextCommandInteractingWithBe):
    def run(self, edit):
        matches = self.view.find_all(r'^.+>')
        if not matches:
            sublime.status_message("Not found a prompt")
            return

        text = self.view.substr(sublime.Region(matches[-1].b, self.view.size()))
        text = text.strip()

        jsval = yield 'replEval', {'code': text}

        cur = Cursor(self.view.size(), self.view, edit)
        cur.insert('\n< ')
        insert_js_value(
            self.view,
            make_js_value_inserter(cur, jsval, 0)
        )
