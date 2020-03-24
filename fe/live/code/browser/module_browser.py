import contextlib
import functools
import sublime

from .nodes import JsArray
from .nodes import JsLeaf
from .nodes import JsObject
from live.common.misc import tracking_last
from live.settings import setting
from live.shared.cursor import Cursor
from live.shared.js_cursor import StructuredCursor
from live.sublime.edit import edit_for
from live.sublime.edit import edits_self_view
from live.sublime.misc import is_subregion
from live.sublime.misc import read_only_set_to
from live.sublime.region_edit import RegionEditHelper
from live.sublime.selection import selection_rowcol_preserved_on_replace
from live.sublime.selection import set_selection
from live.sublime.selection import viewport_and_selection_globally_preserved
from live.sublime.selection import viewport_position_preserved


class ModuleBrowser:
    EDIT_REGION_KEY = 'edit'

    MSG_NEEDS_REFRESH = "<<< Module browser is out of sync. Please refresh! >>>"

    def __init__(self, view):
        self.view = view
        self.module_id = setting.module_id[view]
        self.root = None
        self.node_being_edited = None
        self.is_editing = False
        self.new_node_parent = None
        self.new_node_position = None
        self.reh = None
        self.is_pristine = True

    @property
    def is_online(self):
        """Whether the module browser displays actual module contents.

        In case the BE disconnects, the module browser goes offline: it displays some
        placeholder text.
        """
        return not self.is_offline

    @property
    def is_offline(self):
        return self.root is None

    @property
    def is_editing_new_node(self):
        return self.is_editing and self.node_being_edited is None

    @property
    def edit_region(self):
        [reg] = self.view.get_regions(self.EDIT_REGION_KEY)
        return reg

    @edit_region.setter
    def edit_region(self, reg):
        self.view.add_regions(self.EDIT_REGION_KEY, [reg], 'region.bluish livejs.edit',
                              '', sublime.DRAW_EMPTY | sublime.DRAW_NO_OUTLINE)

    def edit_region_contents(self):
        return self.view.substr(self.edit_region).strip()

    def discard_edit_region(self):
        self.view.erase_regions(self.EDIT_REGION_KEY)

    def _make_cursor(self, pos, parent_node):
        return StructuredCursor(pos, self.view, depth=parent_node.depth, 
                                is_inside_object=parent_node.is_object)

    @edits_self_view
    def prepare_for_activation(self):
        """Invalidate the view before first activating it"""
        if self.is_offline and self.is_pristine:
            with read_only_set_to(self.view, False):
                self.view.replace(
                    edit_for[self.view],
                    sublime.Region(0, self.view.size()),
                    self.MSG_NEEDS_REFRESH
                )
                self.is_pristine = False

    def edit_node(self, node):
        """Start editing of the specified node"""
        assert not self.is_editing

        self.view.set_read_only(False)
        self.edit_region = node.region
        self.is_editing = True
        self.node_being_edited = node
        self.reh = CodeBrowserRegionEditHelper(self)

    @edits_self_view
    def edit_new_node(self, parent, pos):
        """Start editing the contents of the to-be-added node"""
        self.view.set_read_only(False)

        if parent.is_object:
            def placeholder(cur):
                cur.insert('newKey')
                cur.insert_keyval_sep()
                cur.insert('newValue')
        else:
            def placeholder(cur):
                cur.insert('newValue')

        if 0 == pos == parent.num_children:
            cur = self._make_cursor(parent.begin + 1, parent)
            cur.push()
            cur.insert_initial_sep()
            cur.push()
            placeholder(cur)
            edit_reg = cur.pop_region()
            cur.insert_terminal_sep()
            enclosing_reg = cur.pop_region()
        elif pos < parent.num_children:
            cur = self._make_cursor(parent.entries[pos].begin, parent)
            cur.push()
            cur.push()
            placeholder(cur)
            edit_reg = cur.pop_region()
            cur.insert_inter_sep()
            enclosing_reg = cur.pop_region()
        else:
            cur = self._make_cursor(parent.entries[parent.num_children - 1].end, parent)
            cur.push()
            cur.insert_inter_sep()
            cur.push()
            placeholder(cur)
            edit_reg = cur.pop_region()
            enclosing_reg = cur.pop_region()

        self.edit_region = edit_reg
        set_selection(self.view, to=edit_reg)
        self.is_editing = True
        self.new_node_parent = parent
        self.new_node_position = pos
        self.reh = CodeBrowserRegionEditHelper(self, enclosing_reg)

    def done_editing(self):
        """Ensure the browser is in the ordinary view mode.

        No textual changes to the view are made.
        """
        if not self.is_editing:
            return

        self.view.erase_status('livejs_pending')
        self.discard_edit_region()
        self.view.set_read_only(True)
        self.is_editing = False
        self.node_being_edited = None
        self.new_node_position = None
        self.new_node_parent = None
        self.reh = None

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

    @edits_self_view
    def replace_value_node(self, path, new_value):
        """Replace value node at given path with new_value"""
        node = self.root.value_node_at(path)

        if node is self.node_being_edited:
            reg = self.reh.enclosing_reg()
            self.done_editing()
        else:
            reg = node.region

        with read_only_set_to(self.view, False),\
                selection_rowcol_preserved_on_replace(self.view, reg),\
                viewport_position_preserved(self.view):
            self.view.erase(edit_for[self.view], reg)
            cur = self._make_cursor(reg.a, node.parent)
            new_node, new_region = self._insert_js_value(cur, new_value)

        node.parent.replace_value_node_at(node.position, new_node, new_region)

    @edits_self_view
    def replace_key_node(self, path, new_name):
        node = self.root.key_node_at(path)

        if node is self.node_being_edited:
            reg = self.reh.enclosing_reg()
            self.done_editing()
        else:
            reg = node.region

        with read_only_set_to(self.view, False):
            self.view.erase(edit_for[self.view], reg)
            cur = Cursor(reg.a, self.view)
            cur.push()
            cur.insert(new_name)

        node.parent.replace_key_node_region_at(node.position, cur.pop_region())

    @edits_self_view
    def delete_node(self, path):
        node = self.root.value_node_at(path)
        parent, pos = node.parent, node.position

        enode = self.node_being_edited

        if enode is not None and enode.value_node_or_self is node:
            # If deleting a node that's currently being edited, we terminate editing mode
            # and delete whatever was typed so far by the user. Also handle the case when
            # the user is editing an object key,
            reg = self.reh.enclosing_reg()
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
            self.view.erase(edit_for[self.view], diereg)

        parent.delete_at(pos)

    @edits_self_view
    def insert_node(self, path, key, value):
        path, new_index = path[:-1], path[-1]
        parent = self.root.value_node_at(path)

        if (key is not None) != parent.is_object:
            raise RuntimeError("Object/array mismatch")

        if self.is_editing_new_node and self.new_node_parent is parent and\
                self.new_node_position == new_index:
            # In this Code Browser view we were editing the new node which is now being
            # inserted. This is typical after the user commits. TODO: erase() below won't
            # work if the cursor is outside editing region
            self.view.erase(edit_for[self.view], self.reh.enclosing_reg())
            self.done_editing()

        with read_only_set_to(self.view, False):
            if parent.num_children == 0:
                cur = self._make_cursor(parent.begin + 1, parent)
                cur.insert_initial_sep()
                with cur.pos_preserved():
                    cur.insert_terminal_sep()
            elif new_index >= parent.num_children:
                cur = self._make_cursor(parent.entries[-1].end, parent)
                cur.insert_inter_sep()
            else:
                cur = self._make_cursor(parent.entries[new_index].begin, parent)
                with cur.pos_preserved():
                    cur.insert_inter_sep()

            if key is not None:
                cur.push()
                cur.insert(key)
                key_region = cur.pop_region()
                cur.insert_keyval_sep()
                value_node, value_region = self._insert_js_value(cur, value)
                parent.insert_at(new_index, key_region, value_node, value_region)
            else:
                node, region = self._insert_js_value(cur, value)
                parent.insert_at(new_index, node, region)

    def focus_view(self):
        self.view.window().focus_view(self.view)

    @edits_self_view
    def refresh(self, entries):
        if self.is_online:
            self.root.put_offline()
            self.root = None

        with read_only_set_to(self.view, False),\
                viewport_and_selection_globally_preserved(self.view):
            self.view.erase(edit_for[self.view], sublime.Region(0, self.view.size()))

            cur = StructuredCursor(0, self.view, depth=-1)

            # TODO: fix this hack by getting the whole object from BE, not entries
            from collections import OrderedDict
            root, _ = self._insert_js_value(cur, {
                'type': 'object',
                'value': OrderedDict(entries)
            })

            self.root = root
            self.root.put_online(self.view)

            self.view.window().focus_view(self.view)

    def _insert_js_value(self, cur, jsval):
        """Insert JS serialized value using the structured cursor cur.

        :return: (node, region)
        """

        def insert_object(obj):
            node = JsObject()
            
            with cur.laying_out('object') as separate:
                for key, value in obj.items():
                    separate()
                    cur.push()
                    cur.insert(key)
                    key_region = cur.pop_region()

                    cur.insert_keyval_sep()

                    value_node, value_region = insert_any(value)
                    node.append(key_region, value_node, value_region)

            return node

        def insert_array(array):
            node = JsArray()

            with cur.laying_out('array') as separate:
                for value in array:
                    separate()
                    subnode, region = insert_any(value)
                    node.append(subnode, region)

            return node

        def insert_any(jsval):
            cur.push()

            if jsval['type'] == 'leaf':
                cur.insert(jsval['value'])
                node = JsLeaf()
            elif jsval['type'] == 'function':
                cur.insert_function(jsval['value'])
                node = JsLeaf()
            elif jsval['type'] == 'object':
                node = insert_object(jsval['value'])
            elif jsval['type'] == 'array':
                node = insert_array(jsval['value'])
            else:
                raise RuntimeError("Unexpected jsval: {}".format(jsval))

            return node, cur.pop_region()

        return insert_any(jsval)

    def set_status_be_pending(self):
        self.view.set_status('livejs_pending', "LiveJS: back-end is processing..")

    def ensure_modifications_within_edit_region(self):
        """If we are in edit mode, undo any modifications outside edit region.

        If we are not in edit mode, do nothing.
        """
        if self.reh is None:
            return

        self.reh.undo_modifications_outside_edit_region()

    def set_view_read_only_if_region_editing(self):
        """If editing is constrained within a given region, set view's read_only status.

        This depends on cursor (selection) position. Currently, if a module browser is in
        edit mode, the editing is always constrained by a region, i.e. we have no
        unconstrained editing mode.
        """
        if self.reh is None:
            return

        self.reh.set_read_only()


class CodeBrowserRegionEditHelper(RegionEditHelper):
    def __init__(self, mbrowser, enclosing_reg=None):
        super().__init__(
            mbrowser.view,
            lambda: mbrowser.edit_region,
            lambda reg: setattr(mbrowser, 'edit_region', reg)
        )
        if enclosing_reg is None:
            self.enclosing_reg_offsets = (0, 0)
        else:
            reg = self.get_edit_region()
            self.enclosing_reg_offsets = (reg.a - enclosing_reg.a,
                                          enclosing_reg.b - reg.b)

    def enclosing_reg(self):
        reg = self.get_edit_region()
        return sublime.Region(reg.a - self.enclosing_reg_offsets[0],
                              reg.b + self.enclosing_reg_offsets[1])
