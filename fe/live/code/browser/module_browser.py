import sublime

from .cursor import Cursor
from .nodes import JsArray
from .nodes import JsLeaf
from .nodes import JsObject
from live.code.common import make_js_value_inserter
from live.modules.datastructures import Module
from live.settings import setting_module_id
from live.sublime_util.hacks import set_viewport_position
from live.sublime_util.misc import is_subregion
from live.sublime_util.misc import read_only_set_to
from live.sublime_util.misc import set_selection
from live.sublime_util.region_edit import RegionEditHelper
from live.util import tracking_last


class ModuleBrowser:
    EDIT_REGION_KEY = 'edit'

    def __init__(self, view):
        self.view = view
        self.module_id = setting_module_id[view]
        self.root = None
        self.node_being_edited = None
        self.is_editing = False
        self.new_node_parent = None
        self.new_node_position = None
        self.region_edit_helper = None

    @property
    def is_editing_new_node(self):
        return self.is_editing and self.node_being_edited is None

    @property
    def module(self):
        return Module.with_id(self.module_id)

    @property
    def edit_region(self):
        [reg] = self.view.get_regions('edit')
        return reg

    def edit_region_contents(self):
        return self.view.substr(self.edit_region).strip()

    def set_edit_region(self, reg):
        self.view.add_regions('edit', [reg], 'region.bluish livejs.edit', '',
                              sublime.DRAW_EMPTY | sublime.DRAW_NO_OUTLINE)

    def discard_edit_region(self):
        self.view.erase_regions('edit')

    def edit_node(self, node):
        """Start editing of the specified node"""
        self.view.set_read_only(False)
        self.set_edit_region(node.region)
        self.is_editing = True
        self.node_being_edited = node
        self.region_edit_helper = CodeBrowserRegionEditHelper(self)

    def edit_new_node(self, edit, parent, pos):
        """Start editing the contents of the to-be-added node"""
        nesting = parent.nesting + 1
        
        self.view.set_read_only(False)

        if parent.is_object:
            def placeholder(cur):
                cur.insert('newKey')
                cur.sep_keyval(nesting)
                cur.insert('newValue')
        else:
            def placeholder(cur):
                cur.insert('newValue')

        if 0 == pos == parent.num_children:
            cur = Cursor(parent.begin + 1, self.view, edit)
            cur.push_region()
            cur.sep_initial(nesting)
            cur.push_region()
            placeholder(cur)
            edit_reg = cur.pop_region()
            cur.sep_terminal(nesting)
            enclosing_reg = cur.pop_region()
        elif pos < parent.num_children:
            cur = Cursor(parent.entries[pos].begin, self.view, edit)
            cur.push_region()
            cur.push_region()
            placeholder(cur)
            edit_reg = cur.pop_region()
            cur.sep_inter(nesting)
            enclosing_reg = cur.pop_region()
        else:
            cur = Cursor(parent.entries[parent.num_children - 1].end, self.view, edit)
            cur.push_region()
            cur.sep_inter(nesting)
            cur.push_region()
            placeholder(cur)
            edit_reg = cur.pop_region()
            enclosing_reg = cur.pop_region()

        self.set_edit_region(edit_reg)
        set_selection(self.view, to_reg=edit_reg)
        self.is_editing = True
        self.new_node_parent = parent
        self.new_node_position = pos
        self.region_edit_helper = CodeBrowserRegionEditHelper(self, enclosing_reg)

    def done_editing(self):
        """Ensure the browser is in the ordinary view mode.

        No textual changes to the view are made.
        """
        self.view.erase_status('livejs_pending')
        self.discard_edit_region()
        self.view.set_read_only(True)
        self.is_editing = False
        self.node_being_edited = None
        self.new_node_position = None
        self.new_node_parent = None
        self.region_edit_helper = None

    def find_containing_node(self, xreg, strict=False):
        """Find innermost node that fully contains xreg

        :param strict: if True, the xreg must be completely inside the node. If False, it
        may be adjacent to either beginning or end of a node and is still considered to
        lie within it.
        :return: node (may be a root node)
        """
        node = self.root

        while not node.is_leaf:
            for subnode, subreg in node.all_child_nodes_and_regions():
                if is_subregion(xreg, subreg, strict):
                    node = subnode
                    break
            else:
                # xreg is not fully contained in any single child of node.  That means
                # node and reg are what we're looking for.
                break

        return node

    def find_node_by_exact_region(self, xreg):
        node = self.root

        while not node.is_leaf:
            for subnode, subreg in node.all_child_nodes_and_regions():
                if subreg == xreg:
                    return subnode
                elif is_subregion(xreg, subreg):
                    node = subnode
                    break
            else:
                break

        return None

    def get_single_selected_node(self):
        """If view has a single selection equal to a node's region, return this node.

        :return: node or None
        """
        if len(self.view.sel()) != 1:
            return None
        
        return self.find_node_by_exact_region(self.view.sel()[0])

    def invalidate(self, edit):
        self.done_editing()
        with read_only_set_to(self.view, False):
            self.view.replace(
                edit, sublime.Region(0, self.view.size()),
                "<<<<< Codebrowser contents outdated. Please refresh! >>>>>"
            )

    def replace_value_node(self, edit, path, new_value):
        """Replace value node at given path with new_value"""
        node = self.root.value_node_at(path)

        if node is self.node_being_edited:
            reg = self.region_edit_helper.enclosing_reg()
            self.done_editing()
        else:
            reg = node.region

        with read_only_set_to(self.view, False):
            cur = Cursor(reg.a, self.view, edit)
            cur.erase(reg.b)

            inserter = make_js_value_inserter(cur, new_value, node.nesting)
            new_node, new_region = self.insert_js_value(inserter)

        node.parent.replace_value_node_at(node.position, new_node, new_region)

    def replace_key_node(self, edit, path, new_name):
        node = self.root.key_node_at(path)

        if node is self.node_being_edited:
            reg = self.region_edit_helper.enclosing_reg()
            self.done_editing()
        else:
            reg = node.region

        with read_only_set_to(self.view, False):
            self.view.erase(edit, reg)
            cur = Cursor(reg.a, self.view, edit)
            cur.push_region()
            cur.insert(new_name)

        node.parent.replace_key_node_region_at(node.position, cur.pop_region())

    def delete_node(self, edit, path):
        node = self.root.value_node_at(path)
        parent, pos = node.parent, node.position

        enode = self.node_being_edited

        if enode is not None and enode.value_node_or_self is node:
            # If deleting a node that's currently being edited, we terminate editing mode
            # and delete whatever was typed so far by the user. Also handle the case when
            # the user is editing an object key,
            reg = self.region_edit_helper.enclosing_reg()
            if enode.keyval_match:
                reg = reg.cover(enode.keyval_match.region)

            self.done_editing()
        else:
            reg = parent.entries[pos].region
        
        if node.is_first and node.is_last:
            # TODO: deletion of all nodes from the root is not supported
            diereg = sublime.Region(parent.begin + 1, parent.end - 1)
        elif node.is_first:
            diereg = sublime.Region(reg.a, parent.entries[pos + 1].begin)
        else:
            diereg = sublime.Region(parent.entries[pos - 1].end, reg.b)

        with read_only_set_to(self.view, False):
            self.view.erase(edit, diereg)

        parent.delete_at(pos)

    def insert_node(self, edit, path, key, value):
        path, new_index = path[:-1], path[-1]
        parent = self.root.value_node_at(path)
        nesting = parent.nesting + 1

        if (key is not None) != parent.is_object:
            raise RuntimeError("Object/array mismatch")

        if self.is_editing_new_node and self.new_node_parent is parent and\
                self.new_node_position == new_index:
            # In this Code Browser view we were editing the new node which is now being
            # inserted. This is typical after the user commits.
            self.view.erase(edit, self.region_edit_helper.enclosing_reg())
            self.done_editing()

        def insert():
            if parent.num_children == 0:
                cur = Cursor(parent.begin + 1, self.view, edit)
                cur.sep_initial(nesting)
                yield cur
                cur.sep_terminal(nesting)
            elif new_index >= parent.num_children:
                cur = Cursor(parent.entries[-1].end, self.view, edit)
                cur.sep_inter(nesting)
                yield cur
            else:
                cur = Cursor(parent.entries[new_index].begin, self.view, edit)
                yield cur
                cur.sep_inter(nesting)

        with read_only_set_to(self.view, False):
            gen = insert()
            cur = next(gen)

            if key is not None:
                cur.push_region()
                cur.insert(key)
                key_region = cur.pop_region()
                cur.sep_keyval(nesting)
            
            inserter = make_js_value_inserter(cur, value, nesting)
            value_node, value_region = self.insert_js_value(inserter)

            if key is not None:
                parent.insert_at(new_index, key_region, value_node, value_region)
            else:
                parent.insert_at(new_index, value_node, value_region)

            next(gen, None)

    def focus_view(self):
        self.view.window().focus_view(self.view)

    def refresh(self, edit, entries):
        prev_pos = list(self.view.sel())
        prev_viewport_pos = self.view.viewport_position()

        if self.root is not None:
            self.root._erase_regions_full_depth()
            self.root = None

        self.view.set_read_only(False)
        self.view.erase(edit, sublime.Region(0, self.view.size()))
        cur = Cursor(0, self.view, edit)

        root = JsObject()

        cur.sep_initial(nesting=0)
        for (key, value), islast in tracking_last(entries):
            cur.push_region()
            cur.insert(key)
            key_region = cur.pop_region()

            cur.sep_keyval(nesting=0)

            inserter = make_js_value_inserter(cur, value, 0)
            value_node, value_region = self.insert_js_value(inserter)

            root.append(key_region, value_node, value_region)
            
            (cur.sep_terminal if islast else cur.sep_inter)(nesting=0)

        self.root = root
        self.root.put_online(self.view)
        
        self.view.set_read_only(True)
        self.view.window().focus_view(self.view)
        set_selection(self.view, to_regs=prev_pos)
        set_viewport_position(self.view, prev_viewport_pos, False)

    def insert_js_value(self, inserter):
        """Return (node, region)"""
        def insert_object():
            node = JsObject()

            while True:
                cmd, args = next(inserter)
                if cmd == 'pop':
                    return node, args.region

                assert cmd == 'leaf'
                key_region = args.region

                value_node, value_region = insert_any(*next(inserter))
                node.append(key_region, value_node, value_region)

        def insert_array():
            node = JsArray()

            while True:
                cmd, args = next(inserter)
                if cmd == 'pop':
                    return node, args.region

                child_node, child_region = insert_any(cmd, args)
                node.append(child_node, child_region)

        def insert_any(cmd, args):
            if cmd == 'push_object':
                return insert_object()
            elif cmd == 'push_array':
                return insert_array()
            elif cmd == 'leaf':
                return JsLeaf(), args.region
            else:
                assert 0, "Inserter yielded unknown command: {}".format(cmd)

        return insert_any(*next(inserter))

    def set_status_be_pending(self):
        self.view.set_status('livejs_pending', "LiveJS: back-end is processing..")

    def ensure_modifications_within_edit_region(self):
        """If we are in edit mode, undo any modifications outside edit region.

        If we are not in edit mode, do nothing.
        """
        if self.region_edit_helper is None:
            return

        self.region_edit_helper.undo_modifications_outside_edit_region()

    def set_view_read_only_if_region_editing(self):
        """If editing is constrained within a given region, set view's read_only status.

        This depends on cursor (selection) position. Currently, if a module browser is in
        edit mode, the editing is always constrained by a region, i.e. we have no
        unconstrained editing mode.
        """
        if self.region_edit_helper is None:
            return

        self.region_edit_helper.set_read_only()


class CodeBrowserRegionEditHelper(RegionEditHelper):
    def __init__(self, mbrowser, enclosing_reg=None):
        super().__init__(mbrowser.view, mbrowser.EDIT_REGION_KEY,
                         mbrowser.set_edit_region)
        if enclosing_reg is None:
            self.enclosing_reg_offsets = (0, 0)
        else:
            reg = self._get_edit_region()
            self.enclosing_reg_offsets = (reg.a - enclosing_reg.a,
                                          enclosing_reg.b - reg.b)

    def enclosing_reg(self):
        reg = self._get_edit_region()
        return sublime.Region(reg.a - self.enclosing_reg_offsets[0],
                              reg.b + self.enclosing_reg_offsets[1])
