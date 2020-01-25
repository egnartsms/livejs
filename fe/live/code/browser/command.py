import functools
import sublime
import sublime_plugin

from .operations import module_browser_for
from live.comm import run_method_interacts_with_be
from live.gstate import ws_handler
from live.sublime_util.edit import edit_for
from live.sublime_util.edit import run_method_remembers_edit
from live.util.inheritable_decorators import ClassWithInheritableDecorators
from live.util.inheritable_decorators import decorator_for
from live.util.misc import mapping_key_set


class BaseModuleBrowserTextCommand(sublime_plugin.TextCommand,
                                   metaclass=ClassWithInheritableDecorators):
    @decorator_for('run')
    def _check_before_run(run):
        @functools.wraps(run)
        def decorated(self, *args, **kwargs):
            if self.mbrowser.module is None:
                sublime.status_message("Modules not synchronized with BE")
                return

            return run(self, *args, **kwargs)

        return decorated

    @property
    def mbrowser(self):
        return module_browser_for(self.view)


class ModuleBrowserTextCommand(BaseModuleBrowserTextCommand):
    _edit = decorator_for('run', run_method_remembers_edit)


class ModuleBrowserBeInteractingTextCommand(BaseModuleBrowserTextCommand):
    _be = decorator_for('run', run_method_interacts_with_be)
