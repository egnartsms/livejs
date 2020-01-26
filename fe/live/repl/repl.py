import contextlib
import sublime

from live.code.cursor import Cursor
from live.modules.datastructures import Module
from live.settings import setting
from live.sublime_util.edit import edits_self_view
from live.sublime_util.misc import read_only_set_to
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

    @property
    def edit_region(self):
        [reg] = self.view.get_regions(self.EDIT_REGION_KEY)
        return reg

    def _set_edit_region(self, reg):
        add_hidden_regions(self.view, self.EDIT_REGION_KEY, [reg])

    def _set_reh(self):
        self.reh = RegionEditHelper(
            self.view, self.EDIT_REGION_KEY, self._set_edit_region
        )

    def insert_prompt(self, cur):
        cur.insert(self.current_prompt)
        self._set_edit_region(sublime.Region(cur.pos))
        self._set_reh()

    @edits_self_view
    def erase_all_insert_prompt(self):
        cur = Cursor(0, self.view)
        cur.erase(self.view.size())
        self.insert_prompt(cur)

    def prepare_for_activation(self):
        if not self.is_ready:
            self.erase_all_insert_prompt()

    def ensure_modifications_within_edit_region(self):
        """Undo any modifications outside edit region"""
        if self.reh is not None:
            self.reh.undo_modifications_outside_edit_region()

    def set_view_read_only(self):
        """Set the REPL view's read_only status depending on current selection"""
        if self.reh is not None:
            self.reh.set_read_only()

    @contextlib.contextmanager
    def _reh_suppressed(self):
        self.reh = None
        try:
            yield
        finally:
            self._set_reh()

    @contextlib.contextmanager
    def suppressed_region_editing(self):
        with self._reh_suppressed(), read_only_set_to(self.view, False):
            yield
