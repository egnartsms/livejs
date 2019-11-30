import sublime
import sublime_plugin

from live.config import config
from live.code.cursor import Cursor, UnexpectedContents


ROOT_NESTING = 1

re_beginning = r'^[ ]{{{nspaces}}}.+?(?=\{{)'.format(nspaces=ROOT_NESTING * config.indent)


class PersistCursor(Cursor):
    """Initialized to point right after the root object's opening brace"""

    def __init__(self, view, edit):
        super().__init__(0, view, edit)
        self.depth = 0
        self.is_inside_object = False

        reg = self.find(re_beginning)
        if reg.a == -1:
            raise UnexpectedContents(self, "not found module object beginning")
        self.pos = reg.b
        self.enter()

    def enter(self):
        if self.char not in '[{':
            raise UnexpectedContents(self, "cannot enter smth which is neither array nor "
                                           "object")
        self.is_inside_object = self.char == '{'
        self.pos += 1
        self.depth += 1

    def moveto_entry_end(self):
        self.consume(upto=r',')
        self.skip_ws_bwd()

    def moveto_next_entry_or_end(self):
        found = self.consume(upto_and_including=r',')
        if found:
            self.skip_ws()

    def moveto_next_entry(self):
        found = self.consume(upto_and_including=r',')
        if not found:
            raise UnexpectedContents(self, "next entry not found")
        self.skip_ws()

    def moveto_nth_entry(self, n):
        self.skip_ws()
        while n > 0:
            self.moveto_next_entry()
            n -= 1

    def moveto_nth_key(self, n):
        if not self.is_inside_object:
            raise UnexpectedContents(self, "cannot go to a key, not inside an object")
        self.moveto_nth_entry(n)

    def moveto_nth_value(self, n):
        self.moveto_nth_entry(n)

        if self.is_inside_object:
            self.skip_propname()

    def skip_propname(self):
        self.skip(r'\S+?:\s*')

    @classmethod
    def at_key(cls, path, view, edit):
        path, nlast = path[:-1], path[-1]
        cur = cls.at_entry_start(path, view, edit)
        cur.moveto_nth_key(nlast)
        return cur

    @classmethod
    def at_value(cls, path, view, edit):
        path, nlast = path[:-1], path[-1]
        cur = cls.at_entry_start(path, view, edit)
        cur.moveto_nth_value(nlast)
        return cur

    @classmethod
    def at_entry(cls, path, view, edit):
        path, nlast = path[:-1], path[-1]
        cur = cls.at_entry_start(path, view, edit)
        cur.moveto_nth_entry(nlast)
        return cur

    @classmethod
    def at_entry_start(cls, path, view, edit):
        cur = cls(view, edit)

        for n in path:
            cur.moveto_nth_value(n)
            cur.enter()

        return cur
