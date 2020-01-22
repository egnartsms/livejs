from live.sublime_util.region_edit import RegionEditHelper
from live.sublime_util.misc import add_hidden_regions
from live.settings import setting_module_id
from live.modules.datastructures import Module


class Repl:
    def __init__(self, view):
        self.view = view
        self.reh = RegionEditHelper(self.view, 'edit', self._set_edit_region)
        self.module_id = setting_module_id[view]

    @property
    def module(self):
        return Module.with_id(self.module_id)

    def insert_prompt(self):
        pass

    def _set_edit_region(self, reg):
        add_hidden_regions(self.view, 'edit', [reg])
