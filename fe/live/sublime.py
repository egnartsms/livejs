import os
import traceback
import json
import re
import collections
from functools import partial

import sublime
import sublime_plugin

import live.server as server
from live.eventloop import EventLoop
from live.config import config
from live.util import first_such, tracking_last


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


def websocket_handler(ws, data):
    data = json.loads(data, object_pairs_hook=collections.OrderedDict)
    if data['type'] == 'msg':
        sublime.message_dialog("LiveJS: {}".format(data['msg']))
        return
    
    if not response_callbacks:
        sublime.error_message("LiveJS: logic error: expected response_callbacks not to "
                              "be empty")
        return

    cb = response_callbacks.pop(0)
    sublime.set_timeout(lambda: cb(resp=data['resp']), 0)


CODE_BROWSER_VIEW_NAME = "LiveJS: Code Browser"


class LivejsRefreshCodeBrowser(sublime_plugin.WindowCommand):
    def run(self):
        cbv = first_such(view for view in self.window.views()
                         if view.name() == CODE_BROWSER_VIEW_NAME)
        if cbv is None:
            cbv = self.window.new_file()
            cbv.set_name(CODE_BROWSER_VIEW_NAME)
            cbv.set_scratch(True)
            cbv.set_syntax_file('Packages/JavaScript/JavaScript.sublime-syntax')

        response_callbacks.append(thru_technical_command(cbv, do_refresh_code_browser))
        server.websocket.enqueue_message('$.sendAllEntries()')


def do_refresh_code_browser(view, edit, resp):
    view.erase(edit, sublime.Region(0, view.size()))
    
    for key, value in resp:
        view.insert(edit, view.size(), key + '\n')
        insert_js_unit(view, edit, value)
        view.insert(edit, view.size(), '\n\n')

    view.window().focus_view(view)


def insert_js_unit(view, edit, obj):
    nesting = 0

    def insert(s):
        view.insert(edit, view.size(), s)

    def indent():
        insert(config.s_indent * nesting)

    def insert_unit(obj):
        if isinstance(obj, list):
            insert_array(obj)
            return
        
        assert isinstance(obj, dict), "Got non-dict: {}".format(obj)
        leaf = obj.get('__leaf_type__')
        if leaf == 'js-value':
            insert(obj['value'])
        elif leaf == 'function':
            insert_function(obj['value'])
        else:
            assert leaf is None
            insert_object(obj)

    def insert_array(arr):
        nonlocal nesting

        if not arr:
            insert("[]")
            return
        insert("[\n")
        nesting += 1
        for item in arr:
            indent()
            insert_unit(item)
            insert(",\n")
        nesting -= 1
        indent()
        insert("]")

    def insert_object(obj):
        nonlocal nesting

        if not obj:
            insert("{}")
            return
        insert("{\n")
        nesting += 1
        for k, v in obj.items():
            indent()
            insert(k)
            insert(': ')
            insert_unit(v)
            insert(',\n')
        nesting -= 1
        indent()
        insert("}")

    def insert_function(source):
        # The last line of a function contains a single closing brace and is indented at
        # the same level as the whole function.  This of course depends on the formatting
        # style but it works for now and is very simple.
        i = source.rfind('\n')
        if i == -1:
            pass

        i += 1
        n = 0
        while i + n < len(source) and ord(source[i + n]) == 32:
            n += 1

        line0, *lines = source.splitlines()
        
        insert(line0)
        insert('\n')
        for line, islast in tracking_last(lines):
            indent()
            if not re.match(r'^\s*$', line):
                insert(line[n:])
            if not islast:
                insert('\n')

    insert_unit(obj)


class LivejsTechnicalCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        print("LivejsTechnicalCommand")
        technical_command_callback(view=self.view, edit=edit)


class InsertItCommand(sublime_plugin.TextCommand):
    def run(self, edit, text, smext):
        print(text, smext)
