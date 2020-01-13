import sublime

import json
from functools import partial

from live.util import first_such
from live.sublime_util.edit import call_with_edit
from live.comm import be_interaction, BackendError
from live.code.common import make_js_value_inserter, jsval_placeholder
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
    <div>
        <a href="">{contents}</a>
    </div>
</body>
'''


def render_phantom_html(is_expanded):
    return PHANTOM_HTML_TEMPLATE.format(
        contents='—' if is_expanded else '+'
    )


def add_phantom(view, region, on_navigate, is_expanded):
    return view.add_phantom('', region, render_phantom_html(is_expanded),
                            sublime.LAYOUT_INLINE, on_navigate)


class Node:
    def __init__(self, view, jsval, nesting, region):
        self.view = view
        self.nesting = nesting
        self.type = jsval['type']
        self.id = jsval['id']
        self.is_expanded = 'value' in jsval
        self.phid = None

        self._add_phantom(region)

    def _erase_phantom(self):
        assert self.phid is not None
        self.view.erase_phantom_by_id(self.phid)
        self.phid = None

    def _add_phantom(self, region):
        assert self.phid is None
        self.phid = add_phantom(self.view, region, self.on_navigate, self.is_expanded)

    def _collapse(self, edit):
        assert self.is_expanded
        [reg] = self.view.query_phantom(self.phid)
        self._erase_phantom()
        cur = Cursor(reg.a, self.view, edit)
        cur.erase(reg.b)
        cur.push_region()
        cur.insert(jsval_placeholder(self.type))
        self.is_expanded = False
        self._add_phantom(cur.pop_region())

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


class Unrevealed:
    """Unrevealed is used for getters (actual value is obtained lazily)

    Unrevealed instance is always collapsed. When expanded it's substituted with smth
    else, and the Unrevealed instance is gone forever.
    """

    def __init__(self, view, parent_id, prop, nesting, region):
        self.view = view
        self.parent_id = parent_id
        self.prop = prop
        self.nesting = nesting
        self.phid = add_phantom(self.view, region, self.on_navigate, False)

    @be_interaction
    def on_navigate(self, href):
        """Abandon this node and insert a new expanded one"""
        def impl(edit, jsval=None, error_info=None):
            [reg] = self.view.query_phantom(self.phid)
            self.view.erase_phantom_by_id(self.phid)
            self.phid = None
            self.view.erase(edit, reg)
            cur = Cursor(reg.a, self.view, edit)
            if jsval is not None:
                inserter = make_js_value_inserter(cur, jsval, self.nesting)
                insert_js_value(self.view, inserter)
            else:
                cur.insert("throw new {}({})".format(
                    error_info['excClassName'],
                    json.dumps(error_info['excMessage'])
                ))

        error_info = jsval = None

        try:
            jsval = yield 'inspectGetterValue', {
                'parentId': self.parent_id,
                'prop': self.prop
            }
        except BackendError as e:
            if e.name == 'getter_threw':
                error_info = e.info
            else:
                raise

        call_with_edit(self.view, partial(impl, error_info=error_info, jsval=jsval))


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
                # 1-line functions don't need to be collapsed
                nline_beg, _ = view.rowcol(args.region.a)
                nline_end, _ = view.rowcol(args.region.b)
                if nline_end > nline_beg:
                    Node(view, args.jsval, args.nesting, args.region)
            elif args.jsval['type'] == 'unrevealed':
                Unrevealed(view, args.jsval['parentId'], args.jsval['prop'],
                           args.nesting, args.region)
        else:
            assert 0, "Inserter yielded unexpected command: {}".format(cmd)

    insert_any(*next(inserter))
