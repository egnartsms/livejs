import sublime_plugin

from .operations import find_repl, new_repl


__all__ = ['LivejsOpenReplCommand']


class LivejsOpenReplCommand(sublime_plugin.WindowCommand):
    def run(self):
        repl = find_repl(self.window)
        if repl is None:
            repl = new_repl(self.window)
        
        self.window.focus_view(repl)
