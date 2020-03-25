import os.path
import re

from collections import namedtuple
from live.projects.operations import read_project_file_at
from live.common.misc import file_contents
from live.gstate import config


Module = namedtuple('Module', 'id name')


class Project:
    def __init__(self, id, name, path):
        self.id = id
        self.name = name
        self.path = path

    def module_filepath(self, module_name):
        return os.path.join(self.path, module_name + '.js')

    def module_contents(self, module_name):
        return file_contents(self.module_filepath(module_name))

    def get_all_js_files(self, root):
        """Return all .js files in the project root folder
    
        The project file is not included.

        :return: [{'name', 'src'}]
        """
        res = []

        for fname in os.listdir(root):
            mo = re.match(r'(\w+)\.js$', fname)
            if mo:
                res.append({
                    'name': mo.group(1),
                    'src': file_contents(os.path.join(root, mo.group()))
                })

        return res

    def read_project_data(self):
        return read_project_file_at(self.path)

    @property
    def project_file_path(self):
        return os.path.join(self.path, config.project_file_name)