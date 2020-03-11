import json
import os
import re
import sublime
import sublime_plugin

from .datastructures import Project
from .operations import get_project_file_path
from .operations import get_project_modules_contents
from .operations import project_for_window
from live.coroutine import co_driver
from live.gstate import config
from live.gstate import fe_projects
from live.settings import setting
from live.util.misc import file_contents
from live.util.misc import gen_uid
from live.ws_handler import ws_handler
from live.ws_handler import sublime_error_message_on_be_error
from live.shared.backend import BackendInteractingWindowCommand
from live.shared.backend import is_interaction_possible
from live.util.method import method


__all__ = ['LivejsLoadProject', 'LivejsAddModule']


class LivejsLoadProject(BackendInteractingWindowCommand):
    @method.primary
    def run(self):
        folders = self.window.folders()
        if len(folders) != 1:
            sublime.status_message(
                "Must have exactly 1 folder open to determine project root"
            )
            return

        [root] = folders
        project_file_path = get_project_file_path(root)

        if not project_file_path:
            sublime.status_message("Project file not found (ending in .live.js)")
            return

        if len(project_file_path) > 1:
            sublime.status_message(
                "Multiple project files (ending in .live.js) at root level"
            )
            return

        [project_file_path] = project_file_path

        ws_handler.run_async_op('evalAsJson', {
            'source': file_contents(project_file_path)
        })
        project_data = yield

        project = Project(
            id=project_data['projectId'],
            name=project_data['projectName'],
            path=root
        )

        ws_handler.run_async_op('loadProject', {
            'projectPath': root,
            'project': project_data,
            'sources': {
                module['id']: file_contents(project.module_name_filepath(module['name']))
                for module in project_data['modules']
            }
        })
        yield

        fe_projects.append(project)
        setting.project_id[self.window] = project.id


class LivejsAddModule(BackendInteractingWindowCommand):
    @method.primary
    def run(self, module_name):
        project = project_for_window(self.window)
        module_path = os.path.join(project.path, module_name + '.js')

        if os.path.exists(module_path):
            sublime.error_message("File \"{}\" already exists".format(module_path))
            return

        module_contents = file_contents(
            os.path.join(config.be_root, '_new_module_template.js')
        )
        
        with open(module_path, 'w') as file:
            file.write(module_contents)

        ws_handler.run_async_op('loadModule', {
            'projectId': project.id,
            'moduleId': gen_uid(),
            'name': module_name,
            'source': module_contents,
            'untracked': []
        })
        yield       

    def input(self, args):
        if not is_interaction_possible() or not project_for_window(self.window):
            return None
        # return ModuleNameInputHandler(self.window)
        return None


class ModuleNameInputHandler(sublime_plugin.TextInputHandler):
    def __init__(self, window):
        modules_data = ws_handler.run_sync_op('getProjectModules', {
            'projectId': setting.project_id[window]
        })
        self.existing_module_names = [md['name'] for md in modules_data]

    def validate(self, text):
        if not re.match(r'^[a-zA-Z0-9-]+$', text):
            return False

        return text not in self.existing_module_names
