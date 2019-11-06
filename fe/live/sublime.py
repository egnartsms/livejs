import os
import traceback

try:
    import sublime
    import sublime_plugin

    g_insublime = True
except ImportError:
    g_insublime = False


import live.server as server
from live.eventloop import EventLoop
from live.config import config


g_el = EventLoop()


@g_el.register_error_handler
def eventloop_error_handler(msg):
    print("Eventloop error:", msg)


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


def ws_handler(ws, msg):
    sublime.active_window().active_view().run_command('insert_it', {
        'text': msg
    })


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


class SendToBrowser(sublime_plugin.TextCommand):
    def run(self, edit):
        text = self.view.substr(sublime.Region(0, self.view.size()))
        server.websocket.enqueue_message(text)
