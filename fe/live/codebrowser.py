import re
from collections import OrderedDict
import operator as pyop
from functools import partial

import sublime_plugin
import sublime

from live import server
from live.config import config
from live.util import tracking_last, first_such
from live.technical_command import thru_technical_command
from live.sublime_util import Cursor


__all__ = ['PerViewInfoDiscarder', 'LivejsCbRefresh', 'LivejsCbEdit', 'LivejsCbCommit',
           'CodeBrowserEventListener']


def path_join(path, n):
    if path:
        return '{}.{}'.format(path, n)
    else:
        return str(n)


class JsNode:
    is_leaf = None   # to be overriden by subclasses

    def __init__(self):
        super().__init__()
        self.parent = None

    @property
    def is_root(self):
        return self.parent is None

    @property
    def num(self):
        assert not self.is_root
        return self.parent.index(self)

    @property
    def nesting(self):
        if self.is_root:
            return 0
        else:
            return 1 + self.parent.nesting

    @property
    def path(self):
        components = []
        node = self
        while not node.is_root:
            components.append(node.num)
            node = node.parent

        components.reverse()
        return components

    @property
    def dotpath(self):
        return '.'.join(map(str, self.path))

    def span(self, view):
        assert not self.is_root
        return view.get_regions(self.parent.key_reg_children)[self.num]

    def begin(self, view):
        assert not self.is_root
        return self.span(view).a

    def end(self, view):
        assert not self.is_root
        return self.span(view).b


class JsInterior(JsNode, list):
    is_leaf = False
    
    def __init__(self, is_object):
        super().__init__()
        self.is_object = is_object
    
    @property
    def key_reg_keys(self):
        assert self.is_object
        return path_join(self.dotpath, 'keys')
    
    @property
    def key_reg_values(self):
        assert self.is_object
        return path_join(self.dotpath, 'values')

    @property
    def key_reg_items(self):
        assert not self.is_object
        return path_join(self.dotpath, 'items')

    @property
    def key_reg_children(self):
        return self.key_reg_values if self.is_object else self.key_reg_items

    def append_child(self, jsnode):
        jsnode.parent = self
        self.append(jsnode)

    def human_readable(self):
        if self.is_object:
            return '{' + ','.join([x.human_readable() for x in self]) + '}'
        else:
            return '[' + ','.join([x.human_readable() for x in self]) + ']'

    def __repr__(self):
        return '#<jsnode: {}>'.format(self.human_readable())


class JsLeaf(JsNode):
    is_leaf = True

    def human_readable(self):
        return 'x'

    def __repr__(self):
        return '#<jsleaf>'


per_view = dict()


class ViewInfo:
    root = None
    jsnode_being_edited = None

    def __init__(self):
        pass


def info_for(view):
    vid = view.id()
    if vid not in per_view:
        per_view[vid] = ViewInfo()

    return per_view[vid]


class PerViewInfoDiscarder(sublime_plugin.EventListener):
    def on_close(self, view):
        vid = view.id()
        if vid in per_view:
            del per_view[vid]


def reset(view, edit, response):
    root = info_for(view).root
    if root is not None:
        erase_regions(view, root)

    view.set_read_only(False)
    view.erase(edit, sublime.Region(0, view.size()))
    cur = Cursor(0, view, edit)
    
    root = JsInterior(is_object=True)
    reg_keys, reg_values = [], []

    for key, value in response:
        x0 = cur.pos
        cur.insert(key)
        x1 = cur.pos
        reg_keys.append(sublime.Region(x0, x1))

        cur.insert(' =\n')

        x0 = cur.pos
        insert_js_unit(cur, value, root)
        x1 = cur.pos
        reg_values.append(sublime.Region(x0, x1))
        
        cur.insert('\n\n')

    view.add_regions(root.key_reg_keys, reg_keys, '', '', sublime.HIDDEN)
    view.add_regions(root.key_reg_values, reg_values, '', '', sublime.HIDDEN)

    info_for(view).root = root

    view.set_read_only(True)
    view.window().focus_view(view)


