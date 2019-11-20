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
