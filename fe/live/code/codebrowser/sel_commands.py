import sublime_plugin

from live.sublime_util.selection import set_selection
from . import operations as ops


__all__ = [
    'LivejsCbSelect', 'LivejsCbMoveSelNext', 'LivejsCbMoveSelPrev',
    'LivejsCbMoveSelOutside', 'LivejsCbMoveSelInside'
]


class LivejsCbSelect(sublime_plugin.TextCommand):
    def run(self, edit):
        if len(self.view.sel()) != 1:
            self.view.window().status_message("Could not determine the node to select: "
                                              "many cursors")
            return

        r0 = self.view.sel()[0]
        node = ops.find_containing_node(self.view, r0)
        if node.is_root:
            self.view.window().status_message("Could not determine the node to select: "
                                              "selected region is not entirely inside a "
                                              "node")
            return

        set_selection(self.view, to_reg=node.region)


class LivejsCbMoveSelNext(sublime_plugin.TextCommand):
    def run(self, edit, by_same_kind):
        node = ops.get_single_selected_node(self.view)
        if node is None:
            return  # should not normally happen

        if by_same_kind:
            right = node.following_sibling_circ
        else:
            right = node.textually_following_sibling_circ

        set_selection(self.view, to_reg=right.region, show=True)


class LivejsCbMoveSelPrev(sublime_plugin.TextCommand):
    def run(self, edit, by_same_kind):
        node = ops.get_single_selected_node(self.view)
        if node is None:
            return  # should not normally happen

        if by_same_kind:
            left = node.preceding_sibling_circ
        else:
            left = node.textually_preceding_sibling_circ
        
        set_selection(self.view, to_reg=left.region, show=True)


class LivejsCbMoveSelOutside(sublime_plugin.TextCommand):
    def run(self, edit):
        node = ops.get_single_selected_node(self.view)
        if node is None:
            return  # should not normally happen

        up = node.parent
        if up.is_root:
            return

        set_selection(self.view, to_reg=up.region, show=True)


class LivejsCbMoveSelInside(sublime_plugin.TextCommand):
    def run(self, edit, into_key):
        node = ops.get_single_selected_node(self.view)
        if node is None:
            return  # should not normally happen

        if node.is_leaf or not node:
            return

        if into_key and node.is_object:
            down = node.key_nodes[0]
        else:
            down = node.value_nodes[0]

        set_selection(self.view, to_reg=down.region, show=True)
