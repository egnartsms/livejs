import sublime

from live.code.cursor import Cursor
from live.modules.datastructures import Module
from live.settings import setting
from live.sublime_util.edit import edit_for
from live.sublime_util.edit import edits_self_view
from live.sublime_util.misc import add_hidden_regions
from live.sublime_util.region_edit import RegionEditHelper


class Repl:
    EDIT_REGION_KEY = 'edit'

    def __init__(self, view):
        self.view = view
        self.reh = None

    @property
    def module_id(self):
        return setting.module_id[self.view]

    @property
    def module_name(self):
        return setting.module_name[self.view]
    
    @property
    def module(self):
        return Module.with_id(self.module_id)

    @property
    def is_ready(self):
        return self.reh is not None
    
    @property
    def current_prompt(self):
        return self.module_name + '> '

    def insert_prompt(self, cur):
        cur.insert(self.current_prompt)
        self._set_edit_region(sublime.Region(cur.pos))
        self.reh = RegionEditHelper(self.view, self.EDIT_REGION_KEY,
                                    self._set_edit_region)

    @edits_self_view
    def erase_all_insert_prompt(self):
        cur = Cursor(0, self.view)
        cur.erase(self.view.size())
        self.insert_prompt(cur)

    def prepare_for_activation(self):
        if not self.is_ready:
            self.erase_all_insert_prompt()

    @edits_self_view
    def _clear_out_for_offline_work(self):
        cur = Cursor(0, self.view)
        cur.erase(self.view.size())
        self.insert_prompt(cur)
        self.is_cleared_out_for_offline_work = True

    @property
    def edit_region(self):
        [reg] = self.view.get_regions(self.EDIT_REGION_KEY)
        return reg

    def _set_edit_region(self, reg):
        add_hidden_regions(self.view, self.EDIT_REGION_KEY, [reg])
