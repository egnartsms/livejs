import operator as pyop
import sublime
import sublime_plugin

from .operations import is_view_module_browser
from .operations import module_browser_for
from live.gstate import ws_handler
from live.sublime_util.edit import call_with_edit


__all__ = ['CodeBrowserEventListener']


class CodeBrowserEventListener(sublime_plugin.ViewEventListener):
    @classmethod
    def is_applicable(cls, settings):
        return is_view_module_browser(settings)

    @classmethod
    def applies_to_primary_view_only(cls):
        return True

    @property
    def mbrowser(self):
        return module_browser_for(self.view)

    def on_query_context(self, key, operator, operand, match_all):
        if operator == sublime.OP_EQUAL:
            op = pyop.eq
        elif operator == sublime.OP_NOT_EQUAL:
            op = pyop.ne
        else:
            return False

        if key == 'livejs_cb_exact_node_selected':
            val = self.mbrowser.get_single_selected_node() is not None
        elif key == 'livejs_cb_edit_mode':
            val = self.mbrowser.is_editing
        elif key == 'livejs_cb_view_mode':
            val = not self.mbrowser.is_editing
        else:
            return False

        return op(val, operand)

    def on_activated(self):
        if not ws_handler.is_connected or self.mbrowser.root is None:
            call_with_edit(self.view, self.mbrowser.invalidate)

    def on_modified(self):
        self.mbrowser.ensure_modifications_within_edit_region()

    def on_selection_modified(self):
        self.mbrowser.set_view_read_only_if_region_editing()
