import re

import sublime
import sublime_plugin


from live.sublime_util.cursor import Cursor
from live.util import tracking_last
from live.code.common import inserting_js_value


re_toplevel = r'^\s{nesting}\$\.([^=]+)\s*='
re_any_brace = r'''[`'"()[\]{}]'''
re_line_comment = r'//'
re_block_comment = r'/\*'
re_of_interest = (
    '{re_any_brace}|{re_line_comment}|{re_block_comment}|/'.format(**globals())
)


class CodePersistCursor(Cursor):
    def __init__(self, pos, view, edit=None):
        super().__init__(pos, view, edit)
        self.nesting = self.view.settings().get('tab_size')
        self.re_toplevel = re_toplevel.replace('nesting', str(self.nesting))

    def next_toplevel(self):
        reg = self.find(self.re_toplevel)
        if reg.a == -1:
            raise UnexpectedContents(self, "Could not move to next toplevel")
        self.pos = reg.a
        return reg

    def skipws(self):
        reg = self.find(r'\S')
        if reg.a == -1:
            self.pos = self.view.size()
        else:
            self.pos = reg.a

    def consume(self, terminator, inc):
        balance = 0

        re_target = '({})|({})'.format(re_of_interest, terminator)

        while True:
            reg = self.find(re_target)
            if reg.a == -1:
                raise UnexpectedContents(self, "Not found the terminator {}", terminator)

            s = self.view.substr(reg)
            self.pos = reg.b

            if re.match(terminator, s):
                if balance == 0:
                    if not inc:
                        self.pos = reg.a
                    break
                else:
                    pass
            elif s == '/*':
                self._skip_to_end_of_block_comment()
            elif s == '//':
                self._skip_to_newline()
            elif s.endswith('/'):
                # May be a regex. Check what precedes the current position
                if self._is_start_of_regex():
                    self._skip_to_end_of_regex()
                else:
                    pass
            elif s in "\"'`":
                self._skip_to_end_of_string(s)
            elif s in '([{':
                balance += 1
            elif s in ')]}':
                if balance == 0:
                    self.pos = reg.a
                    break
                else:
                    balance -= 1
            else:
                raise UnexpectedContents(self, "Unexpected match: {}", s)

    def _skip_to_end_of_block_comment(self):
        reg = self.find(r'\*/')
        if reg.a == -1:
            raise UnexpectedContents(self, "Not found the end of block comment")
        self.pos = reg.b

    def _skip_to_newline(self):
        reg = self.find('[\n]')
        if reg.a == -1:
            raise UnexpectedContents(self, "Not found the newline")
        self.pos = reg.b

    def _skip_to_end_of_string(self, s):
        reg = self.find(r'(?<!\\)' + s)
        if reg.a == -1:
            raise UnexpectedContents(self, "Unterminated string literal")
        self.pos = reg.b

    def _is_start_of_regex(self):
        reg = self.view.line(self.pos)
        line = self.view.substr(sublime.Region(reg.a, self.pos - 1))[::-1]
        return bool(re.match(r'\s*([,([{!~+-/*&|=:]|$)', line))

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


class UnexpectedContents(Exception):
    def __init__(self, cur, msg, *args):
        msg = msg.format(*args)
        super().__init__("Unexpected contents after pos {}: {}".format(cur.pos, msg))


def handle_edit_action(view, edit, path, new_value):
    path = path.components  # TODO: make this normal
    cur = CodePersistCursor(0, view, edit)
    reg = cur.next_toplevel()
    for i in range(path[0]):
        cur.pos += 1  # to force the current toplevel not to be found again
        reg = cur.next_toplevel()

    cur.pos = reg.b
    cur.skipws()

    for n in path[1:]:
        if cur.char not in ('{', '['):
            raise UnexpectedContents(cur, "Expected object or array")

        is_object = cur.char == '{'
        cur.pos += 1

        for _ in range(n):
            if is_object:
                cur.consume(':', inc=True)
            cur.consume(',', inc=True)

        if is_object:
            cur.consume(':', inc=True)

        cur.skipws()

    beg = cur.pos
    cur.consume(',|;', inc=False)
    cur.erase(beg)
    
    itr = inserting_js_value(cur, new_value, len(path))
    while next(itr, None):
        pass

    # Just saving does not work, we have to do it after the current command completes
    sublime.set_timeout(lambda: view.run_command('save'), 0)
