import sublime_plugin
from .operations import is_view_repl
from live.sublime_util.view_info import view_info_getter
from live.sublime_util.region_edit import RegionEditHelper
from live.sublime_util.misc import add_hidden_regions


__all__ = ['ReplEventListener']


class ReplEventListener(sublime_plugin.ViewEventListener):
    @classmethod
    def is_applicable(cls, settings):
        return is_view_repl(settings)

    @classmethod
    def applies_to_primary_view_only(cls):
        return True

    def on_modified(self):
        repl_to_region_edit_helper[self.view].undo_modifications_outside_edit_region()

    def on_selection_modified(self):
        repl_to_region_edit_helper[self.view].set_read_only()
