import sublime_plugin

from live.gstate import fe_modules


class ModuleInputHandler(sublime_plugin.ListInputHandler):
    def name(self):
        return 'module_id'

    def list_items(self):
        return [(fe_m.name, fe_m.id) for fe_m in fe_modules]
