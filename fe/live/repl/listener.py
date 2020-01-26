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

    def on_activated(self):
        self.repl.prepare_for_activation()

    def on_modified(self):
        self.repl.ensure_modifications_within_edit_region()

    def on_selection_modified(self):
        self.repl.set_view_read_only()