def insert_js_unit(cur, obj, parent):
    nesting = parent.nesting

    def indent():
        cur.insert(config.s_indent * nesting)

    def insert_unit(obj, parent):
        if isinstance(obj, list):
            return insert_array(obj, parent)
        
        assert isinstance(obj, OrderedDict), "Got non-dict: {}".format(obj)
        leaf = obj.get('__leaf_type__')
        if leaf == 'js-value':
            cur.insert(obj['value'])
            parent.append_child(JsLeaf())
        elif leaf == 'function':
            insert_function(obj['value'])
            parent.append_child(JsLeaf())
        else:
            assert leaf is None
            insert_object(obj, parent)

    def insert_array(arr, parent):
        nonlocal nesting

        reg_items, jsnode = [], JsInterior(is_object=False)
        parent.append_child(jsnode)

        if not arr:
            cur.insert("[]")
            return jsnode

        cur.insert("[\n")
        nesting += 1
        for item in arr:
            indent()
            x0 = cur.pos
            insert_unit(item, jsnode)
            x1 = cur.pos
            reg_items.append(sublime.Region(x0, x1))

            cur.insert(",\n")
        nesting -= 1
        indent()
        cur.insert("]")

        cur.view.add_regions(jsnode.key_reg_items, reg_items, '', '', sublime.HIDDEN)

    def insert_object(obj, parent):
        nonlocal nesting

        reg_keys, reg_values, jsnode = [], [], JsInterior(is_object=True)
        parent.append_child(jsnode)

        if not obj:
            cur.insert("{}")
            return jsnode

        cur.insert("{\n")
        nesting += 1
        for k, v in obj.items():
            indent()
            x0 = cur.pos
            cur.insert(k)
            x1 = cur.pos
            reg_keys.append(sublime.Region(x0, x1))

            cur.insert(': ')
            x0 = cur.pos
            insert_unit(v, jsnode)
            x1 = cur.pos
            reg_values.append(sublime.Region(x0, x1))

            cur.insert(',\n')
        nesting -= 1
        indent()
        cur.insert("}")

        cur.view.add_regions(jsnode.key_reg_keys, reg_keys, '', '', sublime.HIDDEN)
        cur.view.add_regions(jsnode.key_reg_values, reg_values, '', '', sublime.HIDDEN)

    def insert_function(source):
        # The last line of a function contains a single closing brace and is indented at
        # the same level as the whole function.  This of course depends on the formatting
        # style but it works for now and is very simple.
        i = source.rfind('\n')
        if i == -1:
            pass

        i += 1
        n = 0
        while i + n < len(source) and ord(source[i + n]) == 32:
            n += 1

        line0, *lines = source.splitlines()
        
        cur.insert(line0)
        cur.insert('\n')
        for line, islast in tracking_last(lines):
            indent()
            if not re.match(r'^\s*$', line):
                cur.insert(line[n:])
            if not islast:
                cur.insert('\n')

    insert_unit(obj, parent)


def erase_regions(view, jsnode):
    def erase(node):
        if node.is_leaf:
            return

        for subnode in node:
            erase(subnode)

        if node.is_object:
            view.erase_regions(node.key_reg_keys)
            view.erase_regions(node.key_reg_values)
        else:
            view.erase_regions(node.key_reg_items)

    erase(jsnode)


def find_containing_leaf(view, x):
    node = info_for(view).root
    reg = None

    while not node.is_leaf:
        if node.is_object:
            regs = view.get_regions(node.key_reg_values)
        else:
            regs = view.get_regions(node.key_reg_items)

        assert len(regs) == len(node)

        for subreg, subnode in zip(regs, node):
            if subreg.contains(x):
                node = subnode
                reg = subreg
                break
        else:
            return None, None

    return node, reg


##########
# Commands
CODE_BROWSER_VIEW_NAME = "LiveJS: Code Browser"


