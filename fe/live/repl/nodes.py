import sublime

from live.util import eraise
from live.sublime_util.technical_command import run_technical_command
from live.code.cursor import Cursor


PHANTOM_HTML_TEMPLATE = '''
<body id="casual">
   <style>
     a {{
        display: block;
        text-decoration: none;
     }}
   </style>
   <a href="">{contents}</a>
</body>
'''


def render_phantom_html(is_expanded):
    return PHANTOM_HTML_TEMPLATE.format(
        contents='—' if is_expanded else '+'
    )


class Node:
    def __init__(self, view, jsval, region):
        self.view = view
        self.type = jsval['type']
        self.id = jsval.get('id', None)  # missing for functions
        self.is_expanded = 'value' in jsval
        self.phid = None

        self._add_phantom(region)

    def collapsed_placeholder(self):
        if self.type == 'object':
            return "{...}"
        elif self.type == 'array':
            return "[...]"
        elif self.type == 'function':
            return "func () {...}"
        else:
            assert 0

    def _erase_phantom(self):
        assert self.phid is not None
        self.view.erase_phantom_by_id(self.phid)
        self.phid = None

    def _add_phantom(self, region):
        assert self.phid is None
        self.phid = self.view.add_phantom(
            '', region, render_phantom_html(self.is_expanded), sublime.LAYOUT_INLINE,
            self.on_navigate
        )

    def _collapse(self, edit):
        assert self.is_expanded
        [reg] = self.view.query_phantom(self.phid)
        self._erase_phantom()
        placeholder = self.collapsed_placeholder()
        self.view.replace(edit, reg, placeholder)
        self.is_expanded = False
        self._add_phantom(sublime.Region(reg.a, reg.a + len(placeholder)))

    def on_navigate(self, href):
        if self.is_expanded:
            run_technical_command(self.view, self._collapse)
        else:
            raise NotImplementedError
