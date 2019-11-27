import re

import sublime
import sublime_plugin


from live.sublime_util.cursor import Cursor
from live.util import tracking_last
from live.code.common import make_js_value_inserter


re_toplevel_before_key = r'^\s{nesting}\$\.'
re_toplevel = re_toplevel_before_key + r'([^=]+)\s*='
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
        self.re_toplevel_before_key = \
            re_toplevel_before_key.replace('nesting', str(self.nesting))
        self.re_toplevel = re_toplevel.replace('nesting', str(self.nesting))

    def goto_nth_toplevel(self, n):
        regs = self.view.find_all(self.re_toplevel)
        if n >= len(regs):
            raise UnexpectedContents(self, "Could not move to toplevel #{} "
                                           "(only {} in total)".format(n, len(regs)))
        self.pos = regs[n].a

    def goto_cur_toplevel_value(self):
        self.skip_re(self.re_toplevel)
        self.skip_ws()

    def goto_cur_toplevel_key(self):
        self.skip_re(self.re_toplevel_before_key)

    def skip_to_nth_value(self, n):
        if self.char not in ('{', '['):
            raise UnexpectedContents(self, "Expected object or array")

        is_object = self.char == '{'
        self.pos += 1

        for _ in range(n):
            self.consume(',', inc=True)

        if is_object:
            self.consume(':', inc=True)

        self.skip_ws()

    def skip_to_nth_key(self, n):
        if self.char != '{':
            raise UnexpectedContents(self, "Expected object")

        self.pos += 1

        for _ in range(n):
            self.consume(',', inc=True)

        self.skip_ws()

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


def edit(view, edit, path, new_value):
    cur = CodePersistCursor(0, view, edit)
    ntoplevel, *path = path
    cur.goto_nth_toplevel(ntoplevel)
    cur.goto_cur_toplevel_value()

    for n in path:
        cur.skip_to_nth_value(n)

    beg = cur.pos
    cur.consume(',|;', inc=False)
    cur.erase(beg)
    
    itr = make_js_value_inserter(cur, new_value, len(path))
    while next(itr, None):
        pass

    # Just saving does not work, we have to do it after the current command completes
    sublime.set_timeout(lambda: view.run_command('save'), 0)


def rename_key(view, edit, path, new_name):
    cur = CodePersistCursor(0, view, edit)
    ntoplevel, *path = path
    cur.goto_nth_toplevel(ntoplevel)
    if not path:
        cur.goto_cur_toplevel_key()
    else:
        cur.goto_cur_toplevel_value()
        path, nlast = path[:-1], path[-1]
        for n in path:
            cur.skip_to_nth_value(n)
        cur.skip_to_nth_key(nlast)

    beg = cur.pos
    cur.skip_re(r'[a-zA-Z0-9_]+')
    cur.erase(beg)
    cur.insert(new_name)

    # Just saving does not work, we have to do it after the current command completes
    sublime.set_timeout(lambda: view.run_command('save'), 0)
