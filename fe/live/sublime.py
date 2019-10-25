import os
from threading import Thread

import sublime
import sublime_plugin


from live.server import LiveJsServer  # noqa


g_srv = None


def start_server():
    global g_srv

    assert g_srv is None
    print("Starting the server...")
    be_root = os.path.realpath(os.path.join(__file__, '../../../be'))
    print("BE root:", be_root)
    g_srv = LiveJsServer(('127.0.0.1', 8000), backend_root=be_root)
    Thread(target=g_srv.serve_forever).start()
    print("Started")


def stop_server():
    global g_srv

    assert g_srv is not None
    print("Stopping the server...")
    g_srv.shutdown()
    g_srv = None
    print("Stopped")


def plugin_loaded():
    print("Loading LiveJS...")
    start_server()
    print("Loaded")


def plugin_unloaded():
    print("Unloading LiveJS...")
    if g_srv is not None:
        stop_server()
    print("Unloaded")


class ToggleServerCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if g_srv is None:
            start_server()
        else:
            stop_server()


class InsertItCommand(sublime_plugin.TextCommand):
    def run(self, edit, text):
        self.view.insert(edit, self.view.size(), text)
