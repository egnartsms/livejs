import sublime_plugin

import re
from functools import partial

from live.gstate import fe_modules
from live.sublime_util.technical_command import run_technical_command
from live.sublime_util.selection import set_selection
from live.modules.datastructures import Module
from live.comm import be_interaction
from .view_info import info_for
from .operations import (
    find_module_browser,
    new_module_browser,
    is_module_browser,
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
from .command import ModuleBrowserCommand


__all__ = [
    'LivejsCbRefresh', 'LivejsBrowseModule', 'LivejsCbEdit', 'LivejsCbCommit',
    'LivejsCbCancelEdit', 'LivejsCbDelNode', 'LivejsCbMoveNodeFwd', 'LivejsCbMoveNodeBwd',
    'LivejsCbAddNode'
]


class LivejsCbRefresh(ModuleBrowserCommand):
    @be_interaction
    def run(self, edit):
        if not is_module_browser(self.view):
            self.view.window().status_message("Not a LiveJS module browser")
            return

        done_editing(self.view)
        entries = yield 'sendAllEntries', {'mid': self.mid}
        # We cannot use the 'edit' argument here since the command is already run, we've
        # already yielded.
        run_technical_command(self.view, partial(refresh, entries=entries))


class LivejsBrowseModule(sublime_plugin.WindowCommand):
    @be_interaction
    def run(self, module_id):
        module = Module.with_id(module_id)
        view = find_module_browser(self.window, module)
        if view is None:
            view = new_module_browser(self.window, module)
            entries = yield 'sendAllEntries', {'mid': module.id}
            run_technical_command(view, partial(refresh, entries=entries))
        else:
            self.window.focus_view(view)

    def input(self, args):
        return ModuleInputHandler()


class ModuleInputHandler(sublime_plugin.ListInputHandler):
    def name(self):
        return 'module_id'

    def list_items(self):
        return [
            (fe_m.name, fe_m.id)
            for fe_m in fe_modules
        ]


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


class LivejsCbCommit(ModuleBrowserCommand):
    @be_interaction
    def run(self, edit):
        vinfo = info_for(self.view)
        if not vinfo.is_editing:
            return  # shoult not normally happen

        if vinfo.is_editing_new_node:
            yield from self._commit_new_node_edit()
        else:
            yield from self._commit_node_edit()

    def _commit_new_node_edit(self):
        vinfo = info_for(self.view)
        js_entered = edit_region_contents(self.view)
        if vinfo.new_node_parent.is_object:
            keyval_sep = r'=' if vinfo.new_node_parent.is_root else r':'
            mo = re.match(r'([a-zA-Z0-9_$]+)\s*{}\s*(.+)$'.format(keyval_sep),
                          js_entered, re.DOTALL)
            if mo is None:
                self.view.window().status_message("Invalid object entry")
                return

            self.set_status_be_pending()

            yield 'addObjectEntry', {
                'mid': self.mid,
                'parentPath': vinfo.new_node_parent.path,
                'pos': vinfo.new_node_position,
                'key': mo.group(1),
                'codeValue': mo.group(2)
            }
        else:
            self.set_status_be_pending()

            yield 'addArrayEntry', {
                'mid': self.mid,
                'parentPath': vinfo.new_node_parent.path,
                'pos': vinfo.new_node_position,
                'codeValue': js_entered
            }

    def _commit_node_edit(self):
        vinfo = info_for(self.view)
        node = vinfo.node_being_edited
        js_entered = edit_region_contents(self.view)

        if node.is_key:
            if not re.match(r'[a-zA-Z0-9_$]+$', js_entered):
                self.view.window().status_message("Invalid JS identifier")
                return

            self.set_status_be_pending()

            yield 'renameKey', {
                'mid': self.mid,
                'path': node.path,
                'newName': js_entered
            }
        else:
            self.set_status_be_pending()

            yield 'replace', {
                'mid': self.mid,
                'path': node.path,
                'codeNewValue': js_entered
            }


class LivejsCbCancelEdit(ModuleBrowserCommand):
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
            new_name = yield 'getKeyAt', {
                'mid': self.mid,
                'path': node.path
            }
            run_technical_command(
                self.view,
                partial(replace_key_node, path=node.path, new_name=new_name)
            )
        else:
            new_value = yield 'getValueAt', {
                'mid': self.mid,
                'path': node.path
            }
            run_technical_command(
                self.view,
                partial(replace_value_node, path=node.path, new_value=new_value)
            )


class LivejsCbMoveNodeFwd(ModuleBrowserCommand):
    @be_interaction
    def run(self, edit):
        node = get_single_selected_node(self.view)
        if node is None:
            return  # should not normally happen, protected by key binding context

        new_path = yield 'move', {
            'mid': self.mid,
            'path': node.path,
            'fwd': True
        }
        root = info_for(self.view).root
        node = (root.key_node_at if node.is_key else root.value_node_at)(new_path)
        set_selection(self.view, to_reg=node.region, show=True)


class LivejsCbMoveNodeBwd(ModuleBrowserCommand):
    @be_interaction
    def run(self, edit):
        node = get_single_selected_node(self.view)
        if node is None:
            return  # should not normally happen, protected by key binding context

        new_path = yield 'move', {
            'mid': self.mid,
            'path': node.path,
            'fwd': False
        }
        root = info_for(self.view).root
        node = (root.key_node_at if node.is_key else root.value_node_at)(new_path)
        set_selection(self.view, to_reg=node.region, show=True)


class LivejsCbDelNode(ModuleBrowserCommand):
    @be_interaction
    def run(self, edit):
        node = get_single_selected_node(self.view)
        if node is None:
            self.view.run_command('livejs_cb_select')
            return

        yield 'deleteEntry', {
            'mid': self.mid,
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
