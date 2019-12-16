import sublime
import sublime_plugin

import operator as pyop

from live.gstate import ws_handler
from .operations import (
    invalidate_codebrowser,
    set_edit_region,
    get_single_selected_node,
    edit_region
)
from .view_info import info_for


__all__ = ['CodeBrowserEventListener']


class CodeBrowserEventListener(sublime_plugin.ViewEventListener):
    @classmethod
    def is_applicable(cls, settings):
        return settings.get('livejs_view') == 'Code Browser'

    @classmethod
    def applies_to_primary_view_only(cls):
        return True

    def on_query_context(self, key, operator, operand, match_all):
        if not key.startswith('livejs_'):
            return None
        if operator not in (sublime.OP_EQUAL, sublime.OP_NOT_EQUAL):
            return None
        
        op = pyop.eq if operator == sublime.OP_EQUAL else pyop.ne
        if key == 'livejs_view':
            return op(self.view.settings().get('livejs_view'), operand)
        elif key == 'livejs_cb_exact_node_selected':
            return op(get_single_selected_node(self.view) is not None, operand)
        elif key == 'livejs_cb_edit_mode':
            return op(info_for(self.view).is_editing, operand)
        elif key == 'livejs_cb_view_mode':
            return not op(info_for(self.view).is_editing, operand)
        else:
            raise RuntimeError("Unknown context key: {}".format(key))

    def on_activated(self):
        if not ws_handler.is_connected:
            invalidate_codebrowser(self.view)
            return
        vinfo = info_for(self.view)
        if vinfo.root is None:
            invalidate_codebrowser(self.view)

    def _get_pre_post_sizes(self):
        [reg] = self.view.get_regions('edit')
        return reg.a, self.view.size() - reg.b

    def _after_insertion_at_reg_begin(self):
        [reg] = self.view.get_regions('edit')
        sel = self.view.sel()
        return len(sel) == 1 and sel[0].a == reg.a

    def _after_insertion_at_reg_end(self, delta):
        [reg] = self.view.get_regions('edit')
        sel = self.view.sel()
        return len(sel) == 1 and sel[0].a == reg.b + delta

    def on_modified(self):
        """Undo modifications to portions of the buffer outside the edit region.

        We only detect such modifications when the sizes of the corresponding pre and post
        regions change.  This cannot detect e.g. line swaps but still very useful.

        Also, we detect insertion of text right before the edit region and right after it,
        and extend the edit region to include what was just inserted.
        """
        vinfo = info_for(self.view)
        if not vinfo.is_editing:
            return

        pre, post = vinfo.edit_pre_post
        
        while True:
            xpre, xpost = self._get_pre_post_sizes()
            if xpre > pre and xpost == post and self._after_insertion_at_reg_begin():
                reg = edit_region(self.view)
                reg = sublime.Region(reg.a - (xpre - pre), reg.b)
                set_edit_region(self.view, reg, vinfo.enclosing_edit_reg(reg))
                break
            elif xpost > post and xpre == pre and \
                    self._after_insertion_at_reg_end(xpost - post):
                reg = edit_region(self.view)
                reg = sublime.Region(reg.a, reg.b + (xpost - post))
                set_edit_region(self.view, reg, vinfo.enclosing_edit_reg(reg))
                break
            elif xpre == pre and xpost == post:
                break

            self.view.run_command('undo')
            self.view.window().status_message("Cannot edit outside the editing region")

    def on_query_completions(self, prefix, locations):
        """Suppress completions when the cursor is not in the edit region.

        Despite the fact that we suppress modifications in the non-edit region of the
        buffer, Sublime still displays a completion list in there.  So suppress it, too.
        """
        [reg] = self.view.get_regions('edit')
        if not all(p > reg.a and p < reg.b for p in locations):
            return (
                [],
                sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS
            )
        else:
            return None
