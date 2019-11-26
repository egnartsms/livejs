import sublime_plugin
import sublime

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


class JsNode:
    is_leaf = False
    is_key = False

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
        path = []
        node = self
        while not node.is_root:
            path.append(node.position)
            node = node.parent

        path.reverse()
        return path

    @property
    def dotpath(self):
        return '.'.join(map(str, self.path))

    def span(self, view):
        return view.get_regions(self.parent.key_reg_values)[self.position]

    def begin(self, view):
        return self.span(view).a

    def end(self, view):
        return self.span(view).b

    @property
    def _my_siblings(self):
        """Parent's list where self is contained.

        For JsKey, this is overriden to return self.parent.keys.
        """
        return self.parent

    def following_sibling(self):
        return self._my_siblings[(self.position + 1) % len(self._my_siblings)]

    def preceding_sibling(self):
        return self._my_siblings[self.position - 1]

    def textually_following_sibling(self):
        return self.parent._child_textually_following(self)

    def textually_preceding_sibling(self):
        return self.parent._child_textually_preceding(self)

    def prepare_for_editing(self, view, edit):
        """Make necessary adjustments in the view and return the extended region"""
        return self.parent._prepare_for_editing_of_child(self, view, edit)


class JsLeaf(JsNode):
    is_leaf = True

    def human_readable(self):
        return 'x'

    def __repr__(self):
        return '#<jsleaf>'


class JsKey(JsNode):
    is_leaf = True
    is_key = True

    def __repr__(self):
        return '#<jspropname>'

    @property
    def position(self):
        return index_where(x is self for x in self.parent.keys)

    @property
    def nesting(self):
        return self.parent.nesting

    @property
    def dotpath(self):
        raise NotImplementedError  # makes no sense

    def span(self, view):
        return view.get_regions(self.parent.key_reg_keys)[self.position]

    @property
    def _my_siblings(self):
        return self.parent.keys


class JsObject(JsNode, list):
    """A list of values nodes. Key nodes are stored under 'keys' attribute."""

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

    def retain_key_region(self, reg):
        self.reg_keys.append(reg)

    def retain_value_region(self, reg):
        self.reg_values.append(reg)

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

    def _child_textually_following(self, child):
        if child.is_key:
            return self[child.position]
        else:
            return self.keys[(child.position + 1) % len(self)]

    def _child_textually_preceding(self, child):
        if child.is_key:
            return self[child.position - 1]
        else:
            return self.keys[child.position]

    def get_all_child_nodes(self):
        for key_node, val_node in zip(self.keys, self):
            yield key_node
            yield val_node

    def get_all_regions(self, view):
        for regk, regv in zip(view.get_regions(self.key_reg_keys),
                              view.get_regions(self.key_reg_values)):
            yield regk
            yield regv

    def _prepare_for_editing_of_child(self, child, view, edit):
        reg = child.span(view)
        beg, end = Cursor(reg.a, view, edit), Cursor(reg.b, view, edit)

        if child.is_key:
            beg.skip_ws_to_bol(skip_bol=True)
            end.insert('\n')
        else:
            beg.skip_ws_to_bol(skip_bol=False)
            end.insert('\n')

        return sublime.Region(beg.pos, end.pos)

    def reinsert_after_edit(self, cur, is_key):
        if is_key:
            cur.insert('\n')
            cur.indent(self.nesting)
            yield
            if self.is_root:
                cur.insert(' ')
        else:
            cur.insert(' ')
            yield


class JsArray(JsNode, list):
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

    def retain_value_region(self, reg):
        self.reg_values.append(reg)

    def add_regions(self, view):
        view.add_regions(self.key_reg_values, self.reg_values, '', '', sublime.HIDDEN)
        del self.reg_values

    def append_child(self, child_node):
        self.append(child_node)
        child_node.parent = self

    def _child_textually_following(self, child):
        return child.following_sibling()

    def _child_textually_preceding(self, child):
        return child.preceding_sibling()

    def get_all_child_nodes(self):
        return self

    def get_all_regions(self, view):
        return view.get_regions(self.key_reg_values)

    def _prepare_for_editing_of_child(self, child, view, edit):
        reg = child.span(view)
        beg, end = Cursor(reg.a, view, edit), Cursor(reg.b, view, edit)

        beg.skip_ws_to_bol(skip_bol=True)
        end.insert('\n')

        return sublime.Region(beg.pos, end.pos)

    def reinsert_after_edit(self, cur, is_key):
        cur.insert('\n')
        cur.indent(self.nesting)
        yield


def dotpath_join(dotpath, n):
    if dotpath:
        return '{}.{}'.format(dotpath, n)
    else:
        return str(n)


def value_node_at(node, path):
    for n in path:
        node = node[n]
    return node


def key_node_at(node, path):
    for n in path[:-1]:
        node = node[n]
    if not isinstance(node, JsObject):
        raise RuntimeError("Path to key node of {} is incorrect: {}".format(node, path))
    return node.keys[path[-1]]


def insert_js_value(view, inserter):
    def insert_object():
        node = JsObject()

        while True:
            cmd = next(inserter)
            if cmd == 'pop':
                break

            reg = cmd
            node.retain_key_region(reg)
            child_node = insert_any(next(inserter))
            reg = next(inserter)
            node.retain_value_region(reg)
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
            node.retain_value_region(reg)
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


def find_containing_node(xreg, view):
    """Find innermost node that fully contains xreg

    :return: node or None if not inside any node or spans >1 top-level nodes.
    """
    node = info_for(view).root

    while not node.is_leaf:
        for subnode, subreg in zip(node.get_all_child_nodes(),
                                   node.get_all_regions(view)):
            if subreg.contains(xreg):
                node = subnode
                break
        else:
            # xreg is not fully contained in any single child of node.  That means that
            # node and reg are what we're looking for.
            break

    return None if node.is_root else node


def find_node_by_exact_region(xreg, view):
    node = info_for(view).root

    while not node.is_leaf:
        for subnode, subreg in zip(node.get_all_child_nodes(),
                                   node.get_all_regions(view)):
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
        root.retain_key_region(sublime.Region(x0, x1))

        cur.insert(' = ')

        x0 = cur.pos
        child = insert_js_value(view, make_js_value_inserter(cur, value, 0))
        x1 = cur.pos
        root.retain_value_region(sublime.Region(x0, x1))

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
    node = value_node_at(info_for(view).root, path)

    assert node is info_for(view).node_being_edited

    parent = node.parent
    [reg] = view.get_regions('being_edited')

    erase_regions(node, view)
    
    view.erase(edit, reg)
    cur = Cursor(reg.a, view, edit)
    reinserter = parent.reinsert_after_edit(cur, node.is_key)
    next(reinserter)
    beg = cur.pos
    new_node = insert_js_value(
        view,
        make_js_value_inserter(cur, new_value, parent.nesting)
    )
    end = cur.pos
    next(reinserter, None)

    parent[node.position] = new_node
    new_node.parent = parent
    node.parent = None

    add_regions(new_node, view)
    replace_region(new_node, sublime.Region(beg, end), view)
