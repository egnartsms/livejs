import sublime_plugin
import sublime

import json

from live.config import config
from live.code.common import make_js_value_inserter
from live.sublime_util.cursor import Cursor
from live.sublime_util.hacks import set_viewport_position
from live.util import index_where


__all__ = ['PerViewInfoDiscarder']


# Information we associate with codebrowser views.  Keep in mind that it's not persisted.
# On Sublime re-start, none of these data structures will be in memory, but the code
# browser views will be persisted.
per_view = dict()


class ViewInfo:
    root = None
    node_being_edited = None

    def __init__(self):
        pass


def info_for(view):
    vid = view.id()
    if vid not in per_view:
        per_view[vid] = ViewInfo()

    return per_view[vid]


class PerViewInfoDiscarder(sublime_plugin.EventListener):
    def on_close(self, view):
        per_view.pop(view.id(), None)


class JsNodePath:
    def __init__(self, components, key_at=None):
        self.components = components
        self.key_at = key_at

    def as_json(self):
        return json.dumps({
            'components': self.components,
            'keyAt': self.key_at
        })

    @classmethod
    def from_json(cls, json):
        return cls(json['components'], json['keyAt'])


class JsNode:
    is_leaf = None   # to be overriden by subclasses

    def __init__(self):
        super().__init__()
        self.parent = None

    @property
    def is_root(self):
        return self.parent is None

    @property
    def position(self):
        return index_where(x is self for x in self.parent)

    @property
    def nesting(self):
        node = self
        nesting = 0
        while not node.is_root:
            nesting += 1
            node = node.parent

        return nesting

    @property
    def path(self):
        components = []
        node = self
        while not node.is_root:
            components.append(node.position)
            node = node.parent

        components.reverse()
        return JsNodePath(components)

    @property
    def dotpath(self):
        return '.'.join(map(str, self.path.components))

    def span(self, view):
        return view.get_regions(self.parent.key_reg_values)[self.position]

    def begin(self, view):
        return self.span(view).a

    def end(self, view):
        return self.span(view).b


class JsLeaf(JsNode):
    is_leaf = True

    def human_readable(self):
        return 'x'

    def __repr__(self):
        return '#<jsleaf>'


class JsKey(JsNode):
    is_leaf = True

    def __repr__(self):
        return '#<jspropname>'

    @property
    def position(self):
        return index_where(x is self for x in self.parent.keys)

    @property
    def nesting(self):
        return self.parent.nesting

    @property
    def path(self):
        path = self.parent.path
        path.key_at = self.position
        return path

    @property
    def dotpath(self):
        raise NotImplementedError  # makes no sense

    def span(self, view):
        return view.get_regions(self.parent.key_reg_keys)[self.position]


def dotpath_join(dotpath, n):
    if dotpath:
        return '{}.{}'.format(dotpath, n)
    else:
        return str(n)


class JsObject(JsNode, list):
    """A list of values nodes. Key nodes are stored under 'keys' attribute."""
    is_leaf = False

    def __init__(self):
        super().__init__()
        self.keys = []
        self.reg_keys = []
        self.reg_values = []

    def human_readable(self):
        return '{' + ','.join([x.human_readable() for x in self]) + '}'

    def __repr__(self):
        return '#<jsnode: {}>'.format(self.human_readable())

    @property
    def key_reg_keys(self):
        return dotpath_join(self.dotpath, 'keys')
    
    @property
    def key_reg_values(self):
        return dotpath_join(self.dotpath, 'values')

    def add_regions(self, view):
        view.add_regions(self.key_reg_keys, self.reg_keys, '', '', sublime.HIDDEN)
        del self.reg_keys
        view.add_regions(self.key_reg_values, self.reg_values, '', '', sublime.HIDDEN)
        del self.reg_values

    def append_entry(self, key_node, val_node):
        assert isinstance(key_node, JsKey)
        self.keys.append(key_node)
        key_node.parent = self
        self.append(val_node)
        val_node.parent = self


class JsArray(JsNode, list):
    is_leaf = False

    def __init__(self):
        super().__init__()
        self.reg_values = []

    def human_readable(self):
        return '[' + ','.join([x.human_readable() for x in self]) + ']'

    def __repr__(self):
        return '#<jsnode: {}>'.format(self.human_readable())

    @property
    def key_reg_values(self):
        return dotpath_join(self.dotpath, 'values')

    def add_regions(self, view):
        view.add_regions(self.key_reg_values, self.reg_values, '', '', sublime.HIDDEN)
        del self.reg_values

    def append_child(self, child_node):
        self.append(child_node)
        child_node.parent = self


