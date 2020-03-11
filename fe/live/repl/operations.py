import json
import sublime

from .repl import Repl
from live.code.common import jsval_placeholder
from live.code.common import make_js_value_inserter
from live.code.cursor import Cursor
from live.shared.backend import interacts_with_backend
from live.settings import setting
from live.sublime_util.edit import edit_for
from live.sublime_util.edit import edits_self_view
from live.sublime_util.view_info import view_info_getter
from live.util.misc import first_or_none
from live.util.misc import gen_uid
from live.ws_handler import GetterThrewError
from live.ws_handler import ws_handler


def is_view_repl(view):
    return setting.view[view] == 'REPL'


def find_repl_view(window):
    return first_or_none(view for view in window.views() if is_view_repl(view))


def new_repl_view(window, module):
    view = window.new_file()
    setting.view[view] = 'REPL'
    view.set_name('LiveJS: REPL')
    view.set_scratch(True)
    view.assign_syntax('Packages/LiveJS/LiveJS REPL.sublime-syntax')

    repl = repl_for(view)
    repl.set_current_module(module)
    repl.inspection_space_id = gen_uid()
    
    repl.erase_all_insert_prompt()

    return view


repl_for = view_info_getter(Repl, is_view_repl)


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

    @property
    def repl(self):
        return repl_for(self.view)

    def _erase_phantom(self):
        assert self.phid is not None
        self.view.erase_phantom_by_id(self.phid)
        self.phid = None

    def _add_phantom(self, region):
        assert self.phid is None
        self.phid = add_phantom(self.view, region, self.on_navigate, self.is_expanded)

    @edits_self_view
    def _collapse(self):
        assert self.is_expanded

        [reg] = self.view.query_phantom(self.phid)
        self._erase_phantom()

        with self.repl.region_editing_off_then_reestablished():
            cur = Cursor(reg.a, self.view, inter_sep_newlines=1)
            cur.erase(reg.b)
            cur.push()
            cur.insert(jsval_placeholder(self.type))

        self.is_expanded = False
        self._add_phantom(cur.pop_reg_beg())

    @interacts_with_backend(edits_view=lambda self: self.view)
    def _expand(self):
        """Abandon this node and insert a new expanded one"""
        assert not self.is_expanded

        ws_handler.run_async_op('inspectObjectById', {
            'spaceId': self.repl.inspection_space_id,
            'id': self.id
        })
        jsval = yield 
        
        [reg] = self.view.query_phantom(self.phid)
        self._erase_phantom()

        with self.repl.region_editing_off_then_reestablished():
            self.view.erase(edit_for[self.view], reg)
            cur = Cursor(reg.a, self.view, inter_sep_newlines=1)
            inserter = make_js_value_inserter(cur, jsval, self.nesting)
            insert_js_value(self.view, inserter)

    def on_navigate(self, href):
        if self.is_expanded:
            self._collapse()
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

    @property
    def repl(self):
        return repl_for(self.view)

    @interacts_with_backend(edits_view=lambda self: self.view)
    def on_navigate(self, href):
        """Abandon this node and insert a new expanded one"""
        error = jsval = None

        try:
            ws_handler.run_async_op('inspectGetterValue', {
                'spaceId': self.repl.inspection_space_id,
                'parentId': self.parent_id,
                'prop': self.prop
            })
            jsval = yield
        except GetterThrewError as e:
            error = e

        [reg] = self.view.query_phantom(self.phid)
        self.view.erase_phantom_by_id(self.phid)
        self.phid = None
        
        with self.repl.region_editing_off_then_reestablished():
            self.view.erase(edit_for[self.view], reg)
            cur = Cursor(reg.a, self.view, inter_sep_newlines=1)
            if jsval is not None:
                inserter = make_js_value_inserter(cur, jsval, self.nesting)
                insert_js_value(self.view, inserter)
            else:
                cur.insert("throw new {}({})".format(
                    error.exc_class_name,
                    json.dumps(error.exc_message)
                ))


def insert_js_value(view, inserter):
    """Create Node instances which are inaccessible as of now.

    They exist only for the sake of phantoms, and get GCed when we deleted phantoms.
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
