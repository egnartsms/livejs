import contextlib
import sublime

from live.gstate import config
from live.sublime.edit import edit_for


class Cursor:
    def __init__(self, pos, view):
        super().__init__()
        self.pos = pos
        self.view = view
        self.retain_stack = []

    @property
    def edit(self):
        return edit_for[self.view]

    def __getstate__(self):
        """retain_stack is not copied"""
        state = self.__dict__.copy()
        state['retain_stack'] = []
        return state

    @contextlib.contextmanager
    def pos_preserved(self):
        pos = self.pos
        yield pos
        self.pos = pos

    @property
    def char(self):
        return self.view.substr(self.pos)

    @property
    def prec_char(self):
        return self.view.substr(self.pos - 1)

    def insert(self, s):
        n_ins = self.view.insert(self.edit, self.pos, s)
        self.pos += n_ins

    def insert_spaces(self, n):
        self.insert(' ' * n)

    def indent(self, n):
        self.insert(n * config.s_indent)

    def __getitem__(self, n):
        """Access the stack of pushed cursor positions.

        cur[0] gives the current pos, cur[1] gives the most recently pushed, and so on.
        """
        return self.pos if n == 0 else self.retain_stack[-n]

    def push(self):
        self.retain_stack.append(self.pos)

    def pop(self):
        self.pos = self.retain_stack.pop()

    def pop_region(self):
        beg = self.retain_stack.pop()
        end = self.pos
        return sublime.Region(beg, end)

    def erase(self, upto):
        if self.pos == upto:
            return

        self.view.erase(self.edit, sublime.Region(self.pos, upto))
        if upto < self.pos:
            self.pos = upto

    def pop_erase(self):
        beg = self.retain_stack.pop()
        self.erase(beg)

    def replace(self, upto, new_text):
        self.view.replace(self.edit, sublime.Region(self.pos, upto), new_text)
        self.pos = (upto if upto < self.pos else self.pos) + len(new_text)

    def find(self, pattern):
        """Return sublime.Region"""
        return self.view.find(pattern, self.pos)

    def go_past(self, pattern):
        """Move to the end of the nearest pattern match.

        :return: whether pattern was found
        """
        reg = self.find(pattern)
        if reg.a == -1:
            return False

        self.pos = reg.b
        return True

    def skip_ws(self):
        """Skip whitespace forwards"""
        while self.char.isspace():
            self.pos += 1

    def skip_ws_bwd(self, limit=0):
        """Skip whitespace backwards"""
        while self.pos > limit and self.prec_char.isspace():
            self.pos -= 1
