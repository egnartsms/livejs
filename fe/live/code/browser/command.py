import functools
import sublime
import sublime_plugin

from .operations import module_browser_for
from live.comm import interacts_with_be
from live.sublime_util.edit import run_method_remembers_edit
from live.util.inheritable_decorators import ClassWithInheritableDecorators
from live.util.inheritable_decorators import decorator_for


class ModuleBrowserTextCommand(sublime_plugin.TextCommand,
                               metaclass=ClassWithInheritableDecorators):
    _edit = decorator_for('run', run_method_remembers_edit)

    @property
    def mbrowser(self):
        return module_browser_for(self.view)


class ModuleBrowserBeInteractingTextCommand(ModuleBrowserTextCommand):
    _be = decorator_for('run', interacts_with_be(edits_view='self.view'))
