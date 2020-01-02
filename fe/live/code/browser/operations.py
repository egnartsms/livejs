import sublime

from live.util import first_such, tracking_last
from live.sublime_util.hacks import set_viewport_position
from live.sublime_util.technical_command import run_technical_command
from live.sublime_util.selection import set_selection
from ..common import read_only_set_to, make_js_value_inserter, add_hidden_regions
from .cursor import Cursor
from .view_info import info_for
from .nodes import JsObject, JsArray, JsLeaf


CODE_BROWSER_VIEW_NAME = "LiveJS: Code Browser"


def find_module_browser(window, module):
    return first_such(
        view for view in window.views()
        if view.settings().get('livejs_view') == 'Code Browser' and
        view.settings().get('livejs_module_id') == module.id
    )


def new_module_browser(window, module):
    view = window.new_file()
    view.settings().set('livejs_view', 'Code Browser')
    view.settings().set('livejs_module_id', module.id)
    view.set_name(module_browser_view_name(module))
    view.set_scratch(True)
    view.set_read_only(True)
    view.assign_syntax('Packages/JavaScript/JavaScript.sublime-syntax')
    return view


def module_browser_view_name(module):
    return "LiveJS: {}".format(module.name)


def is_module_browser(view):
    return view.settings().get('livejs_view') == 'Code Browser'


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
            node.append(key_region, value_node, value_region)

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


def find_containing_node(view, xreg, strict=False):
    """Find innermost node that fully contains xreg

    :param strict: if True, the xreg must be completely inside the node. If False, it may
    be adjacent to either beginning or end of a node and is still considered to lie within
    it.
    :return: node (may be a root node)
    """
    if strict:
        def lies_within(reg):
            return reg.a < xreg.a and reg.b > xreg.b
    else:
        def lies_within(reg):
            return reg.contains(xreg)

    node = info_for(view).root

    while not node.is_leaf:
        for subnode, subreg in node.all_child_nodes_and_regions():
            if lies_within(subreg):
                node = subnode
                break
        else:
            # xreg is not fully contained in any single child of node.  That means that
            # node and reg are what we're looking for.
            break

    return node


def find_node_by_exact_region(view, xreg):
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


def find_insert_position(parent, reg):
    """Child index of a node that would be inserted at reg

    :param reg: sublime.Region
    :return: index or None in case reg is not fully contained in a single inter-node
             region.
    """
    pos = 0
    folw = None

    while True:
        prec = folw
        folw = None if pos == parent.num_children else parent.entries[pos]

        inter_reg = sublime.Region(
            prec.end if prec else parent.begin + 1,
            folw.begin if folw else parent.end - 1
        )
        if inter_reg.contains(reg):
            return pos

        if folw is None:
            break

        pos += 1

    return None


def get_single_selected_node(view):
    """If view has a single selection equal to a node's region, return this node.

    :return: node or None
    """
    if len(view.sel()) != 1:
        return None
    return find_node_by_exact_region(view, view.sel()[0])


def set_edit_region(view, reg, enclosing=None):
    view.add_regions('edit', [reg], 'region.bluish livejs.edit', '',
                     sublime.DRAW_EMPTY | sublime.DRAW_NO_OUTLINE)
    if enclosing is None:
        enclosing = reg
    add_hidden_regions(view, 'enclosing_edit', [enclosing])


def discard_edit_region(view):
    view.erase_regions('edit')
    view.erase_regions('enclosing_edit')


def edit_region(view):
    [reg] = view.get_regions('edit')
    return reg


def enclosing_edit_region(view):
    [reg] = view.get_regions('enclosing_edit')
    return reg


def edit_region_contents(view):
    return view.substr(edit_region(view)).strip()


def edit_node(node):
    """Start editing of the specified node"""
    view = node.view
    view.set_read_only(False)
    set_edit_region(view, node.region)
    info_for(view).edit_node(node)


def edit_new_node(view, edit, parent, pos):
    """Start editing the contents of the to-be-added node"""
    nesting = parent.nesting + 1
    
    view.set_read_only(False)

    if parent.is_object:
        def placeholder(cur):
            cur.insert('newKey')
            cur.sep_keyval(nesting)
            cur.insert('newValue')
    else:
        def placeholder(cur):
            cur.insert('newValue')

    if 0 == pos == parent.num_children:
        cur = Cursor(parent.begin + 1, view, edit)
        cur.push_region()
        cur.sep_initial(nesting)
        cur.push_region()
        placeholder(cur)
        edit_reg = cur.pop_region()
        cur.sep_terminal(nesting)
        enclosing_reg = cur.pop_region()
    elif pos < parent.num_children:
        cur = Cursor(parent.entries[pos].begin, view, edit)
        cur.push_region()
        cur.push_region()
        placeholder(cur)
        edit_reg = cur.pop_region()
        cur.sep_inter(nesting)
        enclosing_reg = cur.pop_region()
    else:
        cur = Cursor(parent.entries[parent.num_children - 1].end, view, edit)
        cur.push_region()
        cur.sep_inter(nesting)
        cur.push_region()
        placeholder(cur)
        edit_reg = cur.pop_region()
        enclosing_reg = cur.pop_region()

    set_edit_region(view, edit_reg, enclosing_reg)
    set_selection(view, to_reg=edit_reg)
    info_for(view).edit_new_node(parent, pos, edit_reg, enclosing_reg)


