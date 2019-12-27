import sublime

from functools import partial

from live.gstate import config
from live.util import first_such
from live.sublime_util.technical_command import run_technical_command
from live.sublime_util.on_view_loaded import on_load
from .codebrowser import operations as codebrowser
from .persist import operations as persist


persist_handlers = {}


def persist_handler(fn):
    request_name = fn.__name__
    assert request_name not in persist_handlers
    persist_handlers[request_name] = fn
    return fn


def get_module_view(window):
    view = window.find_open_file(config.live_module_filepath)
    if view is None:
        focused_view = window.active_view()
        view = window.open_file(config.live_module_filepath)
        window.focus_view(focused_view)
    return view


@persist_handler
def replace(request):
    cbv = first_such(view for view in sublime.active_window().views()
                     if view.settings().get('livejs_view') == 'Code Browser')
    
    run_technical_command(
        cbv,
        partial(codebrowser.replace_value_node,
                path=request['path'], new_value=request['newValue'])
    )

    module_view = get_module_view(sublime.active_window())

    @on_load(module_view)
    def _():
        run_technical_command(
            module_view,
            partial(persist.replace_value,
                    path=request['path'], new_value=request['newValue'])
        )


@persist_handler
def rename_key(request):
    cbv = first_such(view for view in sublime.active_window().views()
                     if view.settings().get('livejs_view') == 'Code Browser')
    
    run_technical_command(
        cbv,
        partial(codebrowser.replace_key_node,
                path=request['path'],
                new_name=request['newName'])
    )

    module_view = get_module_view(sublime.active_window())

    @on_load(module_view)
    def _():
        run_technical_command(
            module_view,
            partial(persist.rename_key,
                    path=request['path'], new_name=request['newName'])
        )


@persist_handler
def delete(request):
    cbv = first_such(view for view in sublime.active_window().views()
                     if view.settings().get('livejs_view') == 'Code Browser')
    
    run_technical_command(
        cbv,
        partial(codebrowser.delete_node, path=request['path'])
    )

    module_view = get_module_view(sublime.active_window())
    
    @on_load(module_view)
    def _():
        run_technical_command(
            module_view,
            partial(persist.delete, path=request['path'])
        )


@persist_handler
def insert(request):
    cbv = first_such(view for view in sublime.active_window().views()
                     if view.settings().get('livejs_view') == 'Code Browser')
    
    run_technical_command(
        cbv,
        partial(codebrowser.insert_node,
                path=request['path'], key=request['key'], value=request['value'])
    )

    module_view = get_module_view(sublime.active_window())
    
    @on_load(module_view)
    def _():
        run_technical_command(
            module_view,
            partial(persist.insert,
                    path=request['path'], key=request['key'], value=request['value'])
        )
