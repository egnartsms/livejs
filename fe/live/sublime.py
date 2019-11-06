import os
import traceback
import json
import functools

import sublime
import sublime_plugin

import live.server as server
from live.eventloop import EventLoop
from live.config import config


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
        g_el.add_coroutine(server.serve(8001, ws_handler), 'server')
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


continuation = None
view = None
resp = None


def ws_handler(ws, msg):
    global resp
    
    msg = json.loads(msg)
    if msg['type'] != 'response':
        return
    resp = msg['response']
    sublime.set_timeout(lambda: view.run_command('do_refresh_code_browser'), 0)


class ToggleServerCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        global g_co, g_el
        if g_el.is_coroutine_live('server'):
            stop_server()
        else:
            start_server()


class InsertItCommand(sublime_plugin.TextCommand):
    def run(self, edit, text):
        self.view.insert(edit, self.view.size(), '\n\n' + text)


class DoRefreshCodeBrowser(sublime_plugin.TextCommand):
    def run(self, edit):
        global continuation, view, resp
        view = None
        c = continuation
        continuation = None
        r = resp
        resp = None
        c(self.view, edit, r)


class RefreshCodeBrowser(sublime_plugin.WindowCommand):
    def run(self):
        cbv = next((v for v in self.window.views() if v.name() == 'live-code-browser'),
                   None)
        if cbv is None:
            cbv = self.window.new_file()
            cbv.set_name('live-code-browser')
            cbv.set_scratch(True)
            cbv.set_syntax_file('Packages/JavaScript/JavaScript.sublime-syntax')

        global continuation, view
        continuation = do_refresh_code_browser
        view = cbv
        server.websocket.enqueue_message('$.sendAllEntries()')


def do_refresh_code_browser(cbv, edit, resp):
    cbv.erase(edit, sublime.Region(0, cbv.size()))
    for key, value in resp:
        cbv.insert(edit, cbv.size(), key + '\n')
        cbv.insert(edit, cbv.size(), value + '\n\n')
    cbv.window().focus_view(cbv)
