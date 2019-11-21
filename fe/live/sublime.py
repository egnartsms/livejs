import os
import traceback

import sublime
import sublime_plugin

from live import server
from live.eventloop import EventLoop
from live.config import config
from live.code import *  # noqa
from live.sublime_util import *  # noqa

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
        g_el.add_coroutine(server.serve(8001), 'server')
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


class LivejsIndicate(sublime_plugin.TextCommand):
    def run(self, edit, msg):
        self.view.window().status_message(msg)
