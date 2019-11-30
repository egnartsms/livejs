import sublime_plugin
import sublime

import contextlib

from live.sublime_util.hacks import set_viewport_position
from live.code.common import make_js_value_inserter
from live.code.cursor import Cursor
from live.util import index_where, serially


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


def add_regions(key, regs, view):
    view.add_regions(key, regs, '', '', sublime.HIDDEN)


@contextlib.contextmanager
def region_list(key, view):
    region_list = view.get_regions(key)
    yield region_list
    add_regions(key, region_list, view)


class JsNode:
    is_leaf = False
    is_key = False
    is_object = False
    is_array = False

    def __init__(self):
        super().__init__()
        self.parent = None

    @property
    def is_attached(self):
        """Whether this node is being displayed in a code browser"""
        return 'view' in self.root.__dict__

    @property
    def view(self):
        # The root will have self.view instance attr assigned
        return self.root.__dict__['view']

    @property
    def root(self):
        node = self
        while not node.is_root:
            node = node.parent
        return node

    @property
    def is_root(self):
        return self.parent is None

    @property
    def position(self):
        return self._my_siblings.index(self)

    @property
    def depth(self):
        """Root has depth of 0, its children - 1, grandchildren - 2, etc."""
        node = self
        depth = 0
        while not node.is_root:
            depth += 1
            node = node.parent

        return depth

    @property
    def nesting(self):
        """Indentation level of the context where this node appears"""
        return self.depth - 1

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

    @property
    def _parent_regkey(self):
        """String key under which the parent stores regions to which this node belongs.
        
        JsKey overrides it to return a different key.
        """
        return self.parent.regkey_values

    @property
    def region(self):
        return self.view.get_regions(self._parent_regkey)[self.position]

    @property
    def begin(self):
        return self.region.a

    @property
    def end(self):
        return self.region.b

    @property
    def _my_siblings(self):
        """Parent's list where self is contained. JsKey overrides it"""
        return self.parent.value_nodes

    @property
    def following_sibling(self):
        pos = self.position + 1
        return None if pos == len(self._my_siblings) else self._my_siblings[pos]

    @property
    def preceding_sibling(self):
        pos = self.position
        return None if pos == 0 else self._my_siblings[pos - 1]

    @property
    def is_first(self):
        return self.preceding_sibling is None

    @property
    def is_last(self):
        return self.following_sibling is None

    @property
    def following_sibling_circ(self):
        return self._my_siblings[(self.position + 1) % len(self._my_siblings)]

    @property
    def preceding_sibling_circ(self):
        return self._my_siblings[self.position - 1]

    @property
    def textually_following_sibling_circ(self):
        return self.parent._child_textually_following_circ(self)

    @property
    def textually_preceding_sibling_circ(self):
        return self.parent._child_textually_preceding_circ(self)

    def _add_retained_regions_full_depth(self):
        """Does nothing for all nodes except composite ones, which see"""

    def _erase_regions_full_depth(self):
        """Does nothing for all nodes except composite ones, which see"""


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
    def dotpath(self):
        raise NotImplementedError  # makes no sense

    @property
    def _parent_regkey(self):
        return self.parent.regkey_keys
    
    @property
    def _my_siblings(self):
        return self.parent.key_nodes


class JsComposite(JsNode):
    def _add_retained_regions(self):
        raise NotImplementedError

    def _erase_regions(self):
        raise NotImplementedError

    def delete_at(self, pos):
        raise NotImplementedError

    @property
    def entries(self):
        raise NotImplementedError

    def _add_retained_regions_full_depth(self):
        self._add_retained_regions()
        for child in self.value_nodes:
            child._add_retained_regions_full_depth()

    def _erase_regions_full_depth(self):
        for child in self.value_nodes:
            child._erase_regions_full_depth()
        self._erase_regions()

    def replace_value_node_at(self, pos, new_node, new_reg):
        assert self.is_attached

        old_node = self.value_nodes[pos]
        old_node._erase_regions_full_depth()
        old_node.parent = None

        self.value_nodes[pos] = new_node
        new_node.parent = self
        new_node._add_retained_regions_full_depth()

        with region_list(self.regkey_values, self.view) as regions:
            regions[pos] = new_reg

    def value_node_at(self, path):
        node = self
        for n in path:
            node = node.value_nodes[n]
        return node

    def key_node_at(self, path):
        node = self
        for n in path[:-1]:
            node = node.value_nodes[n]
        if not node.is_object:
            raise RuntimeError(
                "Path to key node of {} is incorrect: {}".format(node, path)
            )
        return node.key_nodes[path[-1]]


