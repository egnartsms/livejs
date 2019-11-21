import operator as pyop
from functools import partial

import sublime
import sublime_plugin

from live.util import first_such
from live import server
from live.sublime_util.technical_command import thru_technical_command
from live.sublime_util.cursor import Cursor
from live.code.codebrowser import (
    on_refresh, info_for, find_containing_leaf_and_region, replace_node
)


__all__ = ['LivejsCbRefresh', 'LivejsCbEdit', 'LivejsCbCommit', 'LivejsCbCancelEdit',
           'CodeBrowserEventListener']


CODE_BROWSER_VIEW_NAME = "LiveJS: Code Browser"


class CodeBrowserEventListener(sublime_plugin.ViewEventListener):
    @classmethod
    def is_applicable(cls, settings):
        return settings.get('livejs_view') == 'Code Browser'

    @classmethod
    def applies_to_primary_view_only(cls):
        return True

    def on_query_context(self, key, operator, operand, match_all):
        if key != 'livejs_view':
            return None
        if operator not in (sublime.OP_EQUAL, sublime.OP_NOT_EQUAL):
            return False
        
        op = pyop.eq if operator == sublime.OP_EQUAL else pyop.ne
        return op(self.view.settings().get('livejs_view'), operand)

    def on_activated(self):
        if server.websocket is None:
            invalidate_codebrowser(self.view)
            return
        vinfo = info_for(self.view)
        if vinfo.root is None:
            invalidate_codebrowser(self.view)


def invalidate_codebrowser(view):
    def go(view, edit):
        view.set_read_only(False)
        view.erase(edit, sublime.Region(0, view.size()))
        view.insert(edit, 0, "<<<<< Codebrowser contents outdated. Please refresh! >>>>>")
        view.set_read_only(True)

    thru_technical_command(view, go)()


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

        server.response_callbacks.append(thru_technical_command(cbv, on_refresh))
        server.websocket.enqueue_message('$.sendAllEntries()')


class LivejsCbEdit(sublime_plugin.TextCommand):
    def run(self, edit):
        if len(self.view.sel()) != 1:
            self.view.window().status_message(">1 cursors")
            return

        r0 = self.view.sel()[0]
        if r0.size() > 0:
            self.view.window().status_message("must not select any regions")
            return

        obj, reg = find_containing_leaf_and_region(self.view, r0.b)
        if obj is None:
            self.view.window().status_message("not inside a leaf")
            return

        info_for(self.view).jsnode_being_edited = obj

        self.view.set_read_only(False)
        
        beg = Cursor(reg.a, self.view)
        beg.skip_ws_bwd(skip_bol=True)
        end = Cursor(reg.b, self.view, edit)
        end.insert('\n')
        reg = sublime.Region(beg.pos, end.pos)

        self.view.add_regions('being_edited', [reg], 'region.greenish', '',
                              sublime.DRAW_NO_FILL | sublime.DRAW_EMPTY)
        self.view.sel().clear()
        self.view.sel().add(reg)


class LivejsCbCommit(sublime_plugin.TextCommand):
    def run(self, edit):
        jsnode = info_for(self.view).jsnode_being_edited
        [reg] = self.view.get_regions('being_edited')
        js = self.view.substr(reg).strip()

        JSCODE = '''$.edit({}, (function () {{ return ({}); }}));'''.format(
            jsnode.path, js
        )
        server.response_callbacks.append(partial(on_edit_committed, view=self.view))
        server.websocket.enqueue_message(JSCODE)
        self.view.set_status('pending', "LiveJS: back-end is processing..")


def on_edit_committed(view, response):
    switch_to_view_mode(view)


def switch_to_view_mode(view):
    """Switch from edit mode to the ordinary view mode"""
    view.erase_status('pending')
    info_for(view).jsnode_being_edited = None
    view.erase_regions('being_edited')
    view.set_read_only(True)


class LivejsCbCancelEdit(sublime_plugin.TextCommand):
    def run(self, edit):
        path = info_for(self.view).jsnode_being_edited.path
        JSCODE = '''$.sendObjectAt({})'''.format(path)
        server.response_callbacks.append(partial(on_edit_aborted, view=self.view))
        server.websocket.enqueue_message(JSCODE)


def on_edit_aborted(view, response):
    node = info_for(view).jsnode_being_edited
    thru_technical_command(view, replace_node)(path=node.path, new_value=response)
    switch_to_view_mode(view)
