import sublime
import sublime_plugin

import re
from functools import partial

from live.util import first_such
from live.gstate import ws_handler
from live.sublime_util.technical_command import thru_technical_command
from live.sublime_util.selection import set_selection
from .view_info import info_for
from .operations import (
    CODE_BROWSER_VIEW_NAME,
    set_edit_region,
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
from .cursor import Cursor


__all__ = [
    'LivejsCbRefresh', 'LivejsCbEdit', 'LivejsCbCommit', 'LivejsCbCancelEdit',
    'LivejsCbDelNode', 'LivejsCbMoveNodeFwd', 'LivejsCbMoveNodeBwd', 'LivejsCbAddNode'
]


class LivejsCbRefresh(sublime_plugin.WindowCommand):
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

        ws_handler.request('$.sendAllEntries()', thru_technical_command(cbv, refresh))


class LivejsCbEdit(sublime_plugin.TextCommand):
    def run(self, edit):
        node = get_single_selected_node(self.view)
        if node is None:
            self.view.run_command('livejs_cb_select')
            return

        edit_node(node)


class LivejsCbCommit(sublime_plugin.TextCommand):
    def run(self, edit):
        vinfo = info_for(self.view)
        if not vinfo.is_editing:
            return  # shoult not normally happen

        if vinfo.is_editing_new_node:
            committed = self._commit_new_node_edit()
        else:
            committed = self._commit_node_edit()

        if committed:
            self.view.set_status('livejs_pending', "LiveJS: back-end is processing..")

    def _commit_new_node_edit(self):
        vinfo = info_for(self.view)
        js = edit_region_contents(self.view)
        if vinfo.new_node_parent.is_object:
            mo = re.match(r'([a-zA-Z0-9_$]+)\s*:(.+)$', js, re.DOTALL)
            if mo is None:
                self.view.window().status_message("Invalid object entry")
                return False

            key, value = mo.group(1), mo.group(2)
        else:
            key, value = '', js

        js = '''
            $.addObjectEntry({parent_path}, {pos}, "{key}",
                             (function () {{ return ({value}) }}))
        '''
        js = js.format(
            parent_path=vinfo.new_node_parent.path,
            pos=vinfo.new_node_position,
            key=key,
            value=value
        )

        ws_handler.request(js)

        return True

    def _commit_node_edit(self):
        vinfo = info_for(self.view)
        node = vinfo.node_being_edited
        js = edit_region_contents(self.view)

        if node.is_key:
            if not re.match(r'[a-zA-Z0-9_$]+$', js):
                self.view.window().status_message("Invalid JS identifier")
                return False
            js = '$.renameKey({}, "{}")'.format(node.path, js)
        else:
            js = (
                '$.replace({}, (function () {{ return ({}); }}));'.format(node.path, js)
            )

        ws_handler.request(js)

        return True


class LivejsCbCancelEdit(sublime_plugin.TextCommand):
    def run(self, edit):
        vinfo = info_for(self.view)
        if not vinfo.is_editing:
            return  # should not happen

        if vinfo.is_editing_new_node:
            self.view.erase(edit, enclosing_edit_region(self.view))
            done_editing(self.view)
        else:
            node = vinfo.node_being_edited
            if node.is_key:
                js = '$.sendKeyAt({})'.format(node.path)
            else:
                js = '$.sendValueAt({})'.format(node.path)

            ws_handler.request(js, partial(on_edit_aborted, view=self.view))


def on_edit_aborted(view, response):
    node = info_for(view).node_being_edited
    
    if node.is_key:
        thru_technical_command(view, replace_key_node)(
            path=node.path, new_name=response
        )
    else:
        thru_technical_command(view, replace_value_node)(
            path=node.path, new_value=response
        )


class LivejsCbMoveNodeFwd(sublime_plugin.TextCommand):
    def run(self, edit):
        node = get_single_selected_node(self.view)
        if node is None:
            return  # should not normally happen, protected by key binding context

        js = '$.move({}, true)'.format(node.path)
        ws_handler.request(js, partial(select_node, view=self.view, key=node.is_key))


class LivejsCbMoveNodeBwd(sublime_plugin.TextCommand):
    def run(self, edit):
        node = get_single_selected_node(self.view)
        if node is None:
            return  # should not normally happen, protected by key binding context

        js = '$.move({}, false)'.format(node.path)
        ws_handler.request(js, partial(select_node, view=self.view, key=node.is_key))


def select_node(view, response, key):
    path = response
    root = info_for(view).root
    node = (root.key_node_at if key else root.value_node_at)(path)

    set_selection(view, to_reg=node.region, show=True)


class LivejsCbDelNode(sublime_plugin.TextCommand):
    def run(self, edit):
        node = get_single_selected_node(self.view)
        if node is None:
            self.view.run_command('livejs_cb_select')
            return

        js = '$.delete({})'.format(node.path)
        ws_handler.request(js)


class LivejsCbAddNode(sublime_plugin.TextCommand):
    def run(self, edit):
        if len(self.view.sel()) != 1:
            self.view.window().status_message("Cannot determine where to add")
            return

        reg = self.view.sel()[0]
        parent = find_containing_node(self.view, reg, strict=True)
        
        if parent is None:
            self.view.window().status_message("Not inside any node")
            return

        if parent.is_leaf:
            self.view.window().status_message("Cannot add here")
            return

        pos = find_insert_position(parent, reg)
        if pos is None:
            self.view.window().status_message("Cannot determine where to add")
            return

        edit_new_node(self.view, edit, parent, pos)
