import functools
import sublime
import sublime_plugin

from .operations import module_browser_for
from live.gstate import ws_handler
from live.sublime_util.edit import run_method_remembering_edit


def run_method_ensuring_modules_synched(run):
    @functools.wraps(run)
    def decorated(self, *args, **kwargs):
        if self.mbrowser.module is None:
            sublime.status_message("Modules not synchronized with BE")
            return

        return run(self, *args, **kwargs)

    return decorated


class ModuleBrowserTextCommandMetaclass(type):
    def __init__(cls, *args):
        if 'run' not in cls.__dict__:
            return

        cls.run = run_method_remembering_edit(cls.run)
        cls.run = run_method_ensuring_modules_synched(cls.run)


class ModuleBrowserTextCommand(sublime_plugin.TextCommand,
                               metaclass=ModuleBrowserTextCommandMetaclass):
    @property
    def mbrowser(self):
        return module_browser_for(self.view)
