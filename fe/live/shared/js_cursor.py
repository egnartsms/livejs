import contextlib
import re
import sublime

from copy import copy

from live.common.misc import tracking_last
from live.gstate import config
from live.shared.cursor import Cursor
from live.sublime.edit import edit_for


class UnexpectedContents(Exception):
    def __init__(self, cur, msg, *args):
        msg = msg.format(*args)
        msg = "Unexpected contents in {filepath} after {rowcol[0]}:{rowcol[1]}: {msg}"\
            .format(
                filepath=cur.view.file_name(),
                rowcol=cur.view.rowcol(cur.pos),
                msg=msg
            )
        super().__init__(msg)


re_any_brace = r'''[`'"()[\]{}]'''
re_line_comment = r'//'
re_block_comment = r'/\*'
re_of_interest = (
    '{re_any_brace}|{re_line_comment}|{re_block_comment}|/'.format(
        re_any_brace=re_any_brace,
        re_line_comment=re_line_comment,
        re_block_comment=re_block_comment
    )
)


class JsAwareCursor(Cursor):
    def js_go_upto(self, pattern, move_if_not_found=False):
        return self._js_go(pattern, False, move_if_not_found)

    def js_go_past(self, pattern, move_if_not_found=False):
        return self._js_go(pattern, True, move_if_not_found)

    def _js_go(self, pattern, including, move_if_not_found):
        """Find specified pattern outside JS comment, string or brace nesting.

        :return: True if met, False if encountered any kind of closing brace.
        """
        balance = 0
        re_target = '({})|({})'.format(re_of_interest, pattern)
        initial_pos = self.pos

        while True:
            reg = self.find(re_target)
            if reg.a == -1:
                if not move_if_not_found:
                    self.pos = initial_pos
                return False

            s = self.view.substr(reg)
            self.pos = reg.b

            if re.match(pattern, s):
                if balance == 0:
                    if not including:
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
                    self.pos = reg.a if move_if_not_found else initial_pos
                    return False
                else:
                    balance -= 1
            else:
                raise RuntimeError("Unexpected match: {}".format(s))

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
        with self.pos_preserved():
            self.pos -= 1
            self.skip_ws_bwd()
            return self.prec_char in ",([{!~+-/*&|=:"

    def _skip_to_end_of_regex(self):
        while True:
            reg = self.find(r'\[|(?<!\\)/|\n')
            if reg.a == -1 or self.view.substr(reg) == '\n':
                raise UnexpectedContents(self, "unterminated regex literal")
            self.pos = reg.b
            s = self.view.substr(reg)
            if s == '/':
                return
            
            # Skip character class
            assert s == '['
            reg = self.find(r'(?<!\\)]|\n')
            if reg.a == -1 or self.view.substr(reg) == '\n':
                raise UnexpectedContents(self, "unterminated regex character class")
            self.pos = reg.b


