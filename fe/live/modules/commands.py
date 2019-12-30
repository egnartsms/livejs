import sublime
import sublime_plugin

import os
import re
from functools import partial

from live.gstate import fe_modules
from live.comm import be_interaction
from .operations import load_modules
from .datastructures import Module


__all__ = ['LivejsAddModule']


class LivejsAddModule(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if view.settings().get('syntax') !=\
                'Packages/JavaScript/JavaScript.sublime-syntax':
            sublime.error_message("Not a JavaScript file")
            return

        if not view.file_name():
            sublime.error_message("This view does not correspond to a real file on disk")
            return

        if view.is_dirty():
            sublime.error_message("The file is dirty, please save it before loading as "
                                  "LiveJS module")
            return

        intuitive_module_name = os.path.splitext(os.path.basename(view.file_name()))[0]
        self.window.show_input_panel(
            'New module name:', intuitive_module_name,
            partial(self.on_module_name_entered, view), None, None
        )

    @be_interaction
    def on_module_name_entered(self, view, module_name):
        if not re.match(r'^[a-zA-Z0-9-]+$', module_name):
            self.window.status_message("Invalid module name (should be alphanums)")
            return

        if any(m.name == module_name for m in fe_modules):
            self.window.status_message("Module with the name {} already exists"
                                       .format(module_name))
            return

        new_module = Module(name=module_name, path=view.file_name())
        yield from load_modules([new_module])
        self.window.status_message("Module {} added!".format(module_name))
