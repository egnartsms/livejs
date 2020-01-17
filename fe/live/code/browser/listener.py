import operator as pyop
import sublime
import sublime_plugin

from .operations import get_single_selected_node
from .operations import invalidate_codebrowser
from .view_info import info_for
from live.gstate import ws_handler
from live.sublime_util.region_edit import region_edit_helpers


__all__ = ['CodeBrowserEventListener']


class CodeBrowserEventListener(sublime_plugin.ViewEventListener):
    @classmethod
    def is_applicable(cls, settings):
        return settings.get('livejs_view') == 'Code Browser'

    @classmethod
    def applies_to_primary_view_only(cls):
        return True

    def on_query_context(self, key, operator, operand, match_all):
        if operator == sublime.OP_EQUAL:
            op = pyop.eq
        elif operator == sublime.OP_NOT_EQUAL:
            op = pyop.ne
        else:
            return False

        if key == 'livejs_cb_exact_node_selected':
            val = get_single_selected_node(self.view) is not None
        elif key == 'livejs_cb_edit_mode':
            val = info_for(self.view).is_editing
        elif key == 'livejs_cb_view_mode':
            val = not info_for(self.view).is_editing
        else:
            return False

        return op(val, operand)

    def on_activated(self):
        if not ws_handler.is_connected:
            invalidate_codebrowser(self.view)
            return
        vinfo = info_for(self.view)
        if vinfo.root is None:
            invalidate_codebrowser(self.view)

    def on_modified(self):
        """Undo modifications to portions of the buffer outside the edit region.

        We only detect such modifications when the sizes of the corresponding pre and post
        regions change.  This cannot detect e.g. line swaps outside the edit region but
        is still very useful.

        Also, we detect insertion of text right before the edit region and right after it,
        and extend the edit region to include what was just inserted.
        """
        if self.view not in region_edit_helpers:
            return

        region_edit_helpers[self.view].undo_modifications_if_any()

    def on_selection_modified(self):
        if self.view not in region_edit_helpers:
            return

        self.view.set_read_only(region_edit_helpers[self.view].read_only_value())
