import sublime

from functools import wraps

from live.sublime_util.edit import call_with_edit
from live.sublime_util.on_view_loaded import on_load
from live.modules.datastructures import Module
from .browser import operations as browser
from .persist import operations as persist


persist_handlers = {}


def persist_handler(fn):
    request_name = fn.__name__
    assert request_name not in persist_handlers

    @wraps(fn)
    def wrapper(request):
        module = Module.with_id(request['mid'])
        view_browser = browser.find_module_browser(sublime.active_window(), module)
        view_source = open_module_source_view(sublime.active_window(), module.path)
        fn(request, view_browser, view_source)

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
def replace(request, view_browser, view_source):
    call_with_edit(
        view_browser,
        lambda edit: browser.replace_value_node(
            view=view_browser,
            edit=edit,
            path=request['path'],
            new_value=request['newValue']
        )
    )

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
def rename_key(request, view_browser, view_source):
    call_with_edit(
        view_browser,
        lambda edit: browser.replace_key_node(
            view=view_browser,
            edit=edit,
            path=request['path'],
            new_name=request['newName']
        )
    )

    @on_load(view_source)
    def _():
        call_with_edit(
            view_source,
            lambda edit: persist.rename_key(
                view=view_source,
                edit=edit,
                path=request['path'],
                new_name=request['newName']
            )
        )


@persist_handler
def delete(request, view_browser, view_source):
    call_with_edit(
        view_browser,
        lambda edit: browser.delete_node(
            view=view_browser,
            edit=edit,
            path=request['path']
        )
    )

    @on_load(view_source)
    def _():
        call_with_edit(
            view_source,
            lambda edit: persist.delete(
                view=view_source,
                edit=edit,
                path=request['path']
            )
        )


@persist_handler
def insert(request, view_browser, view_source):
    call_with_edit(
        view_browser,
        lambda edit: browser.insert_node(
            view=view_browser,
            edit=edit,
            path=request['path'],
            key=request['key'],
            value=request['value']
        )
    )

    @on_load(view_source)
    def _():
        call_with_edit(
            view_source,
            lambda edit: persist.insert(
                view=view_source,
                edit=edit,
                path=request['path'],
                key=request['key'],
                value=request['value']
            )
        )
