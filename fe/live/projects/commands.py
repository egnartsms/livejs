import os
import re
import sublime
import sublime_plugin

from collections import OrderedDict

from .datastructures import Project
from .operations import project_for_window
from live.common.method import method
from live.common.misc import file_contents
from live.common.misc import gen_uid
from live.gstate import config
from live.gstate import fe_projects
from live.projects.operations import read_project_file_at
from live.settings import setting
from live.shared.backend import BackendInteractingWindowCommand
from live.shared.backend import is_interaction_possible
from live.shared.json_edit import json_root_in
from live.sublime.edit import edits_view
from live.sublime.misc import open_filepath
from live.sublime.on_view_loaded import on_load
from live.sublime.view_saver import saver
from live.ws_handler import ws_handler


__all__ = ['LivejsLoadProject', 'LivejsAddModule']


class LivejsLoadProject(BackendInteractingWindowCommand):
    def validate(self):
        proj = project_for_window(self.window)
        if proj:
            sublime.error_message("This window is already associated with project \"{}\""
                                  .format(proj.name))
            return False
        return True

    @method.primary
    def run(self):
        folders = self.window.folders()
        if len(folders) != 1:
            sublime.status_message(
                "Must have exactly 1 folder open to determine project root"
            )
            return

        [root] = folders

        try:
            proj_data = read_project_file_at(root)
        except Exception as e:
            sublime.error_message("Could not read project file: {}".format(e))
            raise

        proj = Project(
            id=proj_data['projectId'],
            name=proj_data['projectName'],
            path=root
        )

        ws_handler.run_async_op('loadProject', {
            'projectPath': root,
            'project': proj_data,
            'sources': {
                module['id']: proj.module_contents(module['name'])
                for module in proj_data['modules']
            }
        })
        yield

        fe_projects.append(proj)
        setting.project_id[self.window] = proj.id

        sublime.status_message("Project \"{}\" loaded!".format(proj.name))


class LivejsAddModule(BackendInteractingWindowCommand):
    @method.primary
    def run(self, module_name):
        proj = project_for_window(self.window)
        module_path = proj.module_filepath(module_name)

        if os.path.exists(module_path):
            sublime.error_message("File \"{}\" already exists".format(module_path))
            return

        module_contents = file_contents(
            os.path.join(config.be_root, config.new_module_template)
        )
        
        module_id = gen_uid()
        ws_handler.run_async_op('loadModule', {
            'projectId': proj.id,
            'moduleId': module_id,
            'name': module_name,
            'source': module_contents,
            'untracked': []
        })
        yield       

        proj_file_view = open_filepath(self.window, proj.project_file_path)

        @on_load(proj_file_view)
        @edits_view(proj_file_view)
        def modify_project_file():
            R = json_root_in(proj_file_view)
            R['modules'].append(OrderedDict([
                ('id', module_id),
                ('name', module_name),
                ('untracked', [])
            ]))
            saver.request_save(proj_file_view)

        with open(module_path, 'w') as file:
            file.write(module_contents)

    def input(self, args):
        if not is_interaction_possible():
            return None

        proj = project_for_window(self.window)
        if not proj:
            return None
        
        modules_data = ws_handler.run_sync_op('getProjectModules', {
            'projectId': proj.id
        })
        return ModuleNameInputHandler([md['name'] for md in modules_data])


class ModuleNameInputHandler(sublime_plugin.TextInputHandler):
    def __init__(self, existing_module_names):
        self.existing_module_names = existing_module_names

    def validate(self, text):
        if not re.match(r'^[a-zA-Z0-9-]+$', text):
            return False

        return text not in self.existing_module_names
