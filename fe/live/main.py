import sublime
import sublime_plugin

import operator as pyop
import os
import traceback

from live.code import *  # noqa
from live.gstate import config
from live.gstate import fe_projects
from live.lowlvl.eventloop import EventLoop
from live.lowlvl.http_server import serve
from live.projects import *  # noqa
from live.projects.datastructures import Project
from live.repl import *  # noqa
from live.request_handler import request_handler
from live.sublime import *  # noqa


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
