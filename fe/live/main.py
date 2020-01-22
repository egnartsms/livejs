import sublime
import sublime_plugin

import os
import traceback
import operator as pyop

from live.util import eraise
from live.lowlvl.http_server import serve
from live.lowlvl.eventloop import EventLoop
from live.gstate import config
from live.ws_handler import ws_handler
from live.code import *  # noqa
from live.sublime_util import *  # noqa
from live.modules import *  # noqa
from live.repl import *  # noqa

g_el = EventLoop()


@g_el.register_error_handler
def eventloop_error_handler(msg, exc):
    print(msg)
    if exc is not None:
        traceback.print_exception(type(exc), exc, exc.__traceback__)


def start_server():
    if not g_el.is_coroutine_live('server'):
        print("Starting the server...")
        g_el.add_coroutine(serve(7000, ws_handler), 'server')
        print("Started")


def stop_server():
    if g_el.is_coroutine_live('server'):
        print("Stopping the server...")
        g_el.force_quit_coroutine('server')
        print("Stopped")


def plugin_loaded():
    print("Loading LiveJS...")
    config.be_root = os.path.realpath(os.path.join(__file__, '../../../be'))
    print("BE root:", config.be_root)
    assert not g_el.is_running
    g_el.run_in_new_thread()
    start_server()
    print("Loaded")


def plugin_unloaded():
    print("Unloading LiveJS...")
    stop_server()
    g_el.stop()
    print("Unloaded")


class LivejsToggleServerCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if g_el.is_coroutine_live('server'):
            stop_server()
        else:
            start_server()


class QueryContextProcessor(sublime_plugin.EventListener):
    def on_query_context(self, view, key, operator, operand, match_all):
        
        if operator == sublime.OP_EQUAL:
            op = pyop.eq
        elif operator == sublime.OP_NOT_EQUAL:
            op = pyop.ne
        else:
            return None

        if key == 'livejs_view':
            val = view.settings().get('livejs_view')
        else:
            return None

        return op(val, operand)
