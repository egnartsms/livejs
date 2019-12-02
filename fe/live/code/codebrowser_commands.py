import sublime
import sublime_plugin

import re
import operator as pyop
from functools import partial

from live.util import first_such
from live import server
from live.sublime_util.technical_command import thru_technical_command
from live.code.cursor import Cursor
from live.code.codebrowser import (
    refresh, info_for, find_containing_node, replace_value_node, replace_key_node,
    find_node_by_exact_region
)


__all__ = ['CodeBrowserEventListener', 'LivejsCbRefresh', 'LivejsCbEdit',
           'LivejsCbCommit', 'LivejsCbCancelEdit', 'LivejsCbSelect',
           'LivejsCbMoveSelNext', 'LivejsCbMoveSelPrev', 'LivejsCbMoveSelOutside',
           'LivejsCbMoveSelInside', 'LivejsCbDelNode', 'LivejsCbMoveNodeFwd',
           'LivejsCbMoveNodeBwd']


class CodeBrowserEventListener(sublime_plugin.ViewEventListener):
    @classmethod
    def is_applicable(cls, settings):
        return settings.get('livejs_view') == 'Code Browser'

    @classmethod
    def applies_to_primary_view_only(cls):
        return True

    def on_query_context(self, key, operator, operand, match_all):
        # print("on_query_context:", key, operator, operand)
        if key not in ('livejs_view', 'livejs_exact_node_selected'):
            return None
        if operator not in (sublime.OP_EQUAL, sublime.OP_NOT_EQUAL):
            return None
        
        op = pyop.eq if operator == sublime.OP_EQUAL else pyop.ne
        if key == 'livejs_view':
            return op(self.view.settings().get('livejs_view'), operand)
        elif key == 'livejs_exact_node_selected':
            return op(get_single_selected_node(self.view) is not None, operand)
        else:
            assert 0, "Programming error: unexpected context key {}".format(key)

    def on_activated(self):
        if server.websocket is None:
            invalidate_codebrowser(self.view)
            return
        vinfo = info_for(self.view)
        if vinfo.root is None:
            invalidate_codebrowser(self.view)


def get_single_selected_node(view):
    if len(view.sel()) != 1:
        return None
    return find_node_by_exact_region(view.sel()[0], view)


def invalidate_codebrowser(view):
    def go(view, edit):
        view.set_read_only(False)
        view.erase(edit, sublime.Region(0, view.size()))
        view.insert(edit, 0, "<<<<< Codebrowser contents outdated. Please refresh! >>>>>")
        view.set_read_only(True)

    thru_technical_command(view, go)()


CODE_BROWSER_VIEW_NAME = "LiveJS: Code Browser"


class LivejsCbRefresh(sublime_plugin.WindowCommand):
    def run(self):
        if server.websocket is None:
            sublime.error_message("BE is not connected")
            return

        cbv = first_such(view for view in self.window.views()
                         if view.settings().get('livejs_view') == 'Code Browser')
        if cbv is None:
            cbv = self.window.new_file()
            cbv.settings().set('livejs_view', 'Code Browser')
            cbv.set_name(CODE_BROWSER_VIEW_NAME)
            cbv.set_scratch(True)
            cbv.set_syntax_file('Packages/JavaScript/JavaScript.sublime-syntax')

        if info_for(cbv).node_being_edited is not None:
            switch_to_view_mode(cbv)

        server.response_callbacks.append(thru_technical_command(cbv, refresh))
        server.websocket.enqueue_message('$.sendAllEntries()')


class LivejsCbEdit(sublime_plugin.TextCommand):
    def run(self, edit):
        if len(self.view.sel()) != 1:
            self.view.window().status_message("Could not determine the node to edit: "
                                              "many cursors")
            return

        r0 = self.view.sel()[0]
        node = find_containing_node(r0, self.view)
        if node is None:
            self.view.window().status_message("Could not determine the node to edit: "
                                              "selected region is not entirely inside a "
                                              "node")
            return

        info_for(self.view).node_being_edited = node
        self.view.set_read_only(False)
        ex_reg = prepare_node_for_editing(self.view, edit, node)
        self.view.add_regions('being_edited', [ex_reg], 'region.greenish', '',
                              sublime.DRAW_NO_FILL | sublime.DRAW_EMPTY)
        self.view.sel().clear()
        self.view.sel().add(node.region)


def prepare_node_for_editing(view, edit, node):
    beg = node.begin
    cur = Cursor(beg, view, edit)
    row, col = view.rowcol(beg)
    cur.insert('\n')
    cur.indent(node.nesting)
    cur.pos = node.end
    cur.insert('\n')
    return sublime.Region(beg, cur.pos)


