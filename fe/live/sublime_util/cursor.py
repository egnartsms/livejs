import re

import sublime


class Cursor:
    def __init__(self, pos, view, edit=None):
        self.pos = pos
        self.view = view
        self.edit = edit

    @property
    def char(self):
        return self.view.substr(self.pos)

    def insert(self, s):
        n_ins = self.view.insert(self.edit, self.pos, s)
        self.pos += n_ins

    def erase(self, upto):
        self.view.erase(self.edit, sublime.Region(self.pos, upto))
        if upto < self.pos:
            self.pos = upto

    def find(self, pattern):
        return self.view.find(pattern, self.pos)

    def skip_ws_bwd(self, skip_bol=False):
        """Skip whitespace backwards from current position

        If skip_bol is True, move also before the \n that starts the current line in case
        the whitespace extends all the way to the beginning of line
        """
        reg_line = self.view.line(self.pos)
        s = self.view.substr(sublime.Region(reg_line.a, self.pos))[::-1]
        mo = re.match(r'\s*', s)
        if mo.end() == len(s) and skip_bol:
            self.pos -= (mo.end() + 1)
        else:
            self.pos -= mo.end()
