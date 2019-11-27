import re

import sublime

from live.config import config


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

    def indent(self, n):
        self.insert(n * config.s_indent)

    def erase(self, upto):
        self.view.erase(self.edit, sublime.Region(self.pos, upto))
        if upto < self.pos:
            self.pos = upto

    def find(self, pattern):
        return self.view.find(pattern, self.pos)

    def skip_ws_to_bol(self, skip_bol=False):
        """Skip whitespace backwards from current position

        If skip_bol is True, move also before the \n that starts the current line in case
        the whitespace extends all the way to the beginning of the line.
        """
        reg_line = self.view.line(self.pos)
        s = self.view.substr(sublime.Region(reg_line.a, self.pos))[::-1]
        mo = re.match(r'\s*', s)
        if mo.end() == len(s) and skip_bol:
            self.pos -= (mo.end() + 1)
        else:
            self.pos -= mo.end()

    def skip_re(self, re):
        """If the cursor is looking at re, skip it. Otherwise, don't move"""
        reg = self.find(re)
        if reg.a == self.pos:
            self.pos = reg.b

    def skip_ws(self):
        self.skip_re(r'\s+')
