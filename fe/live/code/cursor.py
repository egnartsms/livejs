import sublime

import re
import contextlib

from live.config import config


class UnexpectedContents(Exception):
    def __init__(self, cur, msg, *args):
        msg = msg.format(*args)
        super().__init__("Unexpected contents after pos {}: {}".format(cur.pos, msg))


re_any_brace = r'''[`'"()[\]{}]'''
re_line_comment = r'//'
re_block_comment = r'/\*'
re_of_interest = (
    '{re_any_brace}|{re_line_comment}|{re_block_comment}|/'.format(**globals())
)


class Cursor:
    def __init__(self, pos, view, edit=None):
        super().__init__()
        self.pos = pos
        self.view = view
        self.edit = edit

    @contextlib.contextmanager
    def curpos_preserved(self):
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

    def erase(self, upto):
        self.view.erase(self.edit, sublime.Region(self.pos, upto))
        if upto < self.pos:
            self.pos = upto

    def find(self, pattern):
        return self.view.find(pattern, self.pos)

    def skip(self, pattern):
        """Move past pattern which must match at the current position.

        If pattern doesn't match right where self stands, raise an exception.
        """
        reg = self.find(pattern)
        if reg.a == -1 or reg.a != self.pos:
            raise UnexpectedContents(self, "expected pattern: {}", pattern)
        self.pos = reg.b

    def skip_ws(self):
        self.skip(r'\s*')

    def skip_ws_bwd(self):
        """Skip whitespace backwards from current position"""
        while self.prec_char.isspace():  # [-1] is '\x00' and is not space
            self.pos -= 1

    def sep_initial(self, nesting):
        self.insert('\n')
        self.indent(nesting)

    def sep_inter(self, nesting):
        self.insert(',\n')
        self.indent(nesting)

    def sep_terminal(self, nesting):
        self.insert('\n')
        self.indent(nesting - 1)

    def sep_keyval(self, nesting):
        self.insert(': ')

    def skip_sep(self):
        self.skip(r'\s*(,\s*)?')

    def skip_sep_bwd(self):
        self.skip_ws_bwd()
        if self.prec_char == ',':
            self.pos -= 1
            self.skip_ws_bwd()

    def erase_sep(self):
        beg = self.pos
        self.skip_sep()
        self.erase(beg)

    def erase_sep_bwd(self):
        beg = self.pos
        self.skip_sep_bwd()
        self.erase(beg)

    def consume(self, upto=None, upto_and_including=None):
        """Find specified pattern outside JS comment, string or brace nesting.

        If not found, raise UnexpectedContents.

        :return: True if met, False if encountered any kind of closing brace.
        """
        terminator = upto or upto_and_including
        include = upto_and_including is not None
        balance = 0
        re_target = '({})|({})'.format(re_of_interest, terminator)

        while True:
            reg = self.find(re_target)
            if reg.a == -1:
                raise UnexpectedContents(self, "not found the terminator {}", terminator)

            s = self.view.substr(reg)
            self.pos = reg.b

            if re.match(terminator, s):
                if balance == 0:
                    if not include:
                        self.pos = reg.a
                    return True
            elif s == '/*':
                self._skip_to_end_of_block_comment()
            elif s == '//':
                self._skip_to_newline()
            elif s == '/':
                # May be a regex. Check what precedes the current position
                if self._is_start_of_regex():
                    self._skip_to_end_of_regex()
            elif s in "\"'`":
                self._skip_to_end_of_string(s)
            elif s in '([{':
                balance += 1
            elif s in ')]}':
                if balance == 0:
                    self.pos = reg.a
                    return False
                else:
                    balance -= 1
            else:
                raise UnexpectedContents(self, "unexpected match: {}", s)

    def _skip_to_end_of_block_comment(self):
        reg = self.find(r'\*/')
        if reg.a == -1:
            raise UnexpectedContents(self, "not found the end of block comment")
        self.pos = reg.b

    def _skip_to_newline(self):
        reg = self.find('[\n]')
        if reg.a == -1:
            raise UnexpectedContents(self, "not found the newline")
        self.pos = reg.b

    def _skip_to_end_of_string(self, s):
        reg = self.find(r'(?<!\\)' + s)
        if reg.a == -1:
            raise UnexpectedContents(self, "unterminated string literal")
        self.pos = reg.b

    def _is_start_of_regex(self):
        with self.curpos_preserved():
            self.pos -= 1
            self.skip_ws_bwd()
            return self.prec_char in ",([{!~+-/*&|=:"

    def _skip_to_end_of_regex(self):
        while True:
            reg = self.find(r'\[|(?<!\\)/|\n')
            if reg.a == -1 or self.view.substr(reg) == '\n':
                raise UnexpectedContents(self, "Unterminated regex literal")
            self.pos = reg.b
            s = self.view.substr(reg)
            if s == '/':
                return
            
            # Skip character class
            assert s == '['
            reg = self.find(r'(?<!\\)]|\n')
            if reg.a == -1 or self.view.substr(reg) == '\n':
                raise UnexpectedContents(self, "Unterminated regex character class")
            self.pos = reg.b
