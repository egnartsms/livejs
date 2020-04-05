import sublime
import sublime_plugin

from live.common.method import method
from live.project.datastructure import Module
from live.repl.operation import find_repl_view
from live.repl.operation import new_repl_view
from live.repl.operation import repl_for
from live.settings import setting
from live.shared.backend import BackendInteractingTextCommand
from live.shared.command import TextCommand
from live.shared.input_handler import ModuleInputHandler
from live.shared.inspector import insert_js_value
from live.shared.js_cursor import StructuredCursor
from live.sublime.misc import read_only_set_to
from live.sublime.selection import set_selection
from live.ws_handler import BackendError
from live.ws_handler import ws_handler


__all__ = [
    'LivejsOpenReplCommand', 'LivejsReplSendCommand', 'LivejsReplMoveUserInputCommand',
    'LivejsReplSetCurrentModuleCommand', 'LivejsReplClearCommand'
]


class ReplCommandMixin(sublime_plugin.TextCommand):
    @property
    def repl(self):
        return repl_for(self.view)


class LivejsOpenReplCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = find_repl_view(self.window)
        if view is None:
            module = ws_handler.run_sync_op('getProjectArbitraryModule', {
                'projectId': setting.project_id[self.window]
            })
            view = new_repl_view(self.window,
                                 Module(id=module['id'], name=module['name']))
        
        self.window.focus_view(view)


class LivejsReplSendCommand(BackendInteractingTextCommand, ReplCommandMixin):
    @method.primary
    def run(self):
        text = self.view.substr(self.repl.edit_region)
        stripped_text = text.rstrip()
        if stripped_text != text:
            self.repl.replace_edit_region_contents(stripped_text)
            text = stripped_text

        try:
            ws_handler.run_async_op('replEval', {
                'spaceId': self.repl.inspection_space_id,
                'mid': self.repl.cur_module_id,
                'code': text
            })
            jsval = yield
            error = None
        except BackendError as e:
            error = e

        cur = StructuredCursor(self.repl.edit_region.b, self.view)
        with read_only_set_to(self.view, False):
            if error:
                cur.insert('\n! ')
                cur.insert(error.message)
            else:
                cur.insert('\n< ')
                insert_js_value(self.repl, cur, jsval)
            cur.insert('\n\n')
            self.repl.insert_prompt(cur)

        set_selection(self.view, to=cur.pos, show=True)


class LivejsReplMoveUserInputCommand(TextCommand, ReplCommandMixin):
    @method.primary
    def run(self, forward):
        if forward:
            res = self.repl.to_next_prompt()
            if not res:
                sublime.status_message("Already at newest input")
        else:
            res = self.repl.to_prev_prompt()
            if not res:
                sublime.status_message("Already at oldest input")


class LivejsReplSetCurrentModuleCommand(TextCommand, ReplCommandMixin):
    @method.primary
    def run(self, module):
        module = Module(id=module['id'], name=module['name'])
        self.repl.set_current_module(module)
        self.repl.reinsert_prompt()

    def input(self, args):
        modules = ws_handler.run_sync_op('getProjectModules', {
            'projectId': setting.project_id[self.view.window()]
        })
        return ModuleInputHandler(modules)


class LivejsReplClearCommand(TextCommand, ReplCommandMixin):
    @method.primary
    def run(self):
        self.repl.erase_all_insert_prompt()
        self.repl.release_inspection_space()
