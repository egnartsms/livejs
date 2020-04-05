import os
import sublime

from functools import wraps
from live.browser.operations import module_browser_for
from live.browser.operations import module_browser_view_for_module_id
from live.persist import operations as persist
from live.projects.operations import project_by_id
from live.projects.operations import window_for_project_id
from live.sublime.misc import open_filepath
from live.sublime.on_view_loaded import on_load


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
        view_source = open_filepath(wnd, project.module_filepath(desc['moduleName']))

        @on_load(view_source)
        def _():
            fn(desc, mbrowser, view_source)

    persist_handlers[operation] = wrapper
    return wrapper


@persist_handler
def replace(desc, mbrowser, view_source):
    mbrowser.replace_value_node(desc['path'], desc['newValue'])
    persist.replace_value(
        view_source,
        path=desc['path'], new_value=desc['newValue']
    )


@persist_handler
def rename_key(desc, mbrowser, view_source):
    mbrowser.replace_key_node(desc['path'], desc['newName'])

    persist.rename_key(
        view_source,
        path=desc['path'], new_name=desc['newName']
    )


@persist_handler
def delete(desc, mbrowser, view_source):
    mbrowser.delete_node(desc['path'])

    persist.delete(view_source, path=desc['path'])


@persist_handler
def insert(desc, mbrowser, view_source):
    mbrowser.insert_node(desc['path'], desc['key'], desc['value'])

    persist.insert(
        view_source,
        path=desc['path'], key=desc['key'], value=desc['value']
    )
