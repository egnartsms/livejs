import os.path

from collections import namedtuple


Module = namedtuple('Module', 'id name')


class Project:
    def __init__(self, id, name, path):
        self.id = id
        self.name = name
        self.path = path

    def module_name_filepath(self, module_name):
        return os.path.join(self.path, module_name + '.js')
