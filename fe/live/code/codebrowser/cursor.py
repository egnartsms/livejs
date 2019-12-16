from live.code.cursor import Cursor as BaseCursor


class Cursor(BaseCursor):
    """Cursor with some CodeBrowser-specific bits of behavior added"""

    def sep_initial(self, nesting):
        if nesting == 0:
            pass
        else:
            super().sep_initial(nesting)

    def sep_inter(self, nesting):
        if nesting == 0:
            self.insert('\n\n')
        else:
            super().sep_inter(nesting)

    def sep_terminal(self, nesting):
        if nesting == 0:
            self.insert('\n')
        else:
            super().sep_terminal(nesting)

    def sep_keyval(self, nesting):
        if nesting == 0:
            self.insert(' = ')
        else:
            super().sep_keyval(nesting)
