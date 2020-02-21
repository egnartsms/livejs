import json
import os
import re
import sublime
import sublime_plugin

from .datastructures import Project
from .operations import get_project_modules_contents
from .operations import project_for_window
from live.comm import interacts_with_be
from live.gstate import config
from live.gstate import fe_projects
from live.gstate import ws_handler
from live.settings import setting
from live.util.misc import file_contents
from live.util.misc import gen_uid


__all__ = ['LivejsLoadProject', 'LivejsAddModule']


class LivejsLoadProject(sublime_plugin.WindowCommand):
    def run(self):
        folders = self.window.folders()
        if len(folders) != 1:
            sublime.status_message(
                "Must have exactly 1 folder open to determine project root"
            )
            raise RuntimeError

        if project_for_window(self.window):
            sublime.status_message("Already loaded LiveJS project in this window")
            raise RuntimeError

        [root] = folders
        
        @interacts_with_be()
        def on_project_name_entered(project_name):
            project_id = yield 'loadProject', {
                'name': project_name,
                'path': root,
                'modulesData': get_project_modules_contents(root)
            }

            fe_projects.append(Project(id=project_id, name='hockey', path=root))
            setting.project_id[self.window] = project_id
        
        intuitive_project_name = os.path.basename(root)
        self.window.show_input_panel('Project name:', intuitive_project_name,
                                     on_project_name_entered, None, None)


class LivejsAddModule(sublime_plugin.WindowCommand):
    def run_(self, *args, **kwargs):
        if not project_for_window(self.window):
            sublime.error_message("This window is not associated with any LiveJS project")
            return

        return super().run_(*args, **kwargs)

    @interacts_with_be()
    def run(self, module_name):
        project = project_for_window(self.window)
        module_contents = (
            file_contents(os.path.join(config.be_root, '_new_module_template.js'))
            .replace('LIVEJS_MODULE_ID', json.dumps(gen_uid()))
        )
        yield 'loadModule', {
            'projectId': project.id,
            'name': module_name,
            'src': module_contents
        }

        with open(os.path.join(project.path, module_name + '.js'), 'w') as file:
            file.write(module_contents)

    def input(self, args):
        return ModuleNameInputHandler(self.window)


class ModuleNameInputHandler(sublime_plugin.TextInputHandler):
    def __init__(self, window):
        modules_data = ws_handler.sync_request('getProjectModules', {
            'projectId': setting.project_id[window]
        })
        self.existing_module_names = [md['name'] for md in modules_data]

    def validate(self, text):
        if not re.match(r'^[a-zA-Z0-9-]+$', text):
            return False

        return text not in self.existing_module_names
