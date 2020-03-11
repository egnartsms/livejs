import os
import sublime

from functools import wraps

from .browser.operations import module_browser_for
from .browser.operations import module_browser_view_for_module_id
from .persist import operations as persist
from live.projects.operations import project_by_id
from live.projects.operations import window_for_project_id
from live.sublime_util.on_view_loaded import on_load


persist_handlers = {}


def persist_handler(fn):
    operation = fn.__name__
    assert operation not in persist_handlers

    @wraps(fn)
    def wrapper(desc):
        wnd = window_for_project_id(desc['projectId'])
        project = project_by_id(desc['projectId'])

        if wnd is None or project is None:
            sublime.error_message(
                "LiveJS back-end attempted to use project that the FE does not know about"
            )
            raise RuntimeError

        mb_view = module_browser_view_for_module_id(wnd, desc['moduleId'])
        mbrowser = module_browser_for(mb_view) if mb_view else None
        view_source = open_module_source_view(
            wnd,
            os.path.join(project.path, desc['moduleName'] + '.js')
        )
        fn(desc, mbrowser, view_source)

    persist_handlers[operation] = wrapper
    return wrapper


def open_module_source_view(window, filepath):
    view = window.find_open_file(filepath)
    if view is None:
        focused_view = window.active_view()
        view = window.open_file(filepath)
        window.focus_view(focused_view)
    return view


@persist_handler
def replace(desc, mbrowser, view_source):
    mbrowser.replace_value_node(desc['path'], desc['newValue'])

    @on_load(view_source)
    def _():
        persist.replace_value(
            view_source,
            path=desc['path'], new_value=desc['newValue']
        )


@persist_handler
def rename_key(desc, mbrowser, view_source):
    mbrowser.replace_key_node(desc['path'], desc['newName'])

    @on_load(view_source)
    def _():
        persist.rename_key(
            view_source,
            path=desc['path'], new_name=desc['newName']
        )


@persist_handler
def delete(desc, mbrowser, view_source):
    mbrowser.delete_node(desc['path'])

    @on_load(view_source)
    def _():
        persist.delete(view_source, path=desc['path'])


@persist_handler
def insert(desc, mbrowser, view_source):
    mbrowser.insert_node(desc['path'], desc['key'], desc['value'])

    @on_load(view_source)
    def _():
        persist.insert(
            view_source,
            path=desc['path'], key=desc['key'], value=desc['value']
        )
