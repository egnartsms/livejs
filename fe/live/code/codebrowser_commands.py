import operator as pyop
from functools import partial

import sublime
import sublime_plugin

from live.util import first_such
from live import server
from live.sublime_util.technical_command import thru_technical_command
from live.code.codebrowser import (
    on_refresh, on_value_updated, info_for, find_containing_leaf
)


__all__ = ['LivejsCbRefresh', 'LivejsCbEdit', 'LivejsCbCommit',
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

        obj, reg = find_containing_leaf(self.view, r0.b)
        if obj is None:
            self.view.window().status_message("not inside a leaf")
            return

        info_for(self.view).jsnode_being_edited = obj
        self.view.add_regions('being_edited', [reg], 'region.greenish', '',
                              sublime.DRAW_NO_FILL | sublime.DRAW_EMPTY)
        self.view.sel().clear()
        self.view.sel().add(reg)
        self.view.set_read_only(False)


class LivejsCbCommit(sublime_plugin.TextCommand):
    def run(self, edit):
        jsnode = info_for(self.view).jsnode_being_edited
        [reg] = self.view.get_regions('being_edited')

        JSCODE = '''$.edit({}, (function () {{ return ({}); }}));'''.format(
            jsnode.path, self.view.substr(reg)
        )
        server.response_callbacks.append(partial(on_value_updated, view=self.view))
        server.websocket.enqueue_message(JSCODE)
        self.view.set_status('pending', "LiveJS: back-end is processing..")
