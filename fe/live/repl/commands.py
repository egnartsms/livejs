import sublime
import sublime_plugin

from .operations import find_repl_view
from .operations import insert_js_value
from .operations import new_repl_view
from .operations import repl_for
from live.code.common import make_js_value_inserter
from live.code.cursor import Cursor
from live.comm import interacts_with_be
from live.modules.datastructures import Module
from live.sublime_util.edit import run_method_remembers_edit
from live.util.inheritable_decorators import ClassWithInheritableDecorators
from live.util.inheritable_decorators import decorator_for


__all__ = ['LivejsOpenReplCommand', 'LivejsReplSendCommand']


class ReplTextCommand(sublime_plugin.TextCommand,
                      metaclass=ClassWithInheritableDecorators):
    _edit = decorator_for('run', run_method_remembers_edit)

    @property
    def repl(self):
        return repl_for(self.view)


class ReplBeInteractingTextCommand(ReplTextCommand):
    _be = decorator_for('run', interacts_with_be(edits_view='self.view'))


class LivejsOpenReplCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = find_repl_view(self.window)
        if view is None:
            view = new_repl_view(self.window, Module.bootstrapping())
        
        self.window.focus_view(view)


class LivejsReplSendCommand(ReplBeInteractingTextCommand):
    def run(self):
        cur = Cursor(self.repl.edit_region.b, self.view, inter_sep_newlines=1)
        cur.push_region()
        cur.skip_ws_bwd()
        cur.pop_erase()

        text = self.view.substr(self.repl.edit_region)
        jsval = yield 'replEval', {'code': text}

        cur.insert('\n< ')
        insert_js_value(
            self.view,
            make_js_value_inserter(cur, jsval, 0)
        )
        cur.insert('\n\n')
        self.repl.insert_prompt(cur)