def done_editing(view):
    """Switch from edit mode to the ordinary view mode"""
    view.erase_status('livejs_pending')
    discard_edit_region(view)
    view.set_read_only(True)
    info_for(view).done_editing()


def invalidate_codebrowser(view):
    def go(view, edit):
        with read_only_set_to(view, False):
            view.replace(edit, sublime.Region(0, view.size()),
                         "<<<<< Codebrowser contents outdated. Please refresh! >>>>>")

    run_technical_command(view, go)


def refresh(view, edit, entries):
    prev_pos = list(view.sel())
    prev_viewport_pos = view.viewport_position()

    if info_for(view).root is not None:
        info_for(view).root._erase_regions_full_depth()
        info_for(view).root = None

    view.set_read_only(False)
    view.erase(edit, sublime.Region(0, view.size()))
    cur = Cursor(0, view, edit)
    root = JsObject()

    cur.sep_initial(nesting=0)

    for (key, value), islast in tracking_last(entries):
        cur.push_region()
        cur.insert(key)
        key_region = cur.pop_region()

        cur.sep_keyval(nesting=0)

        cur.push_region()
        value_node = insert_js_value(view, make_js_value_inserter(cur, value, 0))
        value_region = cur.pop_region()

        root.append(key_region, value_node, value_region)
        
        (cur.sep_terminal if islast else cur.sep_inter)(nesting=0)

    info_for(view).root = root
    root.put_online(view)
    
    view.set_read_only(True)
    view.window().focus_view(view)
    set_selection(view, to_regs=prev_pos)

    set_viewport_position(view, prev_viewport_pos, False)


def replace_value_node(view, edit, path, new_value):
    """Replace value node at given path with new_value"""
    vinfo = info_for(view)
    node = vinfo.root.value_node_at(path)

    if node is vinfo.node_being_edited:
        reg = enclosing_edit_region(view)
        done_editing(view)
    else:
        reg = node.region

    with read_only_set_to(view, False):
        cur = Cursor(reg.a, view, edit)
        cur.erase(reg.b)

        cur.push_region()
        new_node = insert_js_value(
            view,
            make_js_value_inserter(cur, new_value, node.nesting)
        )

    node.parent.replace_value_node_at(node.position, new_node, cur.pop_region())


def replace_key_node(view, edit, path, new_name):
    vinfo = info_for(view)
    node = vinfo.root.key_node_at(path)

    if node is vinfo.node_being_edited:
        reg = enclosing_edit_region(view)
        done_editing(view)
    else:
        reg = node.region

    with read_only_set_to(view, False):
        view.erase(edit, reg)
        cur = Cursor(reg.a, view, edit)
        cur.push_region()
        cur.insert(new_name)

    node.parent.replace_key_node_region_at(node.position, cur.pop_region())


def delete_node(view, edit, path):
    vinfo = info_for(view)
    node = vinfo.root.value_node_at(path)
    parent, pos = node.parent, node.position

    enode = vinfo.node_being_edited

    if enode is not None and enode.value_node_or_self is node:
        reg = enclosing_edit_region(view)
        if enode.kv_match:
            reg = reg.cover(enode.kv_match.region)

        done_editing(view)
    else:
        reg = parent.entries[pos].region
    
    if node.is_first and node.is_last:
        # TODO: deletion of all nodes from the root is not supported
        diereg = sublime.Region(parent.begin + 1, parent.end - 1)
    elif node.is_first:
        diereg = sublime.Region(reg.a, parent.entries[pos + 1].begin)
    else:
        diereg = sublime.Region(parent.entries[pos - 1].end, reg.b)

    with read_only_set_to(view, False):
        view.erase(edit, diereg)

    parent.delete_at(pos)


def insert_node(view, edit, path, key, value):
    vinfo = info_for(view)
    path, new_index = path[:-1], path[-1]
    parent = vinfo.root.value_node_at(path)
    nesting = parent.nesting + 1

    if (key is not None) != parent.is_object:
        raise RuntimeError("Object/array mismatch")

    if vinfo.is_editing_new_node and vinfo.new_node_parent is parent and\
            vinfo.new_node_position == new_index:
        # In this Code Browser view we were editing the new node which is now being
        # inserted.  This is typical after the user commits.
        view.erase(edit, enclosing_edit_region(view))
        done_editing(view)

    def insert():
        if parent.num_children == 0:
            cur = Cursor(parent.begin + 1, view, edit)
            cur.sep_initial(nesting)
            yield cur
            cur.sep_terminal(nesting)
        elif new_index >= parent.num_children:
            cur = Cursor(parent.entries[-1].end, view, edit)
            cur.sep_inter(nesting)
            yield cur
        else:
            cur = Cursor(parent.entries[new_index].begin, view, edit)
            yield cur
            cur.sep_inter(nesting)

    with read_only_set_to(view, False):
        gen = insert()
        cur = next(gen)

        if key is not None:
            cur.push_region()
            cur.insert(key)
            key_region = cur.pop_region()
            cur.sep_keyval(nesting)
        
        cur.push_region()
        value_node = insert_js_value(
            view,
            make_js_value_inserter(cur, value, nesting)
        )
        value_region = cur.pop_region()

        if key is not None:
            parent.insert_at(new_index, key_region, value_node, value_region)
        else:
            parent.insert_at(new_index, value_node, value_region)

        next(gen, None)
