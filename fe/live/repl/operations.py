import sublime

import collections
import json

from live.util import first_such
from live.sublime_util.edit import call_with_edit
from live.comm import be_interaction
from live.code.common import make_js_value_inserter
from live.code.cursor import Cursor


def find_repl(window):
    return first_such(
        view for view in window.views()
        if view.settings().get('livejs_view') == 'REPL'
    )


def new_repl(window):
    repl = window.new_file()
    repl.settings().set('livejs_view', 'REPL')
    repl.set_name('LiveJS: REPL')
    repl.set_scratch(True)
    repl.assign_syntax('Packages/LiveJS/LiveJS REPL.sublime-syntax')
    return repl


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
    def __init__(self, view, jsval, nesting, region):
        self.view = view
        self.nesting = nesting
        self.type = jsval['type']
        self.id = jsval['id']
        self.is_expanded = 'value' in jsval
        self.phid = None

        self._add_phantom(region)

    def _collapsed_placeholder(self):
        if self.type == 'object':
            return "{...}"
        elif self.type == 'array':
            return "[...]"
        elif self.type == 'function':
            return "func {...}"
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
        placeholder = self._collapsed_placeholder()
        self.view.replace(edit, reg, placeholder)
        self.is_expanded = False
        self._add_phantom(sublime.Region(reg.a, reg.a + len(placeholder)))

    @be_interaction
    def _expand(self):
        """Abandon this node and insert a new expanded one"""
        assert not self.is_expanded
        jsval = yield 'inspectObjectById', {'id': self.id}
        
        def impl(edit):
            [reg] = self.view.query_phantom(self.phid)
            self._erase_phantom()
            self.view.erase(edit, reg)
            cur = Cursor(reg.a, self.view, edit)
            inserter = make_js_value_inserter(cur, jsval, self.nesting)
            insert_js_value(self.view, inserter)

        call_with_edit(self.view, impl)

    def on_navigate(self, href):
        if self.is_expanded:
            call_with_edit(self.view, self._collapse)
        else:
            self._expand()


def insert_js_value(view, inserter):
    """Create Node instances which are inaccessible as of now.

    They exist only for the sake of phantoms
    """
    def insert_object():
        while True:
            cmd, args = next(inserter)
            if cmd == 'pop':
                Node(view, args.jsval, args.nesting, args.region)
                return

            insert_any(*next(inserter))

    def insert_array():
        while True:
            cmd, args = next(inserter)
            if cmd == 'pop':
                Node(view, args.jsval, args.nesting, args.region)
                return

            insert_any(cmd, args)

    def insert_any(cmd, args):
        if cmd == 'push_object':
            insert_object()
        elif cmd == 'push_array':
            insert_array()
        elif cmd == 'leaf':
            if args.jsval['type'] == 'function':
                Node(view, args.jsval, args.nesting, args.region)
        else:
            assert 0, "Inserter yielded unexpected command: {}".format(cmd)

    insert_any(*next(inserter))
