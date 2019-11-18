import sublime


class Cursor:
    def __init__(self, pos, view, edit=None):
        self.pos = pos
        self.view = view
        self.edit = edit

    def insert(self, s):
        n_ins = self.view.insert(self.edit, self.pos, s)
        self.pos += n_ins

    def erase(self, upto):
        self.view.erase(self.edit, sublime.Region(self.pos, upto))