class JsObject(JsComposite):
    """A list of values nodes. Key nodes are stored under 'keys' attribute."""

    is_object = True

    def __init__(self):
        super().__init__()
        self.key_nodes = []
        self.value_nodes = []
        self.key_regions = []
        self.value_regions = []

    def human_readable(self):
        return '{' + ','.join([x.human_readable() for x in self.value_nodes]) + '}'

    def __repr__(self):
        return '#<jsnode: {}>'.format(self.human_readable())

    def attach_to(self, view):
        assert self.is_root and not self.is_attached
        self.__dict__['view'] = view
        self._add_retained_regions_full_depth()

    @property
    def entries(self):
        return ObjectEntries(self)

    @property
    def regkey_keys(self):
        return dotpath_join(self.dotpath, 'keys')
    
    @property
    def regkey_values(self):
        return dotpath_join(self.dotpath, 'values')

    def _add_retained_regions(self):
        add_regions(self.regkey_keys, self.key_regions, self.view)
        del self.key_regions
        add_regions(self.regkey_values, self.value_regions, self.view)
        del self.value_regions

    def _erase_regions(self):
        self.view.erase_regions(self.regkey_keys)
        self.view.erase_regions(self.regkey_values)

    def entry_region_at(self, pos):
        reg_key = self.key_nodes[pos].region
        reg_value = self.value_nodes[pos].region
        return reg_key.cover(reg_value)

    def append(self, key_node, key_region, value_node, value_region):
        assert not self.is_attached
        assert key_node.is_key and not value_node.is_key

        self.key_nodes.append(key_node)
        key_node.parent = self
        self.key_regions.append(key_region)

        self.value_nodes.append(value_node)
        value_node.parent = self
        self.value_regions.append(value_region)

    def insert_entry(self, key_node, val_node, pos):
        #         if self.is_attached:
        #     with region_list(self.regkey_keys, self.view) as regions:
        #         regions.append(key_region)
            
        #     with region_list(self.regkey_values, self.view) as regions:
        #         regions.append(value_region)

        #     if not value_node.is_leaf:
        #         value_node.add_retained_regions_full_depth()
        # else:
        raise NotImplementedError

    def delete_at(self, pos):
        assert self.is_attached, "Why do we need to delete from an unattached node?"

        self.value_nodes[pos]._erase_regions_full_depth()

        with region_list(self.regkey_keys, self.view) as regions:
            del regions[pos]

        with region_list(self.regkey_values, self.view) as regions:
            del regions[pos]

        self.key_nodes.pop(pos).parent = None
        self.value_nodes.pop(pos).parent = None

    def replace_key_node_region_at(self, pos, region):
        with region_list(self.regkey_keys, self.view) as regions:
            regions[pos] = region

    def _child_textually_following_circ(self, child):
        if child.is_key:
            return self.value_nodes[child.position]
        else:
            return self.key_nodes[child.position].following_sibling_circ

    def _child_textually_preceding_circ(self, child):
        if child.is_key:
            return self.value_nodes[child.position].preceding_sibling_circ
        else:
            return self.key_nodes[child.position]

    def all_child_nodes_and_regions(self):
        key_regions = self.view.get_regions(self.regkey_keys)
        value_regions = self.view.get_regions(self.regkey_values)

        for (node, region) in serially(zip(self.key_nodes, key_regions),
                                       zip(self.value_nodes, value_regions)):
            yield node, region


class JsArray(JsComposite):
    is_array = True

    def __init__(self):
        super().__init__()
        self.value_nodes = []
        self.value_regions = []

    def human_readable(self):
        return '[' + ','.join([x.human_readable() for x in self.value_nodes]) + ']'

    def __repr__(self):
        return '#<jsnode: {}>'.format(self.human_readable())

    @property
    def entries(self):
        return self.value_nodes

    @property
    def regkey_values(self):
        return dotpath_join(self.dotpath, 'values')

    def _add_retained_regions(self):
        add_regions(self.regkey_values, self.value_regions, self.view)
        del self.value_regions

    def _erase_regions(self):
        self.view.erase_regions(self.regkey_values)

    def entry_region_at(self, pos):
        return self.value_nodes[pos].region

    def append(self, node, region):
        assert not self.is_attached
        assert not node.is_key

        self.value_nodes.append(node)
        node.parent = self
        self.value_regions.append(region)

    def insert_entry(self, *args):
        #         if self.is_attached:
        #     with region_list(self.regkey_values, self.view) as regions:
        #         regions.append(region)

        #     if not node.is_leaf:
        #         node.add_retained_regions_full_depth()
        # else:
        raise NotImplementedError

    def delete_at(self, pos):
        assert self.is_attached, "Why do we need to delete from an unattached node?"

        self.value_nodes[pos]._erase_regions_full_depth()

        with region_list(self.regkey_values, self.view) as regions:
            del regions[pos]

        self.value_nodes.pop(pos).parent = None

    def _child_textually_following_circ(self, child):
        return child.following_sibling_circ

    def _child_textually_preceding_circ(self, child):
        return child.preceding_sibling_circ

    def all_child_nodes_and_regions(self):
        value_regions = self.view.get_regions(self.regkey_values)

        for (node, region) in zip(self.value_nodes, value_regions):
            yield node, region


