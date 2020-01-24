import sublime

from functools import wraps

from .browser.operations import find_module_browser_view
from .browser.operations import module_browser_for
from .persist import operations as persist
from live.modules.datastructures import Module
from live.sublime_util.edit import call_with_edit
from live.sublime_util.on_view_loaded import on_load


persist_handlers = {}


def persist_handler(fn):
    request_name = fn.__name__
    assert request_name not in persist_handlers

    @wraps(fn)
    def wrapper(request):
        module = Module.with_id(request['mid'])
        # TODO: for now we ignore other windows except the active one
        mb_view = find_module_browser_view(sublime.active_window(), module)
        mbrowser = module_browser_for(mb_view)
        view_source = open_module_source_view(sublime.active_window(), module.path)
        fn(request, mbrowser, view_source)

    persist_handlers[request_name] = wrapper
    return wrapper


def open_module_source_view(window, filepath):
    view = window.find_open_file(filepath)
    if view is None:
        focused_view = window.active_view()
        view = window.open_file(filepath)
        window.focus_view(focused_view)
    return view


@persist_handler
def replace(request, mbrowser, view_source):
    mbrowser.replace_value_node(request['path'], request['newValue'])

    @on_load(view_source)
    def _():
        call_with_edit(
            view_source,
            lambda edit: persist.replace_value(
                view=view_source,
                edit=edit,
                path=request['path'],
                new_value=request['newValue']
            )
        )


@persist_handler
def rename_key(request, mbrowser, view_source):
    mbrowser.replace_key_node(request['path'], request['newName'])

    @on_load(view_source)
    def _():
        persist.rename_key(
            view_source,
            path=request['path'], new_name=request['newName']
        )


@persist_handler
def delete(request, mbrowser, view_source):
    mbrowser.delete_node(request['path'])

    @on_load(view_source)
    def _():
        persist.delete(view_source, path=request['path'])


@persist_handler
def insert(request, mbrowser, view_source):
    mbrowser.insert_node(request['path'], request['key'], request['value'])

    @on_load(view_source)
    def _():
        persist.insert(
            view_source,
            path=request['path'], key=request['key'], value=request['value']
        )
