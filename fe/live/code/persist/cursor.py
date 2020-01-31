from live.code.cursor import Cursor as BaseCursor
from live.code.cursor import UnexpectedContents
from live.gstate import config


ROOT_NESTING = 1

re_beginning = r'^[ ]{{{nspaces}}}.+?(?=\{{)'.format(nspaces=ROOT_NESTING * config.indent)


class Cursor(BaseCursor):
    def __init__(self, view):
        """Initialized to point right after the root object's opening brace"""
        super().__init__(0, view)
        self.depth = 0
        self.is_inside_object = False

        reg = self.find(re_beginning)
        if reg.a == -1:
            raise UnexpectedContents(self, "not found module object beginning")
        self.pos = reg.b
        self.enter()

    def sep_inter(self, nesting):
        """If at top level, separate entries with two newlines instead of one"""
        self.insert(',\n')
        if nesting == ROOT_NESTING + 1:
            self.insert('\n')
        self.indent(nesting)

    @property
    def is_at_container_begin(self):
        return self.char in '[{'

    @property
    def is_at_container_end(self):
        return self.char in ']}'

    def enter(self):
        if not self.is_at_container_begin:
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
            return not self.is_at_container_end
        else:
            return False

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

    def moveto_nth_entry_or_end(self, n):
        self.skip_ws()
        if self.is_at_container_end:
            return False
        while n > 0:
            found = self.moveto_next_entry_or_end()
            if not found:
                return False
            n -= 1
        return True

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
    def at_key(cls, path, view):
        path, nlast = path[:-1], path[-1]
        cur = cls.at_entry_start(path, view)
        cur.moveto_nth_key(nlast)
        return cur

    @classmethod
    def at_value(cls, path, view):
        path, nlast = path[:-1], path[-1]
        cur = cls.at_entry_start(path, view)
        cur.moveto_nth_value(nlast)
        return cur

    @classmethod
    def at_entry(cls, path, view):
        path, nlast = path[:-1], path[-1]
        cur = cls.at_entry_start(path, view)
        cur.moveto_nth_entry(nlast)
        return cur

    @classmethod
    def at_entry_or_end(cls, path, view):
        path, nlast = path[:-1], path[-1]
        cur = cls.at_entry_start(path, view)
        found = cur.moveto_nth_entry_or_end(nlast)
        return cur, found

    @classmethod
    def at_entry_start(cls, path, view):
        cur = cls(view)

        for n in path:
            cur.moveto_nth_value(n)
            cur.enter()

        return cur
