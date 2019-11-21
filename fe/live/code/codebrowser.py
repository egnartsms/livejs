import sublime_plugin
import sublime

from live.code.common import inserting_js_object
from live.sublime_util.cursor import Cursor
from live.sublime_util.hacks import set_viewport_position


__all__ = ['PerViewInfoDiscarder']


# Information we associate with codebrowser views.  Keep in mind that it's not persisted.
# On Sublime re-start, none of these data structures will be in memory, but the code
# browser views will be persisted.
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
        per_view.pop(view.id(), None)


# JS nodes laid out in a codebrowser view.
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

    def get_at_path(self, path):
        assert len(path) > 0
        node = self
        for n in path:
            node = node[n]
        return node

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


def insert_js_object(cur, obj, parent_node):
    itr = inserting_js_object(cur, obj, parent_node.nesting)

    def insert_object(parent_node):
        reg_keys, reg_values, node = [], [], JsInterior(is_object=True)
        node.parent = parent_node
        parent_node.append(node)

        while True:
            cmd = next(itr)
            if cmd == 'pop':
                break

            beg, end = cmd
            reg_keys.append(sublime.Region(beg, end))
            insert_any(next(itr), node)
            beg, end = next(itr)
            reg_values.append(sublime.Region(beg, end))

        cur.view.add_regions(node.key_reg_keys, reg_keys, '', '', sublime.HIDDEN)
        cur.view.add_regions(node.key_reg_values, reg_values, '', '', sublime.HIDDEN)

    def insert_array(parent_node):
        reg_items, node = [], JsInterior(is_object=False)
        node.parent = parent_node
        parent_node.append(node)

        while True:
            cmd = next(itr)
            if cmd == 'pop':
                break

            insert_any(cmd, node)
            beg, end = next(itr)
            reg_items.append(sublime.Region(beg, end))
        
        cur.view.add_regions(node.key_reg_items, reg_items, '', '', sublime.HIDDEN)

    def insert_any(cmd, parent_node):
        if cmd == 'push_object':
            insert_object(parent_node)
        elif cmd == 'push_array':
            insert_array(parent_node)
        elif cmd == 'leaf':
            leaf = JsLeaf()
            leaf.parent = parent_node
            parent_node.append(leaf)

    insert_any(next(itr), parent_node)


def erase_regions(jsnode, view):
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


def on_refresh(view, edit, response):
    prev_pos = view.sel()[0].begin()
    prev_viewport_pos = view.viewport_position()

    root = info_for(view).root
    if root is not None:
        erase_regions(root, view)

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
        insert_js_object(cur, value, root)
        x1 = cur.pos
        reg_values.append(sublime.Region(x0, x1))
        
        cur.insert('\n\n')

    view.add_regions(root.key_reg_keys, reg_keys, '', '', sublime.HIDDEN)
    view.add_regions(root.key_reg_values, reg_values, '', '', sublime.HIDDEN)

    info_for(view).root = root

    view.set_read_only(True)
    view.window().focus_view(view)
    if prev_pos < view.size():
        view.sel().clear()
        view.sel().add(prev_pos)

    set_viewport_position(view, prev_viewport_pos, False)


def on_value_updated(view, response):
    view.erase_status('pending')
    info_for(view).jsnode_being_edited = None
    view.erase_regions('being_edited')
    view.set_read_only(True)


def handle_edit_action(view, edit, path, new_value):
    jsnode = info_for(view).root.get_at_path(path)
    
    assert jsnode is info_for(view).jsnode_being_edited

    parent = jsnode.parent
    cur = Cursor(jsnode.begin(view), view, edit)
    
    erase_regions(jsnode, view)
    cur.erase(jsnode.end(view))
    n = jsnode.num
    # We temporarily remove all the jsnode's siblings that go after it, then re-add
    following_siblings = parent[n + 1:]
    del parent[n:]
    beg = cur.pos
    insert_js_object(cur, new_value, parent)
    end = cur.pos
    parent += following_siblings

    parent_regions = view.get_regions(parent.key_reg_children)
    parent_regions[n] = sublime.Region(beg, end)
    view.add_regions(parent.key_reg_children, parent_regions, '', '', sublime.HIDDEN)
