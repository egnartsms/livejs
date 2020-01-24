import re
import sublime
import sublime_plugin

from .command import ModuleBrowserTextCommand
from .operations import find_module_browser_view
from .operations import module_browser_for
from .operations import new_module_browser_view
from live.comm import be_interaction
from live.gstate import fe_modules
from live.modules.datastructures import Module
from live.sublime_util.edit import edit_for
from live.sublime_util.misc import set_selection


__all__ = [
    'LivejsCbRefresh', 'LivejsBrowseModule', 'LivejsCbEdit', 'LivejsCbCommit',
    'LivejsCbCancelEdit', 'LivejsCbDelNode', 'LivejsCbMoveNodeFwd', 'LivejsCbMoveNodeBwd',
    'LivejsCbAddNode'
]


class LivejsCbRefresh(ModuleBrowserTextCommand):
    @be_interaction
    def run(self):
        self.mbrowser.done_editing()
        entries = yield 'sendAllEntries', {
            'mid': self.mbrowser.module.id
        }
        self.mbrowser.refresh(entries)


class LivejsBrowseModule(sublime_plugin.WindowCommand):
    @be_interaction
    def run(self, module_id):
        module = Module.with_id(module_id)
        view = find_module_browser_view(self.window, module)
        if view is None:
            view = new_module_browser_view(self.window, module)
            entries = yield 'sendAllEntries', {'mid': module.id}
            module_browser_for(view).refresh(entries)
        else:
            module_browser_for(view).focus_view()

    def input(self, args):
        return ModuleInputHandler()


class ModuleInputHandler(sublime_plugin.ListInputHandler):
    def name(self):
        return 'module_id'

    def list_items(self):
        return [(fe_m.name, fe_m.id) for fe_m in fe_modules]


class LivejsCbEdit(ModuleBrowserTextCommand):
    def run(self):
        if len(self.view.sel()) != 1:
            sublime.status_message("Cannot determine what to edit (multiple cursors)")
            return

        [reg] = self.view.sel()
        node = self.mbrowser.find_containing_node(reg, strict=False)
        if node.is_root:
            sublime.status_message("Cannot determine what to edit "
                                   "(the cursor is at top level)")
            return

        self.mbrowser.edit_node(node)


class LivejsCbCommit(ModuleBrowserTextCommand):
    @be_interaction
    def run(self):
        if not self.mbrowser.is_editing:
            return  # shoult not normally happen

        if self.mbrowser.is_editing_new_node:
            yield from self._commit_new_node_edit()
        else:
            yield from self._commit_node_edit()

    def _commit_new_node_edit(self):
        js_entered = self.mbrowser.edit_region_contents()
        if self.mbrowser.new_node_parent.is_object:
            keyval_sep = r'=' if self.mbrowser.new_node_parent.is_root else r':'
            mo = re.match(r'([a-zA-Z0-9_$]+)\s*{}\s*(.+)$'.format(keyval_sep),
                          js_entered, re.DOTALL)
            if mo is None:
                sublime.status_message("Invalid object entry")
                return

            self.mbrowser.set_status_be_pending()

            yield 'addObjectEntry', {
                'mid': self.mbrowser.module.id,
                'parentPath': self.mbrowser.new_node_parent.path,
                'pos': self.mbrowser.new_node_position,
                'key': mo.group(1),
                'codeValue': mo.group(2)
            }
        else:
            self.mbrowser.set_status_be_pending()

            yield 'addArrayEntry', {
                'mid': self.mbrowser.module.id,
                'parentPath': self.mbrowser.new_node_parent.path,
                'pos': self.mbrowser.new_node_position,
                'codeValue': js_entered
            }

    def _commit_node_edit(self):
        node = self.mbrowser.node_being_edited
        js_entered = self.mbrowser.edit_region_contents()

        if node.is_key:
            if not re.match(r'[a-zA-Z0-9_$]+$', js_entered):
                sublime.status_message("Invalid JS identifier")
                return

            self.mbrowser.set_status_be_pending()

            yield 'renameKey', {
                'mid': self.mbrowser.module.id,
                'path': node.path,
                'newName': js_entered
            }
        else:
            self.mbrowser.set_status_be_pending()

            yield 'replace', {
                'mid': self.mbrowser.module.id,
                'path': node.path,
                'codeNewValue': js_entered
            }


class LivejsCbCancelEdit(ModuleBrowserTextCommand):
    @be_interaction
    def run(self):
        if not self.mbrowser.is_editing:
            return  # should not happen

        if self.mbrowser.is_editing_new_node:
            self.view.erase(edit_for[self.view], self.mbrowser.reh.enclosing_reg())
            self.mbrowser.done_editing()
            return

        node = self.mbrowser.node_being_edited
        if node.is_key:
            new_name = yield 'getKeyAt', {
                'mid': self.mbrowser.module.id,
                'path': node.path
            }
            self.mbrowser.replace_key_node(node.path, new_name)
        else:
            new_value = yield 'getValueAt', {
                'mid': self.mbrowser.module.id,
                'path': node.path
            }
            self.mbrowser.replace_value_node(node.path, new_value)


class LivejsCbMoveNodeFwd(ModuleBrowserTextCommand):
    @be_interaction
    def run(self):
        node = self.mbrowser.get_single_selected_node()
        if node is None:
            return  # should not normally happen, protected by key binding context

        new_path = yield 'move', {
            'mid': self.mbrowser.module.id,
            'path': node.path,
            'fwd': True
        }
        root = self.mbrowser.root
        node = (root.key_node_at if node.is_key else root.value_node_at)(new_path)
        set_selection(self.view, to_reg=node.region, show=True)


class LivejsCbMoveNodeBwd(ModuleBrowserTextCommand):
    @be_interaction
    def run(self):
        node = self.mbrowser.get_single_selected_node()
        if node is None:
            return  # should not normally happen, protected by key binding context

        new_path = yield 'move', {
            'mid': self.mbrowser.module.id,
            'path': node.path,
            'fwd': False
        }
        root = self.mbrowser.root
        node = (root.key_node_at if node.is_key else root.value_node_at)(new_path)
        set_selection(self.view, to_reg=node.region, show=True)


class LivejsCbDelNode(ModuleBrowserTextCommand):
    @be_interaction
    def run(self):
        node = self.mbrowser.get_single_selected_node()
        if node is None:
            self.view.run_command('livejs_cb_select')
            return

        yield 'deleteEntry', {
            'mid': self.mbrowser.module.id,
            'path': node.path
        }


class LivejsCbAddNode(ModuleBrowserTextCommand):
    def run(self):
        if len(self.view.sel()) != 1:
            sublime.status_message("Cannot determine where to add")
            return

        [reg] = self.view.sel()
        parent = self.mbrowser.find_containing_node(reg, strict=True)

        if parent.is_leaf:
            sublime.status_message("Cannot add here")
            return

        pos = parent.internode_pos(reg)
        if pos is None:
            sublime.status_message("Cannot determine where to add")
            return

        self.mbrowser.edit_new_node(parent, pos)
