import operator as pyop
import os
import sublime
import sublime_plugin
import traceback

# Import all commands, listeners and other things that need to be visible at module level
# by Sublime
from live.browser.edit_command import *  # noqa
from live.browser.listener import *  # noqa
from live.browser.sel_command import *  # noqa
from live.project.command import *  # noqa
from live.repl.command import *  # noqa
from live.repl.listener import *  # noqa
from live.sublime.edit import *  # noqa
from live.sublime.on_view_loaded import *  # noqa
from live.sublime.view_info import *  # noqa

from live.gstate import config
from live.gstate import fe_projects
from live.lowlvl.eventloop import EventLoop
from live.lowlvl.http_server import serve
from live.persist.handler import persist_handlers
from live.project.backend import on_backend_connected
from live.project.datastructure import Project
from live.request_handler import request_handler
from live.ws_handler import ws_handler


g_el = EventLoop()


@g_el.register_error_handler
def eventloop_error_handler(msg, exc):
    print(msg)
    if exc is not None:
        traceback.print_exception(type(exc), exc, exc.__traceback__)


def start_server():
    if not g_el.is_coroutine_live('server'):
        print("Starting the server...")
        g_el.add_coroutine(serve(config.port, request_handler), 'server')
        print("Started")


def stop_server():
    if g_el.is_coroutine_live('server'):
        print("Stopping the server...")
        g_el.force_quit_coroutine('server')
        print("Stopped")


def plugin_loaded():
    assert not g_el.is_running
    
    config.be_root = os.path.realpath(os.path.join(__file__, '../../../be'))
    config.livejs_project = Project(
        id=config.livejs_project_id,
        name='LiveJS',
        path=config.be_root
    )
    fe_projects[:] = [config.livejs_project]
    ws_handler.persist_handlers = persist_handlers
    ws_handler.cb_on_connected = on_backend_connected
    
    g_el.run_in_new_thread()
    start_server()
    print("Loaded LiveJS")


def plugin_unloaded():
    stop_server()
    g_el.stop()
    print("Unloaded LiveJS")


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
            return False

        if key == 'livejs_view':
            val = view.settings().get('livejs_view')
        else:
            return False

        return op(val, operand)
