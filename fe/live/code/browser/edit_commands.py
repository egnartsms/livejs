import re
import sublime
import sublime_plugin

from .command import ModuleBrowserCommand
from .view_info import info_for
from live.code.browser import operations as ops
from live.comm import be_interaction
from live.gstate import fe_modules
from live.modules.datastructures import Module
from live.sublime_util.edit import call_with_edit
from live.sublime_util.selection import set_selection
from live.sublime_util.region_edit import region_edit_helpers

__all__ = [
    'LivejsCbRefresh', 'LivejsBrowseModule', 'LivejsCbEdit', 'LivejsCbCommit',
    'LivejsCbCancelEdit', 'LivejsCbDelNode', 'LivejsCbMoveNodeFwd', 'LivejsCbMoveNodeBwd',
    'LivejsCbAddNode'
]


class LivejsCbRefresh(ModuleBrowserCommand):
    @be_interaction
    def run(self, edit):
        if not ops.is_module_browser(self.view):
            self.view.window().status_message("Not a LiveJS module browser")
            return

        ops.done_editing(self.view)
        entries = yield 'sendAllEntries', {'mid': self.mid}
        # We cannot use the 'edit' argument here since the command is already run, we've
        # already yielded.
        call_with_edit(
            self.view,
            lambda edit: ops.refresh(self.view, edit, entries)
        )


class LivejsBrowseModule(sublime_plugin.WindowCommand):
    @be_interaction
    def run(self, module_id):
        module = Module.with_id(module_id)
        view = ops.find_module_browser(self.window, module)
        if view is None:
            view = ops.new_module_browser(self.window, module)
            entries = yield 'sendAllEntries', {'mid': module.id}
            call_with_edit(view, lambda edit: ops.refresh(view, edit, entries))
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
            sublime.status_message("Cannot determine what to edit "
                                   "(multiple cursors)")
            return

        reg = self.view.sel()[0]
        node = ops.find_containing_node(self.view, reg, strict=False)
        if node.is_root:
            sublime.status_message("Cannot determine what to edit "
                                   "(the cursor is at top level)")
            return

        ops.edit_node(node)


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
        js_entered = ops.edit_region_contents(self.view)
        if vinfo.new_node_parent.is_object:
            keyval_sep = r'=' if vinfo.new_node_parent.is_root else r':'
            mo = re.match(r'([a-zA-Z0-9_$]+)\s*{}\s*(.+)$'.format(keyval_sep),
                          js_entered, re.DOTALL)
            if mo is None:
                sublime.status_message("Invalid object entry")
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
        js_entered = ops.edit_region_contents(self.view)

        if node.is_key:
            if not re.match(r'[a-zA-Z0-9_$]+$', js_entered):
                sublime.status_message("Invalid JS identifier")
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
            self.view.erase(edit, region_edit_helpers[self.view].enclosing_reg())
            ops.done_editing(self.view)
            return

        node = vinfo.node_being_edited
        if node.is_key:
            new_name = yield 'getKeyAt', {
                'mid': self.mid,
                'path': node.path
            }
            call_with_edit(
                self.view,
                lambda edit: ops.replace_key_node(
                    view=self.view,
                    edit=edit,
                    path=node.path,
                    new_name=new_name
                )
            )
        else:
            new_value = yield 'getValueAt', {
                'mid': self.mid,
                'path': node.path
            }
            call_with_edit(
                self.view,
                lambda edit: ops.replace_value_node(
                    view=self.view,
                    edit=edit,
                    path=node.path,
                    new_value=new_value
                )
            )


class LivejsCbMoveNodeFwd(ModuleBrowserCommand):
    @be_interaction
    def run(self, edit):
        node = ops.get_single_selected_node(self.view)
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
        node = ops.get_single_selected_node(self.view)
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
        node = ops.get_single_selected_node(self.view)
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
            sublime.status_message("Cannot determine where to add")
            return

        reg = self.view.sel()[0]
        parent = ops.find_containing_node(self.view, reg, strict=True)

        if parent.is_leaf:
            sublime.status_message("Cannot add here")
            return

        pos = ops.find_insert_position(parent, reg)
        if pos is None:
            sublime.status_message("Cannot determine where to add")
            return

        ops.edit_new_node(self.view, edit, parent, pos)