class ObjectEntries:
    __slots__ = ('node', )

    def __init__(self, node):
        assert node.is_object
        self.node = node
    
    def __getitem__(self, i):
        return ObjectEntry(self.node, i)


class ObjectEntry:
    __slots__ = ('node', 'i')

    def __init__(self, node, i):
        self.node = node
        self.i = i

    @property
    def region(self):
        return sublime.Region(self.begin, self.end)

    @property
    def begin(self):
        return self.node.key_nodes[self.i].begin

    @property
    def end(self):
        return self.node.value_nodes[self.i].end


def dotpath_join(dotpath, n):
    if dotpath:
        return '{}.{}'.format(dotpath, n)
    else:
        return str(n)


def insert_js_value(view, inserter):
    def insert_object():
        node = JsObject()

        while True:
            cmd = next(inserter)
            if cmd == 'pop':
                break

            key_region = cmd
            value_node = insert_any(next(inserter))
            value_region = next(inserter)
            node.append(JsKey(), key_region, value_node, value_region)

        return node

    def insert_array():
        node = JsArray()

        while True:
            cmd = next(inserter)
            if cmd == 'pop':
                break

            child_node = insert_any(cmd)
            child_region = next(inserter)
            node.append(child_node, child_region)
        
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


def find_containing_node(xreg, view):
    """Find innermost node that fully contains xreg

    :return: node or None if not inside any node or spans >1 top-level nodes.
    """
    node = info_for(view).root

    while not node.is_leaf:
        for subnode, subreg in node.all_child_nodes_and_regions():
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
        for subnode, subreg in node.all_child_nodes_and_regions():
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
        info_for(view).root._erase_regions_full_depth()
        info_for(view).root = None

    view.set_read_only(False)
    view.erase(edit, sublime.Region(0, view.size()))
    cur = Cursor(0, view, edit)
    root = JsObject()

    for key, value in response:
        x0 = cur.pos
        cur.insert(key)
        x1 = cur.pos
        key_region = sublime.Region(x0, x1)

        cur.insert(' = ')

        x0 = cur.pos
        value_node = insert_js_value(view, make_js_value_inserter(cur, value, 0))
        x1 = cur.pos
        value_region = sublime.Region(x0, x1)

        root.append(JsKey(), key_region, value_node, value_region)
        
        cur.insert('\n\n')

    info_for(view).root = root
    root.attach_to(view)
    
    view.set_read_only(True)
    view.window().focus_view(view)
    view.sel().clear()
    view.sel().add_all(prev_pos)

    set_viewport_position(view, prev_viewport_pos, False)


def replace_value_node(view, edit, path, new_value):
    node = info_for(view).root.value_node_at(path)

    assert node is info_for(view).node_being_edited

    parent, pos = node.parent, node.position
    
    [reg] = view.get_regions('being_edited')
    view.erase(edit, reg)
    cur = Cursor(reg.a, view, edit)
    beg = cur.pos
    new_node = insert_js_value(
        view,
        make_js_value_inserter(cur, new_value, parent.nesting + 1)
    )
    end = cur.pos

    parent.replace_value_node_at(pos, new_node, sublime.Region(beg, end))


def replace_key_node(view, edit, path, new_name):
    node = info_for(view).root.key_node_at(path)

    assert node is info_for(view).node_being_edited

    parent, pos = node.parent, node.position
    
    [reg] = view.get_regions('being_edited')
    view.erase(edit, reg)
    cur = Cursor(reg.a, view, edit)
    beg = cur.pos
    cur.insert(new_name)
    end = cur.pos

    parent.replace_key_node_region_at(pos, sublime.Region(beg, end))


def delete_node(view, edit, path):
    assert info_for(view).node_being_edited is None, \
        "We don't know how to handle deletion of nodes while editing in Code Browser"

    node = info_for(view).root.value_node_at(path)
    parent, pos = node.parent, node.position
    is_first, is_last = node.is_first, node.is_last

    if is_first and is_last:
        # TODO: deletion of all nodes from the root is not supported
        diereg = sublime.Region(parent.begin + 1, parent.end - 1)
    elif is_first:
        diereg = sublime.Region(parent.entries[pos].begin,
                                parent.entries[pos + 1].begin)
    else:
        diereg = sublime.Region(parent.entries[pos - 1].end,
                                parent.entries[pos].end)

    parent.delete_at(pos)
    view.set_read_only(False)
    view.erase(edit, diereg)
    view.set_read_only(True)
