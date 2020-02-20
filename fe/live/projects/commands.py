import sublime
import sublime_plugin

import os
import re
from functools import partial

from live.comm import interacts_with_be
from .datastructures import Module, Project
from live.gstate import projects
from live.util.misc import file_contents
from live.settings import setting


__all__ = ['LivejsLoadProject']


class LivejsLoadProject(sublime_plugin.WindowCommand):
    @interacts_with_be()
    def run(self):
        folders = self.window.folders()
        if len(folders) != 1:
            sublime.status_message(
                "Must have exactly 1 folder open to determine project root"
            )
            raise RuntimeError

        if setting.project_id[self.window] is not None:
            sublime.status_message("Already loaded LiveJS project in this window")
            raise RuntimeError

        [root] = folders

        project_id = yield 'loadProject', {
            'name': 'hockey',
            'path': root,
            'modulesData': get_modules_data(root)
        }

        projects.append(Project(id=project_id, name='hockey', path=root))
        setting.project_id[self.window] = project_id


def get_modules_data(root):
    res = []

    for fname in os.listdir(root):
        mo = re.match(r'(\w+)\.js$', fname)
        if mo:
            res.append({
                'name': mo.group(1),
                'src': file_contents(os.path.join(root, mo.group()))
            })

    return res


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

    @interacts_with_be()
    def on_module_name_entered(self, view, module_name):
        if not re.match(r'^[a-zA-Z0-9-]+$', module_name):
            self.window.status_message("Invalid module name (should be alphanums)")
            return

        if any(m.name == module_name for m in fe_modules):
            self.window.status_message("Module with the name {} already exists"
                                       .format(module_name))
            return

        new_module = Module(id=None, name=module_name, path=view.file_name())
        yield load_modules_request([new_module])
        fe_modules.append(new_module)
        self.window.status_message("Module {} added!".format(module_name))
