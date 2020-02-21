import sublime_plugin


class ModuleInputHandler(sublime_plugin.ListInputHandler):
    def __init__(self, modules):
        self.modules = modules

    def name(self):
        return 'module'

    def list_items(self):
        return [(mod['name'], mod) for mod in self.modules]