class LivejsCbCommit(sublime_plugin.TextCommand):
    def run(self, edit):
        node = info_for(self.view).node_being_edited
        [reg] = self.view.get_regions('being_edited')
        js = self.view.substr(reg).strip()

        if node.is_key:
            if not re.match('^[a-zA-Z0-9_]+$', js):
                self.view.window().status_message("Invalid JS identifier")
                return
            jscode = '$.renameKey({}, "{}")'.format(node.path, js)
            server.response_callbacks.append(
                partial(on_edit_key_committed, view=self.view)
            )
        else:
            jscode = (
                '$.replace({}, (function () {{ return ({}); }}));'.format(node.path, js)
            )
            server.response_callbacks.append(
                partial(on_edit_value_committed, view=self.view)
            )
        server.websocket.enqueue_message(jscode)
        self.view.set_status('pending', "LiveJS: back-end is processing..")


def on_edit_value_committed(view, response):
    switch_to_view_mode(view)


def on_edit_key_committed(view, response):
    switch_to_view_mode(view)


def switch_to_view_mode(view):
    """Switch from edit mode to the ordinary view mode"""
    view.erase_status('pending')
    info_for(view).node_being_edited = None
    view.erase_regions('being_edited')
    view.set_read_only(True)


class LivejsCbCancelEdit(sublime_plugin.TextCommand):
    def run(self, edit):
        node = info_for(self.view).node_being_edited

        if node.is_key:
            jscode = '$.sendKeyAt({})'.format(node.path)
        else:
            jscode = '$.sendValueAt({})'.format(node.path)

        server.response_callbacks.append(partial(on_edit_aborted, view=self.view))
        server.websocket.enqueue_message(jscode)


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

    switch_to_view_mode(view)


class LivejsCbSelect(sublime_plugin.TextCommand):
    def run(self, edit):
        if len(self.view.sel()) != 1:
            self.view.window().status_message("Could not determine the node to select: "
                                              "many cursors")
            return

        r0 = self.view.sel()[0]
        node = find_containing_node(r0, self.view)
        if node is None:
            self.view.window().status_message("Could not determine the node to select: "
                                              "selected region is not entirely inside a "
                                              "node")
            return

        self.view.sel().clear()
        self.view.sel().add(node.region)


class LivejsCbMoveSelNext(sublime_plugin.TextCommand):
    def run(self, edit, by_same_kind):
        node = get_single_selected_node(self.view)
        if node is None:
            return  # should not normally happen

        if by_same_kind:
            right = node.following_sibling_circ
        else:
            right = node.textually_following_sibling_circ

        self.view.sel().clear()
        self.view.sel().add(right.region)
        self.view.show(self.view.sel(), True)


class LivejsCbMoveSelPrev(sublime_plugin.TextCommand):
    def run(self, edit, by_same_kind):
        node = get_single_selected_node(self.view)
        if node is None:
            return  # should not normally happen

        if by_same_kind:
            left = node.preceding_sibling_circ
        else:
            left = node.textually_preceding_sibling_circ
        
        self.view.sel().clear()
        self.view.sel().add(left.region)
        self.view.show(self.view.sel(), True)


class LivejsCbMoveSelOutside(sublime_plugin.TextCommand):
    def run(self, edit):
        node = get_single_selected_node(self.view)
        if node is None:
            return  # should not normally happen

        up = node.parent
        if up.is_root:
            return

        self.view.sel().clear()
        self.view.sel().add(up.region)
        self.view.show(self.view.sel(), True)


class LivejsCbMoveSelInside(sublime_plugin.TextCommand):
    def run(self, edit, into_key):
        node = get_single_selected_node(self.view)
        if node is None:
            return  # should not normally happen

        if node.is_leaf or not node:
            return

        if into_key and node.is_object:
            down = node.key_nodes[0]
        else:
            down = node.value_nodes[0]

        self.view.sel().clear()
        self.view.sel().add(down.region)
        self.view.show(self.view.sel(), True)


class LivejsCbMoveNodeFwd(sublime_plugin.TextCommand):
    def run(self, edit):
        node = get_single_selected_node(self.view)
        if node is None:
            return  # should not normally happen

        jscode = '$.move({}, true)'.format(node.path)
        server.response_callbacks.append(
            partial(select_node, view=self.view, key=node.is_key)
        )
        server.websocket.enqueue_message(jscode)


class LivejsCbMoveNodeBwd(sublime_plugin.TextCommand):
    def run(self, edit):
        node = get_single_selected_node(self.view)
        if node is None:
            return  # should not normally happen

        jscode = '$.move({}, false)'.format(node.path)
        server.response_callbacks.append(
            partial(select_node, view=self.view, key=node.is_key)
        )
        server.websocket.enqueue_message(jscode)


class LivejsCbDelNode(sublime_plugin.TextCommand):
    def run(self, edit):
        node = get_single_selected_node(self.view)
        if node is None:
            return  # should not normally happen

        jscode = '$.delete({})'.format(node.path)
        server.response_callbacks.append(None)
        server.websocket.enqueue_message(jscode)


def select_node(view, response, key):
    path = response
    root = info_for(view).root
    node = (root.key_node_at if key else root.value_node_at)(path)

    view.sel().clear()
    view.sel().add(node.region)
    view.show(view.sel(), True)