class LivejsCbRefresh(sublime_plugin.WindowCommand):
    def run(self):
        if server.websocket is None:
            sublime.error_message("BE did not connect yet")
            return

        cbv = first_such(view for view in self.window.views()
                         if view.settings().get('livejs_view') == 'Code Browser')
        if cbv is None:
            cbv = self.window.new_file()
            cbv.settings().set('livejs_view', 'Code Browser')
            cbv.set_name(CODE_BROWSER_VIEW_NAME)
            cbv.set_scratch(True)
            cbv.set_syntax_file('Packages/JavaScript/JavaScript.sublime-syntax')

        server.response_callbacks.append(thru_technical_command(cbv, reset))
        server.websocket.enqueue_message('$.sendAllEntries()')


class CodeBrowserEventListener(sublime_plugin.ViewEventListener):
    @classmethod
    def is_applicable(cls, settings):
        return settings.get('livejs_view') == 'Code Browser'

    @classmethod
    def applies_to_primary_view_only(cls):
        return True

    def on_query_context(self, key, operator, operand, match_all):
        if key != 'livejs_view':
            return None
        if operator not in (sublime.OP_EQUAL, sublime.OP_NOT_EQUAL):
            return False
        
        op = pyop.eq if operator == sublime.OP_EQUAL else pyop.ne
        return op(self.view.settings().get('livejs_view'), operand)


class LivejsCbEdit(sublime_plugin.TextCommand):
    def run(self, edit):
        if len(self.view.sel()) != 1:
            self.view.window().status_message(">1 cursors")
            return

        r0 = self.view.sel()[0]
        if r0.size() > 0:
            self.view.window().status_message("must not select any regions")
            return

        obj, reg = find_containing_leaf(self.view, r0.b)
        if obj is None:
            self.view.window().status_message("not inside a leaf")
            return

        info_for(self.view).jsnode_being_edited = obj
        self.view.add_regions('being_edited', [reg], 'region.greenish', '',
                              sublime.DRAW_NO_FILL | sublime.DRAW_EMPTY)
        self.view.sel().clear()
        self.view.sel().add(reg)
        self.view.set_read_only(False)


class LivejsCbCommit(sublime_plugin.TextCommand):
    def run(self, edit):
        jsnode = info_for(self.view).jsnode_being_edited
        [reg] = self.view.get_regions('being_edited')

        JSCODE = '''$.edit({}, (function () {{ return ({}); }}));'''.format(
            jsnode.path, self.view.substr(reg)
        )
        server.response_callbacks.append(partial(on_committed, view=self.view))
        server.websocket.enqueue_message(JSCODE)
        self.view.set_status('pending', "LiveJS: back-end is processing..")


def on_committed(view, response):
    print("Successfully committed!")

    view.erase_status('pending')
    info_for(view).jsnode_being_edited = None
    view.erase_regions('being_edited')
    view.set_read_only(True)


def action_handler_edit(action):
    cbv = first_such(view for view in sublime.active_window().views()
                     if view.settings().get('livejs_view') == 'Code Browser')
    thru_technical_command(cbv, edit_change_view)(action=action)


def edit_change_view(view, edit, action):
    path, new_value = action['path'], action['newValue']
    
    assert path == info_for(view).jsnode_being_edited.path

    jsnode = info_for(view).jsnode_being_edited
    span = jsnode.span(view)
    erase_regions(view, jsnode)
    view.erase(edit, span)
    n = jsnode.num
    # We temporarily remove all the jsnode's siblings that go after it, then re-add
    following_siblings = jsnode.parent[n + 1:]
    del jsnode.parent[n:]
    cur = Cursor(span.a, view, edit)
    x0 = cur.pos
    insert_js_unit(cur, new_value, jsnode.parent)
    x1 = cur.pos
    parent_regions = view.get_regions(jsnode.parent.key_reg_children)
    parent_regions[n] = sublime.Region(x0, x1)
    view.add_regions(jsnode.parent.key_reg_children, parent_regions, '', '',
                     sublime.HIDDEN)
    jsnode.parent += following_siblings


server.action_handlers['edit'] = action_handler_edit