class StructuredCursor(JsAwareCursor):
    """Cursor that knows how to travel inside JS object and array literals
    
    container ::= { <init-space> Entry <inter-space> Entry ... Entry <term-space> }
    init-space, trailing-space ::= <whitespace>*
    inter-space ::= "," <whitespace>*
    """

    root_nesting = 0

    def __init__(self, pos, view, depth=0, is_inside_object=None, root_nesting=None):
        super().__init__(pos, view)
        self.depth = depth
        if is_inside_object is not None:
            self.is_inside_object = is_inside_object
        if root_nesting is not None:
            self.root_nesting = root_nesting

    @classmethod
    def at_module_root(cls, view):
        """Initialized to point at the root object"""
        cur = cls(0, view, depth=-1, is_inside_object=False, root_nesting=1)
        found = cur.go_past(r'let \$ = (?=\{)')
        if not found:
            raise RuntimeError

        return cur

    @classmethod
    def at_module_path(cls, view, path):
        cur = cls.at_module_root(view)

        for n in path:
            cur.enter()
            cur.goto_nth_entry(n)

        return cur

    @property
    def nesting(self):
        return self.root_nesting + self.depth
    
    @property
    def is_looking_at_container(self):
        return self.char in '[{'

    @property
    def is_looking_at_object(self):
        return self.char == '{'

    @property
    def is_looking_at_array(self):
        return self.char == '['

    @property
    def is_at_container_begin(self):
        return self.prec_char in '[{'

    @property
    def is_at_container_end(self):
        return self.char in ']}'

    def enter(self):
        # Enter the current entry (which must be a container)
        if self.is_inside_object:
            self.goto_object_value()
        if not self.is_looking_at_container:
            raise UnexpectedContents(self, "non-container follows")

        self.is_inside_object = self.is_looking_at_object
        self.pos += 1
        self.depth += 1

    def goto_next_entry(self):
        found = self.js_go_past(r',\s*')
        if not found:
            raise UnexpectedContents(self, "next entry not found")

    def goto_next_entry_or_end(self):
        self.js_go_past(r',\s*', move_if_not_found=True)

    def goto_nth_entry(self, n):
        if n == 0:
            self.skip_ws()
        else:
            while n > 0:
                self.goto_next_entry()
                n -= 1

    def goto_nth_entry_or_end(self, n):
        if n == 0:
            self.skip_ws()
            return

        if n > 1:
            self.goto_nth_entry(n - 1)
        
        self.goto_next_entry_or_end()        

    def goto_entry_end(self):
        found = self.js_go_upto(r',', move_if_not_found=True)
        if not found:
            self.skip_ws_bwd()

    def skip_sep_bwd(self):
        self.skip_ws_bwd()
        if self.prec_char == ',':
            self.pos -= 1

    def goto_object_value(self):
        found = self.js_go_past(r':\s*')
        if not found:
            raise UnexpectedContents(self, "malformed \"key: value\" entry")

    def skip_object_key(self):
        found = self.js_go_upto(r':')
        if not found:
            raise UnexpectedContents(self, "malformed \"key: value\" entry")

    def erase_object_key(self):
        assert self.is_inside_object
        self.push()
        self.skip_object_key()
        self.pop_erase()

    def erase_value(self):
        if self.is_inside_object:
            self.goto_object_value()
        self.push()
        self.goto_entry_end()
        self.pop_erase()

    def delete_entry(self):
        """Erase the entry we're looking at"""
        folw_beg = copy(self)
        folw_beg.goto_next_entry_or_end()

        if folw_beg.is_at_container_end:
            prec_end = copy(self)
            prec_end.skip_sep_bwd()
            if prec_end.is_at_container_begin:
                # We are the only node
                self.pos = prec_end.pos
                self.erase(folw_beg.pos)
            else:
                # We are the last node
                self.goto_entry_end()
                self.erase(prec_end.pos)
        else:
            self.erase(folw_beg.pos)

    def insert_initial_sep(self):
        self.insert('\n')
        self.indent(self.nesting + 1)

    def insert_inter_sep(self):
        self.insert(',\n')
        self.indent(self.nesting + 1)

    def insert_terminal_sep(self):
        self.insert('\n')
        self.indent(self.nesting)

    def insert_keyval_sep(self):
        self.insert(': ')

    def prepare_for_insertion_at(self, n):
        """Go to insertion position for nth child of the current entry (parent).

        This also inserts all necessary separators so the task of the caller remains to
        insert what actually has to be inserted by using self.
        """
        self.enter()
        self.goto_nth_entry_or_end(n)

        if self.is_at_container_end:
            if self.is_at_container_begin:
                # The only node
                self.insert_initial_sep()
                with self.pos_preserved():
                    self.insert_terminal_sep()
            else:
                # The last node
                self.skip_sep_bwd()
                self.insert_inter_sep()
        else:
            with self.pos_preserved():
                self.insert_inter_sep()

    def insert_function(self, source):
        # The last line of a function contains a single closing brace and is indented at
        # the same level as the whole function.  This of course depends on the formatting
        # style but it works for now and is very simple.
        i = source.rfind('\n') + 1
        n = 0
        while i + n < len(source) and ord(source[i + n]) == 32:
            n += 1

        line0, *lines = source.splitlines()
        
        self.insert(line0)
        if lines:
            self.insert('\n')

        for line, islast in tracking_last(lines):
            self.indent(self.nesting + 1)
            if not re.match(r'^\s*$', line):
                self.insert(line[n:])
            if not islast:
                self.insert('\n')

    def _forget_where_we_are(self):
        if hasattr(self, 'is_inside_object'):
            del self.is_inside_object

    def open_object(self):
        self.insert('{')
        self.depth += 1
        self.is_inside_object = True

    def close_object(self):
        self.insert('}')
        self.depth -= 1
        self._forget_where_we_are()

    def open_array(self):
        self.insert('[')
        self.depth += 1
        self.is_inside_object = False

    def close_array(self):
        self.insert(']')
        self.depth -= 1
        self._forget_where_we_are()

    def open(self, typ):
        if typ == 'object':
            self.open_object()
        elif typ == 'array':
            self.open_array()
        else:
            raise RuntimeError

    def close(self, typ):
        if typ == 'object':
            self.close_object()
        elif typ == 'array':
            self.close_array()
        else:
            raise RuntimeError

    @contextlib.contextmanager
    def laying_out(self, typ):
        self.open(typ)
        sep = SeparatorInserter(self)
        yield sep.insert
        sep.done()
        self.close(typ)


class SeparatorInserter:
    def __init__(self, cur):
        self.cur = cur
        self.inserted_initial = False

    def insert(self):
        if self.inserted_initial:
            self.cur.insert_inter_sep()
        else:
            self.cur.insert_initial_sep()
            self.inserted_initial = True

    def done(self):
        if self.inserted_initial:
            self.cur.insert_terminal_sep()
