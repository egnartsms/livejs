import sublime

from live.sublime_util.misc import add_hidden_regions
from live.sublime_util.misc import hidden_region_list
from live.util import serially


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
        return self.parent is not None

    def attach_to(self, parent):
        assert not self.is_attached
        self.parent = parent

    def detach(self):
        assert self.is_attached
        self.parent = None

    @property
    def is_online(self):
        """Whether this node is being displayed in a code browser"""
        return 'view' in self.root.__dict__

    @property
    def is_offline(self):
        return not self.is_online

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
    def _parent_regkey(self):
        """String key under which the parent stores regions to which this node belongs.
        
        JsKey overrides it to return a different key.
        """
        return self.parent.regkey_values

    @property
    def value_node_or_self(self):
        """For all nodes except object keys, this is self."""
        return self

    @property
    def keyval_match(self):
        """If self is an object's key, return value node, and vice-versa.

        For array elements, return None.
        """
        if self.parent.is_object:
            return self.parent.key_nodes[self.position]
        else:
            return None

    @property
    def region(self):
        if self.is_root:
            return sublime.Region(-1, self.view.size() + 1)
        else:
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

    def __init__(self, parent):
        super().__init__()
        self.parent = parent

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

    @property
    def value_node_or_self(self):
        """For all nodes except object keys, this is self."""
        return self.parent.value_nodes[self.position]

    @property
    def keyval_match(self):
        """If self is an object's key, return value node, and vice-versa.

        For array elements, return None.
        """
        return self.value_node_or_self


class JsComposite(JsNode):
    def __init__(self):
        super().__init__()
        self.child_id_seq = 0
        self.child_id = None

    def attach_to(self, parent):
        assert not self.is_attached
        self.parent = parent
        self.child_id = '{:X}'.format(parent.child_id_seq)
        parent.child_id_seq += 1
        if parent.is_online:
            self._add_retained_regions_full_depth()

    def detach(self):
        assert self.is_attached
        if self.parent.is_online:
            self._erase_regions_full_depth()
        self.parent = None

    @property
    def dotpath(self):
        pieces = []
        node = self

        while not node.is_root:
            pieces.append(node.child_id)
            node = node.parent
        
        pieces.reverse()
        return '.'.join(pieces)

    @property
    def num_children(self):
        return len(self.value_nodes)

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
        assert self.is_online

        old_node = self.value_nodes[pos]
        old_node.detach()
        new_node.attach_to(self)
        self.value_nodes[pos] = new_node

        with hidden_region_list(self.view, self.regkey_values) as regions:
            regions[pos] = new_reg

    def value_node_at(self, path):
        node = self
        for n in path:
            node = node.value_nodes[n]
        return node

    def key_node_at(self, path):
        xpath, nlast = path[:-1], path[-1]
        node = self
        for n in xpath:
            node = node.value_nodes[n]
        
        assert node.is_object, \
            "Path to key node of {} is incorrect: {}".format(self, path)
        
        return node.key_nodes[nlast]

    def internode_pos(self, reg):
        """Child index of a node that would be inserted at reg

        :param reg: sublime.Region
        :return: index or None in case reg is not fully contained in a single inter-node
                 region.
        """
        pos = 0
        folw = None

        while True:
            prec = folw
            folw = None if pos == self.num_children else self.entries[pos]

            inter_reg = sublime.Region(
                prec.end if prec else self.begin + 1,
                folw.begin if folw else self.end - 1
            )
            if inter_reg.contains(reg):
                return pos

            if folw is None:
                break

            pos += 1

        return None


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

    def put_online(self, view):
        assert self.is_root and self.is_offline
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
        add_hidden_regions(self.view, self.regkey_keys, self.key_regions)
        del self.key_regions
        add_hidden_regions(self.view, self.regkey_values, self.value_regions)
        del self.value_regions

    def _erase_regions(self):
        self.view.erase_regions(self.regkey_keys)
        self.view.erase_regions(self.regkey_values)

    def append(self, key_region, value_node, value_region):
        assert self.is_offline
        assert not value_node.is_key

        self.key_nodes.append(JsKey(self))
        self.key_regions.append(key_region)

        self.value_nodes.append(value_node)
        value_node.attach_to(self)
        self.value_regions.append(value_region)

    def insert_at(self, pos, key_region, value_node, value_region):
        assert self.is_online, "Why do we need to insert into an unattached node?"

        self.key_nodes.insert(pos, JsKey(self))
        self.value_nodes.insert(pos, value_node)
        value_node.attach_to(self)

        with hidden_region_list(self.view, self.regkey_keys) as regions:
            regions.insert(pos, key_region)
        
        with hidden_region_list(self.view, self.regkey_values) as regions:
            regions.insert(pos, value_region)

    def delete_at(self, pos):
        assert self.is_online, "Why do we need to delete from an unattached node?"

        with hidden_region_list(self.view, self.regkey_keys) as regions:
            del regions[pos]

        with hidden_region_list(self.view, self.regkey_values) as regions:
            del regions[pos]

        self.key_nodes.pop(pos).detach()
        self.value_nodes.pop(pos).detach()

    def replace_key_node_region_at(self, pos, region):
        with hidden_region_list(self.view, self.regkey_keys) as regions:
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
        add_hidden_regions(self.view, self.regkey_values, self.value_regions)
        del self.value_regions

    def _erase_regions(self):
        self.view.erase_regions(self.regkey_values)

    def append(self, node, region):
        assert self.is_offline
        assert not node.is_key

        self.value_nodes.append(node)
        node.attach_to(self)
        self.value_regions.append(region)

    def insert_at(self, pos, node, region):
        assert self.is_online, "Why do we need to insert into an unattached node?"

        self.value_nodes.insert(pos, node)
        node.attach_to(self)

        with hidden_region_list(self.view, self.regkey_values) as regions:
            regions.insert(pos, region)

    def delete_at(self, pos):
        assert self.is_online, "Why do we need to delete from an unattached node?"

        with hidden_region_list(self.view, self.regkey_values) as regions:
            del regions[pos]

        self.value_nodes.pop(pos).detach()

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

    def __len__(self):
        return self.node.num_children


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


def dotpath_join(dotpath, item):
    if dotpath:
        return '{}.{}'.format(dotpath, item)
    else:
        return item
