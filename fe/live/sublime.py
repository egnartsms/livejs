import os
import traceback
import json
import re
import collections
import operator as pyop
from functools import partial

import sublime
import sublime_plugin

import live.server as server
from live.eventloop import EventLoop
from live.config import config
from live.util import first_such, tracking_last
from live import codebrowser
from live.codebrowser import PerViewInfoDiscarder


g_el = EventLoop()


@g_el.register_error_handler
def eventloop_error_handler(msg, exc):
    print(msg)
    if exc is not None:
        traceback.print_exception(type(exc), exc, exc.__traceback__)


def start_server():
    global g_el
    if not g_el.is_coroutine_live('server'):
        print("Starting the server...")
        g_el.add_coroutine(server.serve(8001, websocket_handler), 'server')
        print("Started")


def stop_server():
    global g_el
    if g_el.is_coroutine_live('server'):
        print("Stopping the server...")
        g_el.force_quit_coroutine('server')
        print("Stopped")


def plugin_loaded():
    global g_el
    print("Loading LiveJS...")
    config.be_root = os.path.realpath(os.path.join(__file__, '../../../be'))
    print("BE root:", config.be_root)
    assert not g_el.is_running
    g_el.run_in_new_thread()
    start_server()
    print("Loaded")


def plugin_unloaded():
    global g_el
    print("Unloading LiveJS...")
    stop_server()
    g_el.stop()
    print("Unloaded")


class ToggleServerCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        global g_co, g_el
        if g_el.is_coroutine_live('server'):
            stop_server()
        else:
            start_server()


response_callbacks = []
technical_command_callback = None


def thru_technical_command(view, final_callback):
    def callback(*args, **kwargs):
        global technical_command_callback
        technical_command_callback = partial(final_callback, *args, **kwargs)
        try:
            view.run_command('livejs_technical')
        finally:
            technical_command_callback = None

    return callback


class LivejsTechnicalCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        technical_command_callback(view=self.view, edit=edit)


def websocket_handler(ws, data):
    data = json.loads(data, object_pairs_hook=collections.OrderedDict)
    if data['type'] == 'msg':
        print(data['msg'])
        return
    
    if not response_callbacks:
        sublime.error_message("LiveJS: logic error: expected response_callbacks not to "
                              "be empty")
        return

    cb = response_callbacks.pop(0)
    sublime.set_timeout(lambda: cb(resp=data['resp']), 0)


CODE_BROWSER_VIEW_NAME = "LiveJS: Code Browser"


class LivejsRefreshCb(sublime_plugin.WindowCommand):
    def run(self):
        if server.websocket is None:
            sublime.error_message("BE did not connect yet")
            return

        cbv = first_such(view for view in self.window.views()
                         if view.settings().get('livejs_view') == 'Code Browser')
        if cbv is None:
            cbv = self.window.new_file()
            cbv.settings().set('livejs_view', 'Code Browser')
            cbv.set_name(CODE_BROWSER_VIEW_NAME)
            cbv.set_scratch(True)
            cbv.set_syntax_file('Packages/JavaScript/JavaScript.sublime-syntax')

        response_callbacks.append(thru_technical_command(cbv, codebrowser.reset))
        server.websocket.enqueue_message('$.sendAllEntries()')


class LivejsIndicate(sublime_plugin.TextCommand):
    def run(self, edit, msg):
        self.view.window().status_message(msg)


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


class LivejsCbSelect(sublime_plugin.TextCommand):
    def run(self, edit):
        if len(self.view.sel()) != 1:
            self.view.window().status_message(">1 cursors")
            return

        r0 = self.view.sel()[0]
        if r0.size() > 0:
            self.view.window().status_message("must not select any regions")
            return

        try:
            obj, reg = codebrowser.find_innermost_region(self.view, r0.b)
        except Exception:
            self.view.window().status_message("error finding innermost region")
            raise

        self.view.sel().clear()
        self.view.sel().add(reg)
