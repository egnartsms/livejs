import sublime

from .command import ModuleBrowserTextCommand
from live.sublime_util.misc import set_selection


__all__ = [
    'LivejsCbSelect', 'LivejsCbMoveSelNext', 'LivejsCbMoveSelPrev',
    'LivejsCbMoveSelOutside', 'LivejsCbMoveSelInside'
]


class LivejsCbSelect(ModuleBrowserTextCommand):
    def run(self):
        if len(self.view.sel()) != 1:
            sublime.status_message("Could not determine the node to select: many cursors")
            return

        [reg] = self.view.sel()
        node = self.mbrowser.find_containing_node(reg, strict=False)
        if node.is_root:
            sublime.status_message("Could not determine the node to select: "
                                   "selected region is not entirely inside a node")
            return

        set_selection(self.view, to=node.region)


class LivejsCbMoveSelNext(ModuleBrowserTextCommand):
    def run(self, by_same_kind):
        node = self.mbrowser.get_single_selected_node()
        if node is None:
            return  # should not normally happen

        if by_same_kind:
            right = node.following_sibling_circ
        else:
            right = node.textually_following_sibling_circ

        set_selection(self.view, to=right.region, show=True)


class LivejsCbMoveSelPrev(ModuleBrowserTextCommand):
    def run(self, by_same_kind):
        node = self.mbrowser.get_single_selected_node()
        if node is None:
            return  # should not normally happen

        if by_same_kind:
            left = node.preceding_sibling_circ
        else:
            left = node.textually_preceding_sibling_circ
        
        set_selection(self.view, to=left.region, show=True)


class LivejsCbMoveSelOutside(ModuleBrowserTextCommand):
    def run(self):
        node = self.mbrowser.get_single_selected_node()
        if node is None:
            return  # should not normally happen

        up = node.parent
        if up.is_root:
            return

        set_selection(self.view, to=up.region, show=True)


class LivejsCbMoveSelInside(ModuleBrowserTextCommand):
    def run(self, into_key):
        node = self.mbrowser.get_single_selected_node()
        if node is None:
            return  # should not normally happen

        if node.is_leaf or node.num_children == 0:
            return

        if into_key and node.is_object:
            down = node.key_nodes[0]
        else:
            down = node.value_nodes[0]

        set_selection(self.view, to=down.region, show=True)