def node_at(node, path):
    for n in path.components:
        node = node[n]
    if path.key_at is not None:
        if not isinstance(node, JsObject):
            raise RuntimeError(
                "Invalid path (last link happens to be a non-JS object): {}".format(path)
            )
        node = node.keys[path.key_at]
    return node


def insert_js_value(view, inserter):
    def insert_object():
        node = JsObject()

        while True:
            cmd = next(inserter)
            if cmd == 'pop':
                break

            reg = cmd
            node.reg_keys.append(reg)
            child_node = insert_any(next(inserter))
            reg = next(inserter)
            node.reg_values.append(reg)
            node.append_entry(JsKey(), child_node)

        return node

    def insert_array():
        node = JsArray()

        while True:
            cmd = next(inserter)
            if cmd == 'pop':
                break

            child_node = insert_any(cmd)
            reg = next(inserter)
            node.reg_values.append(reg)
            node.append_child(child_node)
        
        return node

    def insert_any(cmd):
        if cmd == 'push_object':
            return insert_object()
        elif cmd == 'push_array':
            return insert_array()
        elif cmd == 'leaf':
            return JsLeaf()
        else:
            assert 0, "Unexpected cmd: {}".format(cmd)

    return insert_any(next(inserter))


def add_regions(node, view):
    def add(node):
        if node.is_leaf:
            return

        for subnode in node:
            add(subnode)

        node.add_regions(view)

    add(node)


def erase_regions(node, view):
    def erase(node):
        if node.is_leaf:
            return

        for subnode in node:
            erase(subnode)

        view.erase_regions(node.key_reg_values)

        if isinstance(node, JsObject):
            view.erase_regions(node.key_reg_keys)

    erase(node)


def replace_region(node, reg, view):
    parent_regions = view.get_regions(node.parent.key_reg_values)
    parent_regions[node.position] = reg
    view.add_regions(node.parent.key_reg_values, parent_regions, '', '', sublime.HIDDEN)


def find_containing_node_and_region(view, xreg):
    """Find innermost node that fully contains xreg

    :return: (node, reg) or (root, None) if not inside any node or spans >1 top-level
    nodes.
    """
    node = info_for(view).root
    reg = None

    while not node.is_leaf:
        regs = view.get_regions(node.key_reg_values)

        assert len(regs) == len(node)

        for subnode, subreg in zip(node, regs):
            if subreg.contains(xreg):
                node = subnode
                reg = subreg
                break
        else:
            # xreg is not fully contained in any single child of node.  That means that
            # node and reg are what we're looking for.
            break

    return node, reg


def find_node_by_exact_region(view, xreg):
    node = info_for(view).root

    while not node.is_leaf:
        regs = view.get_regions(node.key_reg_values)

        assert len(regs) == len(node)

        for subnode, subreg in zip(node, regs):
            if subreg == xreg:
                return subnode
            elif subreg.contains(xreg):
                node = subnode
                break
        else:
            break

    return None


def refresh(view, edit, response):
    prev_pos = list(view.sel())
    prev_viewport_pos = view.viewport_position()

    if info_for(view).root is not None:
        erase_regions(info_for(view).root, view)
        info_for(view).root = None

    view.set_read_only(False)
    view.erase(edit, sublime.Region(0, view.size()))
    cur = Cursor(0, view, edit)
    root = JsObject()

    for key, value in response:
        x0 = cur.pos
        cur.insert(key)
        x1 = cur.pos
        root.reg_keys.append(sublime.Region(x0, x1))

        cur.insert(' = ')

        x0 = cur.pos
        child = insert_js_value(view, make_js_value_inserter(cur, value, 0))
        x1 = cur.pos
        root.reg_values.append(sublime.Region(x0, x1))

        root.append_entry(JsKey(), child)
        
        cur.insert('\n\n')

    add_regions(root, view)
    info_for(view).root = root

    view.set_read_only(True)
    view.window().focus_view(view)
    view.sel().clear()
    view.sel().add_all(prev_pos)

    set_viewport_position(view, prev_viewport_pos, False)


def replace_node(view, edit, path, new_value):
    node = node_at(info_for(view).root, path)
    parent = node.parent
    [reg] = view.get_regions('being_edited')

    assert node is info_for(view).node_being_edited

    erase_regions(node, view)
    view.erase(edit, reg)
    cur = Cursor(reg.a, view, edit)
    
    if isinstance(parent, JsObject):
        cur.insert(' ')
    else:
        cur.insert('\n')
        cur.insert(config.s_indent * parent.nesting)
    beg = cur.pos
    new_node = insert_js_value(
        view,
        make_js_value_inserter(cur, new_value, parent.nesting)
    )
    end = cur.pos

    parent[node.position] = new_node
    new_node.parent = parent

    add_regions(new_node, view)
    replace_region(new_node, sublime.Region(beg, end), view)
