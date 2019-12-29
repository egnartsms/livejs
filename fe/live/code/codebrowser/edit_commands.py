import sublime
import sublime_plugin

import re
from functools import partial

from live.util import first_such
from live.gstate import ws_handler
from live.sublime_util.technical_command import run_technical_command
from live.sublime_util.selection import set_selection
from live.comm import be_interaction
from .view_info import info_for
from .operations import (
    CODE_BROWSER_VIEW_NAME,
    edit_region_contents,
    edit_node,
    enclosing_edit_region,
    edit_new_node,
    done_editing,
    refresh,
    find_containing_node,
    replace_value_node,
    replace_key_node,
    find_insert_position,
    get_single_selected_node
)


__all__ = [
    'LivejsCbRefresh', 'LivejsCbEdit', 'LivejsCbCommit', 'LivejsCbCancelEdit',
    'LivejsCbDelNode', 'LivejsCbMoveNodeFwd', 'LivejsCbMoveNodeBwd', 'LivejsCbAddNode'
]


class LivejsCbRefresh(sublime_plugin.WindowCommand):
    @be_interaction
    def run(self):
        if not ws_handler.is_connected:
            sublime.error_message("BE is not connected")
            return

        cbv = first_such(view for view in self.window.views()
                         if view.settings().get('livejs_view') == 'Code Browser')
        if cbv is None:
            cbv = self.window.new_file()
            cbv.settings().set('livejs_view', 'Code Browser')
            cbv.set_name(CODE_BROWSER_VIEW_NAME)
            cbv.set_scratch(True)
            cbv.set_read_only(True)
            cbv.set_syntax_file('Packages/JavaScript/JavaScript.sublime-syntax')

        done_editing(cbv)

        entries = yield 'sendAllEntries', {}
        run_technical_command(cbv, partial(refresh, entries=entries))


class LivejsCbEdit(sublime_plugin.TextCommand):
    def run(self, edit):
        if len(self.view.sel()) != 1:
            self.view.window().status_message("Cannot determine what to edit "
                                              "(multiple cursors)")
            return

        reg = self.view.sel()[0]
        node = find_containing_node(self.view, reg, strict=False)
        if node.is_root:
            self.view.window().status_message("Cannot determine what to edit "
                                              "(the cursor is at top level)")
            return

        edit_node(node)


class LivejsCbCommit(sublime_plugin.TextCommand):
    @be_interaction
    def run(self, edit):
        vinfo = info_for(self.view)
        if not vinfo.is_editing:
            return  # shoult not normally happen

        if vinfo.is_editing_new_node:
            committed = yield from self._commit_new_node_edit()
        else:
            committed = yield from self._commit_node_edit()

        if committed:
            self.view.set_status('livejs_pending', "LiveJS: back-end is processing..")

    def _commit_new_node_edit(self):
        vinfo = info_for(self.view)
        js_entered = edit_region_contents(self.view)
        if vinfo.new_node_parent.is_object:
            keyval_sep = r'=' if vinfo.new_node_parent.is_root else r':'
            mo = re.match(r'([a-zA-Z0-9_$]+)\s*{}\s*(.+)$'.format(keyval_sep),
                          js_entered, re.DOTALL)
            if mo is None:
                self.view.window().status_message("Invalid object entry")
                return False

            yield 'addObjectEntry', {
                'parentPath': vinfo.new_node_parent.path,
                'pos': vinfo.new_node_position,
                'key': mo.group(1),
                'codeValue': mo.group(2)
            }
        else:
            yield 'addArrayEntry', {
                'parentPath': vinfo.new_node_parent.path,
                'pos': vinfo.new_node_position,
                'codeValue': js_entered
            }

        return True

    def _commit_node_edit(self):
        vinfo = info_for(self.view)
        node = vinfo.node_being_edited
        js_entered = edit_region_contents(self.view)

        if node.is_key:
            if not re.match(r'[a-zA-Z0-9_$]+$', js_entered):
                self.view.window().status_message("Invalid JS identifier")
                return False

            yield 'renameKey', {
                'path': node.path,
                'newName': js_entered
            }
        else:
            yield 'replace', {
                'path': node.path,
                'codeNewValue': js_entered
            }

        return True


class LivejsCbCancelEdit(sublime_plugin.TextCommand):
    @be_interaction
    def run(self, edit):
        vinfo = info_for(self.view)
        if not vinfo.is_editing:
            return  # should not happen

        if vinfo.is_editing_new_node:
            self.view.erase(edit, enclosing_edit_region(self.view))
            done_editing(self.view)
            return

        node = vinfo.node_being_edited
        if node.is_key:
            new_name = yield 'getKeyAt', {'path': node.path}
            run_technical_command(
                self.view,
                partial(replace_key_node, path=node.path, new_name=new_name)
            )
        else:
            new_value = yield 'getValueAt', {'path': node.path}
            run_technical_command(
                self.view,
                partial(replace_value_node, path=node.path, new_value=new_value)
            )


class LivejsCbMoveNodeFwd(sublime_plugin.TextCommand):
    @be_interaction
    def run(self, edit):
        node = get_single_selected_node(self.view)
        if node is None:
            return  # should not normally happen, protected by key binding context

        new_path = yield 'move', {
            'path': node.path,
            'fwd': True
        }
        root = info_for(self.view).root
        node = (root.key_node_at if node.is_key else root.value_node_at)(new_path)
        set_selection(self.view, to_reg=node.region, show=True)


class LivejsCbMoveNodeBwd(sublime_plugin.TextCommand):
    @be_interaction
    def run(self, edit):
        node = get_single_selected_node(self.view)
        if node is None:
            return  # should not normally happen, protected by key binding context

        new_path = yield 'move', {
            'path': node.path,
            'fwd': False
        }
        root = info_for(self.view).root
        node = (root.key_node_at if node.is_key else root.value_node_at)(new_path)
        set_selection(self.view, to_reg=node.region, show=True)


class LivejsCbDelNode(sublime_plugin.TextCommand):
    @be_interaction
    def run(self, edit):
        node = get_single_selected_node(self.view)
        if node is None:
            self.view.run_command('livejs_cb_select')
            return

        yield 'deleteEntry', {
            'path': node.path
        }


class LivejsCbAddNode(sublime_plugin.TextCommand):
    def run(self, edit):
        if len(self.view.sel()) != 1:
            self.view.window().status_message("Cannot determine where to add")
            return

        reg = self.view.sel()[0]
        parent = find_containing_node(self.view, reg, strict=True)

        if parent.is_leaf:
            self.view.window().status_message("Cannot add here")
            return

        pos = find_insert_position(parent, reg)
        if pos is None:
            self.view.window().status_message("Cannot determine where to add")
            return

        edit_new_node(self.view, edit, parent, pos)
