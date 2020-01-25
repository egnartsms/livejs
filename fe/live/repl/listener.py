import sublime_plugin

from .operations import is_view_repl
from .operations import repl_for


__all__ = ['ReplEventListener']


class ReplEventListener(sublime_plugin.ViewEventListener):
    @classmethod
    def is_applicable(cls, settings):
        return is_view_repl(settings)

    @classmethod
    def applies_to_primary_view_only(cls):
        return True

    @property
    def repl(self):
        return repl_for(self.view)

    def on_modified(self):
        if self.repl.reh is not None:
            self.repl.reh.undo_modifications_outside_edit_region()

    def on_selection_modified(self):
        if self.repl.reh is not None:
            self.repl.reh.set_read_only()
