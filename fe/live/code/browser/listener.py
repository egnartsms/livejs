import operator as pyop
import sublime
import sublime_plugin

from .operations import edit_region
from .operations import get_single_selected_node
from .operations import invalidate_codebrowser
from .operations import set_edit_region
from .view_info import info_for
from live.gstate import ws_handler


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
            return None

        if key == 'livejs_cb_exact_node_selected':
            val = get_single_selected_node(self.view) is not None
        elif key == 'livejs_cb_edit_mode':
            val = info_for(self.view).is_editing
        elif key == 'livejs_cb_view_mode':
            val = not info_for(self.view).is_editing
        else:
            return None

        return op(val, operand)

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

    def _is_after_insertion_at_reg_begin(self):
        """Does the current selection look like smth was inserted at region beginning.

        This boils down to:
          * single cursor
          * and it is in front of the edit region
        """
        [reg] = self.view.get_regions('edit')
        sel = self.view.sel()
        return len(sel) == 1 and sel[0].a == reg.a

    def _is_after_insertion_at_reg_end(self, delta):
        """Does the current selection look like smth was inserted at region end

        This boils down to:
          * single cursor
          AND
          * it is "delta" positions after the editing region end
          * or we have this: ---<edit region>(*)----, where the star * means cursor
            position, and a parenthesis after it means a closing parenthesis character
            that might be automatically inserted, such as ), ], }, etc. This is needed
            becase when an opening parenthesis is inserted at region end, the whole
            command fails since the closing parenthesis is attempted to be inserted but
            fails. So we take this measure to allow for the closing parenthesis to get
            automatically inserted.
        """
        [reg] = self.view.get_regions('edit')
        sel = self.view.sel()
        if len(sel) != 1:
            return False

        [sel] = sel
        if sel.a == reg.b + delta:
            return True

        if delta == 2 and sel.a == reg.b + 1 and \
                self.view.substr(reg.b + 1) in ')]}"\'`':
            return True

        return False

    def on_modified(self):
        """Undo modifications to portions of the buffer outside the edit region.

        We only detect such modifications when the sizes of the corresponding pre and post
        regions change.  This cannot detect e.g. line swaps outside the edit region but
        is still very useful.

        Also, we detect insertion of text right before the edit region and right after it,
        and extend the edit region to include what was just inserted.
        """
        vinfo = info_for(self.view)
        if not vinfo.is_editing:
            return

        pre, post = vinfo.edit_pre_post
        
        while True:
            xpre, xpost = self._get_pre_post_sizes()
            if xpre == pre and xpost == post:
                break
            elif xpre > pre and xpost == post and self._is_after_insertion_at_reg_begin():
                reg = edit_region(self.view)
                reg = sublime.Region(reg.a - (xpre - pre), reg.b)
                set_edit_region(self.view, reg)
                break
            elif xpost > post and xpre == pre and \
                    self._is_after_insertion_at_reg_end(xpost - post):
                reg = edit_region(self.view)
                reg = sublime.Region(reg.a, reg.b + (xpost - post))
                set_edit_region(self.view, reg)
                break

            self.view.run_command('undo')
            sublime.status_message("Cannot edit outside the editing region")

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
