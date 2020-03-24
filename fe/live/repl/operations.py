import json
import sublime

from .repl import Repl
from live.code.common import jsval_placeholder
from live.code.common import make_js_value_inserter
from live.common.misc import first_or_none
from live.common.misc import gen_uid
from live.settings import setting
from live.shared.backend import interacts_with_backend
from live.shared.cursor import Cursor
from live.shared.js_cursor import StructuredCursor
from live.sublime.edit import edit_for
from live.sublime.edit import edits_self_view
from live.sublime.view_info import view_info_getter
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
    view.assign_syntax('Packages/LiveJS/syntax/repl/JavaScript.sublime-syntax')

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
    def __init__(self, view, jsval, depth, region):
        self.view = view
        self.depth = depth
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
            cur = Cursor(reg.a, self.view)
            cur.erase(reg.b)
            cur.push()
            cur.insert(jsval_placeholder(self.type))

        self.is_expanded = False
        self._add_phantom(cur.pop_region())

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
            cur = StructuredCursor(reg.a, self.view, depth=self.depth)
            insert_js_value(cur, jsval)

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

    def __init__(self, view, parent_id, prop, depth, region):
        self.view = view
        self.parent_id = parent_id
        self.prop = prop
        self.depth = depth
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
            cur = StructuredCursor(reg.a, self.view, depth=self.depth)
            if jsval is not None:
                insert_js_value(cur, jsval)
            else:
                cur.insert("throw new {}({})".format(
                    error.exc_class_name,
                    json.dumps(error.exc_message)
                ))


def insert_js_value(cur, jsval):
    """Create Node instances which are inaccessible as of now.

    They exist only for the sake of phantoms, and get GCed when we delete phantoms.
    """
    def insert_object(obj):
        with cur.laying_out('object') as separate:
            for key, value in obj.items():
                separate()
                cur.insert(key)
                cur.insert_keyval_sep()
                insert_any(value)

    def insert_array(arr):
        with cur.laying_out('array') as separate:
            for value in arr:
                separate()
                insert_any(value)

    def insert_any(jsval):
        if jsval['type'] == 'object':
            cur.push()
            if 'value' in jsval:
                insert_object(jsval['value'])
            else:
                cur.insert(jsval_placeholder('object'))
            Node(cur.view, jsval, cur.depth, cur.pop_region())
        elif jsval['type'] == 'array':
            cur.push()
            if 'value' in jsval:
                insert_array(jsval['value'])
            else:
                cur.insert(jsval_placeholder('array'))
            Node(cur.view, jsval, cur.depth, cur.pop_region())
        elif jsval['type'] == 'function':
            need_node = False

            cur.push()
            if 'value' in jsval:
                cur.insert_function(jsval['value'])
            else:
                cur.insert(jsval_placeholder('function'))
                need_node = True
            reg = cur.pop_region()

            if not need_node:
                # 1-line functions don't need to be collapsed
                nline_beg, _ = cur.view.rowcol(reg.a)
                nline_end, _ = cur.view.rowcol(reg.b)
                need_node = nline_end > nline_beg
            
            if need_node:
                Node(cur.view, jsval, cur.depth, reg)
        elif jsval['type'] == 'unrevealed':
            cur.push()
            cur.insert(jsval_placeholder('unrevealed'))
            reg = cur.pop_region()
            Unrevealed(cur.view, jsval['parentId'], jsval['prop'], cur.depth, reg)
        elif jsval['type'] == 'leaf':
            cur.insert(jsval['value'])
        else:
            raise RuntimeError("Unexpected jsval: {}".format(jsval))

    insert_any(jsval)


def jsval_placeholder(jsval_type):
    if jsval_type == 'object':
        return "{...}"
    elif jsval_type == 'array':
        return "[...]"
    elif jsval_type == 'function':
        return "func {...}"
    elif jsval_type == 'unrevealed':
        return "(...)"
    else:
        raise RuntimeError
