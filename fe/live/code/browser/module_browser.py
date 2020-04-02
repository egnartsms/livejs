import sublime

from live.code.browser.nodes import JsArray
from live.code.browser.nodes import JsKey
from live.code.browser.nodes import JsLeaf
from live.code.browser.nodes import JsObject
from live.settings import setting
from live.shared import inspector
from live.shared.backend import interacts_with_backend
from live.shared.cursor import Cursor
from live.shared.inspector import CollapsedInspectee
from live.shared.inspector import ExpandedInspectee
from live.shared.inspector import FuncCollapsedInspectee
from live.shared.inspector import FuncExpandedInspectee
from live.shared.inspector import LeafInspectee
from live.shared.inspector import UnrevealedInspectee
from live.shared.inspector import release_subtree
from live.shared.js_cursor import StructuredCursor
from live.sublime.edit import edit_for
from live.sublime.edit import edits_self_view
from live.sublime.misc import hidden_region_list
from live.sublime.misc import is_subregion
from live.sublime.misc import read_only_set_to
from live.sublime.region_edit import RegionEditHelper
from live.sublime.selection import selection_rowcol_preserved_on_replace
from live.sublime.selection import set_selection
from live.sublime.selection import viewport_and_selection_globally_preserved
from live.sublime.selection import viewport_position_preserved
from live.ws_handler import ws_handler


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
        return StructuredCursor(
            pos, self.view, depth=parent_node.depth,
            inside_what='object' if parent_node.is_object else 'array'
        )

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
                parent.insert_at(
                    new_index, JsKey(key), key_region, value_node, value_region
                )
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

            self.root = self._insert_module_entries(entries)
            self.root.put_online(self.view)

            self.view.window().focus_view(self.view)

    def _insert_module_entries(self, entries):
        cur = StructuredCursor(0, self.view)
        cur.insert('$ = ')

        root = JsObject()

        with cur.laying_out('object') as separate:
            for key, value in entries:
                separate()
                key_node, key_region, value_node, value_region = \
                    self._insert_module_entry(cur, key, value)
                root.append(key_node, key_region, value_node, value_region)

        return root

    def _insert_module_entry(self, cur, key, mem):
        cur.push()
        cur.insert(key)
        key_region = cur.pop_region()
        cur.insert_keyval_sep()

        value_node, value_region = self._insert_module_member(cur, mem)

        return JsKey(key), key_region, value_node, value_region

    def _insert_module_member(self, cur, mem):
        if mem['isTracked']:
            value_node, value_region = self._insert_js_value(cur, mem['value'])
        else:
            inspectee, value_region = self._insert_toplevel_inspectee(cur, mem['value'])
            value_node = inspectee.module_browser_node

        return value_node, value_region

    def _insert_toplevel_inspectee(self, cur, jsval):
        """Insert toplevel inspectee and return (inspectee, region)"""
        cur.push()
        inspectee = inspector.insert_js_value(self, cur, jsval)
        assert isinstance(inspectee, ToplevelInspectee)
        inspectee.module_browser_node = JsLeaf()
        return inspectee, cur.pop_region()

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
                    node.append(JsKey(key), key_region, value_node, value_region)

            return node

        def insert_array(array):
            node = JsArray()

            with cur.laying_out('array') as separate:
                for value in array:
                    separate()
                    subnode, subregion = insert_any(value)
                    node.append(subnode, subregion)

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

    @property
    def inspection_space_id(self):
        return self.module_id

    def make_leaf_inspectee(self, depth, region):
        cls = ToplevelLeafInspectee if depth == 0 else LeafInspectee
        return cls(self, depth, region)

    def make_collapsed_inspectee(self, js_id, depth, region):
        cls = ToplevelCollapsedInspectee if depth == 0 else CollapsedInspectee
        return cls(self, js_id, depth, region)

    def make_expanded_inspectee(self, js_id, js_type, child_nodes, depth, region):
        cls = ToplevelExpandedInspectee if depth == 0 else ExpandedInspectee
        return cls(self, js_id, js_type, child_nodes, depth, region)

    def make_collapsed_function_inspectee(self, js_id, source, depth, region):
        cls = ToplevelFuncCollapsedInspectee if depth == 0 else FuncCollapsedInspectee
        return cls(self, js_id, source, depth, region)

    def make_expanded_function_inspectee(self, js_id, source, depth, region):
        cls = ToplevelFuncExpandedInspectee if depth == 0 else FuncExpandedInspectee
        return cls(self, js_id, source, depth, region)

    def make_unrevealed_inspectee(self, prop, depth, region):
        cls = ToplevelUnrevealedInspectee if depth == 0 else UnrevealedInspectee
        return cls(self, prop, depth, region)

    def replace_inspectee(self, old_inspectee, do):
        with read_only_set_to(self.view, False):
            if not isinstance(old_inspectee, ToplevelInspectee):
                do()
                return

            new_inspectee, new_region = do()

        assert old_inspectee.module_browser_node is not None
        assert new_inspectee.module_browser_node is None

        new_inspectee.module_browser_node = old_inspectee.module_browser_node
        old_inspectee.module_browser_node = None

        # Fix the region
        module_browser_node = new_inspectee.module_browser_node
        with hidden_region_list(self.view, module_browser_node._parent_regkey) as regs:
            regs[module_browser_node.position] = new_region


class ToplevelInspectee:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.module_browser_node = None

    def _get_phantom_contents(self, region):
        s = '<a href="refresh">\u21bb</a>'
        return s + ' ' + super()._get_phantom_contents(region)

    @interacts_with_backend(edits_view=lambda self: self.ihost.view)
    def on_navigate(self, href):
        yield from self._on_navigate(href)

    def _on_navigate(self, href):
        if href != 'refresh':
            yield from super()._on_navigate(href)
            return

        yield from release_subtree(self.ihost, self, include_self=True)

        mbrowser = self.ihost
        ws_handler.run_async_op('browseModuleMember', {
            'mid': mbrowser.module_id,
            'key': self.module_browser_node.keyval_match.key
        })
        member = yield

        with read_only_set_to(mbrowser.view, False):
            [reg] = mbrowser.view.query_phantom(self.phantom_id)
            mbrowser.view.erase(edit_for[mbrowser.view], reg)

            cur = StructuredCursor(reg.a, mbrowser.view, depth=0)
            new_node, new_region = mbrowser._insert_module_member(cur, member)

        mbrowser.root.replace_value_node(self.module_browser_node, new_node, new_region)


class ToplevelLeafInspectee(ToplevelInspectee, LeafInspectee):
    pass


class ToplevelExpandedInspectee(ToplevelInspectee, ExpandedInspectee):
    pass


class ToplevelCollapsedInspectee(ToplevelInspectee, CollapsedInspectee):
    pass


class ToplevelFuncExpandedInspectee(ToplevelInspectee, FuncExpandedInspectee):
    pass


class ToplevelFuncCollapsedInspectee(ToplevelInspectee, FuncCollapsedInspectee):
    pass


class ToplevelUnrevealedInspectee(ToplevelInspectee, UnrevealedInspectee):
    pass


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
