import re
import sublime

from .command import ModuleBrowserCommandMixin
from .operations import module_browser_for
from .operations import module_browser_view_for_module_id
from .operations import new_module_browser_view
from live.projects.datastructures import Module
from live.projects.operations import project_for_window
from live.settings import setting
from live.shared.backend import BackendInteractingTextCommand
from live.shared.backend import BackendInteractingWindowCommand
from live.shared.backend import is_interaction_possible
from live.shared.command import TextCommand
from live.shared.input_handlers import ModuleInputHandler
from live.sublime.edit import edit_for
from live.sublime.selection import set_selection
from live.util.method import method
from live.ws_handler import ws_handler


__all__ = [
    'LivejsCbRefresh', 'LivejsBrowseModule', 'LivejsCbEdit', 'LivejsCbCommit',
    'LivejsCbCancelEdit', 'LivejsCbDelNode', 'LivejsCbMoveNodeFwd', 'LivejsCbMoveNodeBwd',
    'LivejsCbAddNode'
]


class LivejsCbRefresh(BackendInteractingTextCommand, ModuleBrowserCommandMixin):
    @method.primary
    def run(self):
        self.mbrowser.done_editing()
        ws_handler.run_async_op('sendAllEntries', {
            'mid': self.mbrowser.module_id
        })
        entries = yield
        self.mbrowser.refresh(entries)


class LivejsBrowseModule(BackendInteractingWindowCommand):
    @method.primary
    def run(self, module):
        module = Module(id=module['id'], name=module['name'])
        view = module_browser_view_for_module_id(self.window, module.id)
        if view is None:
            view = new_module_browser_view(self.window, module)
            ws_handler.run_async_op('sendAllEntries', {'mid': module.id})
            entries = yield
            module_browser_for(view).refresh(entries)
        else:
            module_browser_for(view).focus_view()

    def input(self, args):
        if not is_interaction_possible() or not project_for_window(self.window):
            return None

        modules = ws_handler.run_sync_op('getProjectModules', {
            'projectId': setting.project_id[self.window]
        })

        return ModuleInputHandler(modules)


class LivejsCbEdit(TextCommand, ModuleBrowserCommandMixin):
    @method.primary
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


class LivejsCbCommit(BackendInteractingTextCommand, ModuleBrowserCommandMixin):
    @method.primary
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

            ws_handler.run_async_op('addObjectEntry', {
                'mid': self.mbrowser.module_id,
                'parentPath': self.mbrowser.new_node_parent.path,
                'pos': self.mbrowser.new_node_position,
                'key': mo.group(1),
                'codeValue': mo.group(2)
            })
        else:
            self.mbrowser.set_status_be_pending()

            ws_handler.run_async_op('addArrayEntry', {
                'mid': self.mbrowser.module_id,
                'parentPath': self.mbrowser.new_node_parent.path,
                'pos': self.mbrowser.new_node_position,
                'codeValue': js_entered
            })
        
        yield

    def _commit_node_edit(self):
        node = self.mbrowser.node_being_edited
        js_entered = self.mbrowser.edit_region_contents()

        if node.is_key:
            if not re.match(r'[a-zA-Z0-9_$]+$', js_entered):
                sublime.status_message("Invalid JS identifier")
                return

            self.mbrowser.set_status_be_pending()

            ws_handler.run_async_op('renameKey', {
                'mid': self.mbrowser.module_id,
                'path': node.path,
                'newName': js_entered
            })
        else:
            self.mbrowser.set_status_be_pending()

            ws_handler.run_async_op('replace', {
                'mid': self.mbrowser.module_id,
                'path': node.path,
                'codeNewValue': js_entered
            })

        yield


class LivejsCbCancelEdit(BackendInteractingTextCommand, ModuleBrowserCommandMixin):
    @method.primary
    def run(self):
        if not self.mbrowser.is_editing:
            return  # should not happen

        if self.mbrowser.is_editing_new_node:
            self.view.erase(edit_for[self.view], self.mbrowser.reh.enclosing_reg())
            self.mbrowser.done_editing()
            return

        node = self.mbrowser.node_being_edited
        if node.is_key:
            ws_handler.run_async_op('getKeyAt', {
                'mid': self.mbrowser.module_id,
                'path': node.path
            })
            new_name = yield
            self.mbrowser.replace_key_node(node.path, new_name)
        else:
            ws_handler.run_async_op('getValueAt', {
                'mid': self.mbrowser.module_id,
                'path': node.path
            })
            new_value = yield
            self.mbrowser.replace_value_node(node.path, new_value)


class LivejsCbMoveNodeFwd(BackendInteractingTextCommand, ModuleBrowserCommandMixin):
    @method.primary
    def run(self):
        node = self.mbrowser.get_single_selected_node()
        if node is None:
            return  # should not normally happen, protected by key binding context

        ws_handler.run_async_op('move', {
            'mid': self.mbrowser.module_id,
            'path': node.path,
            'fwd': True
        })
        new_path = yield
        root = self.mbrowser.root
        node = (root.key_node_at if node.is_key else root.value_node_at)(new_path)
        set_selection(self.view, to=node.region, show=True)


class LivejsCbMoveNodeBwd(BackendInteractingTextCommand, ModuleBrowserCommandMixin):
    @method.primary
    def run(self):
        node = self.mbrowser.get_single_selected_node()
        if node is None:
            return  # should not normally happen, protected by key binding context

        ws_handler.run_async_op('move', {
            'mid': self.mbrowser.module_id,
            'path': node.path,
            'fwd': False
        })
        new_path = yield
        root = self.mbrowser.root
        node = (root.key_node_at if node.is_key else root.value_node_at)(new_path)
        set_selection(self.view, to=node.region, show=True)


class LivejsCbDelNode(BackendInteractingTextCommand, ModuleBrowserCommandMixin):
    @method.primary
    def run(self):
        node = self.mbrowser.get_single_selected_node()
        if node is None:
            self.view.run_command('livejs_cb_select')
            return

        ws_handler.run_async_op('deleteEntry', {
            'mid': self.mbrowser.module_id,
            'path': node.path
        })
        yield


class LivejsCbAddNode(TextCommand, ModuleBrowserCommandMixin):
    @method.primary
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
