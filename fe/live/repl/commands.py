import sublime
import sublime_plugin

from .operations import find_repl_view
from .operations import insert_js_value
from .operations import new_repl_view
from .operations import repl_for
from live.code.common import make_js_value_inserter
from live.code.cursor import Cursor
from live.comm import BackendError
from live.comm import interacts_with_be
from live.modules.datastructures import Module
from live.sublime_util.edit import run_method_remembers_edit
from live.sublime_util.misc import read_only_set_to
from live.sublime_util.misc import set_selection
from live.util.inheritable_decorators import ClassWithInheritableDecorators
from live.util.inheritable_decorators import decorator_for


__all__ = [
    'LivejsOpenReplCommand', 'LivejsReplSendCommand', 'LivejsReplMoveUserInputCommand'
]


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
        try:
            jsval = yield 'replEval', {'code': text}
            error = None
        except BackendError as e:
            error = e

        with read_only_set_to(self.view, False):
            if error:
                cur.insert('\n! ')
                cur.insert(error.message)
            else:
                cur.insert('\n< ')
                insert_js_value(
                    self.view,
                    make_js_value_inserter(cur, jsval, 0)
                )
            cur.insert('\n\n')
            self.repl.insert_prompt(cur)

        self.view.sel().clear()
        set_selection(self.view, to=cur.pos, show=True)


class LivejsReplMoveUserInputCommand(ReplTextCommand):
    def run(self, forward):
        if forward:
            res = self.repl.to_next_prompt()
            if not res:
                sublime.status_message("Already at newest input")
        else:
            res = self.repl.to_prev_prompt()
            if not res:
                sublime.status_message("Already at oldest input")
