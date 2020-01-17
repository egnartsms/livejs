import sublime

from live.sublime_util.view_info import ViewInfoPlane
from live.sublime_util.selection import inside_region_inc


class RegionEditHelper:
    def __init__(self, view, regkey, edit_region_setter):
        self.view = view
        self.regkey = regkey
        self.edit_region_setter = edit_region_setter
        self.pre, self.post = self._get_pre_post()

    def _get_edit_region(self):
        [reg] = self.view.get_regions(self.regkey)
        return reg

    def _set_edit_region(self, reg):
        self.edit_region_setter(self.view, reg)

    def _get_pre_post(self):
        reg = self._get_edit_region()
        return reg.a, self.view.size() - reg.b

    def _is_after_insertion_at_reg_begin(self):
        """Does the current selection look like smth was inserted at region beginning.

        This boils down to:
          * single cursor
          * and it is in front of the edit region
        """
        reg = self._get_edit_region()
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
        reg = self._get_edit_region()
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

    def undo_modifications_if_any(self):
        """Undo modifications to portions of the buffer outside the edit region.

        We only detect such modifications when the sizes of the corresponding pre and post
        regions change.  This cannot detect e.g. line swaps outside the edit region but
        is still very useful.

        Also, we detect insertion of text right before the edit region and right after it,
        and extend the edit region to include what was just inserted.
        """
        while True:
            pre, post = self._get_pre_post()
            if pre == self.pre and post == self.post:
                break
            elif pre > self.pre and post == self.post and \
                    self._is_after_insertion_at_reg_begin():
                delta = pre - self.pre
                reg = self._get_edit_region()
                self._set_edit_region(sublime.Region(reg.a - delta, reg.b))
                break
            elif post > self.post and pre == self.pre and \
                    self._is_after_insertion_at_reg_end(post - self.post):
                delta = post - self.post
                reg = self._get_edit_region()
                self._set_edit_region(sublime.Region(reg.a, reg.b + delta))
                break

            self.view.run_command('undo')
            sublime.status_message("Cannot edit outside the editing region")

    def read_only_value(self):
        sel = self.view.sel()
        reg = self._get_edit_region()
        return not all(inside_region_inc(reg, p.a) and inside_region_inc(reg, p.b)
                       for p in sel)


region_edit_helpers = ViewInfoPlane()
