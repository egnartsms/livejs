import sublime

import os.path
from functools import partial

from live.gstate import config
from live.util import first_such
from live.sublime_util.technical_command import thru_technical_command
from live.sublime_util.on_view_loaded import on_load
from .codebrowser import operations as codebrowser
from .persist import operations as persist


action_handlers = {}


def action_handler(fn):
    action_type = fn.__name__
    assert action_type not in action_handlers
    action_handlers[action_type] = fn
    return fn


def get_module_view(window):
    filename = os.path.join(config.be_root, config.live_module_filename)
    view = window.find_open_file(filename)
    if view is None:
        focused_view = window.active_view()
        view = window.open_file(filename)
        window.focus_view(focused_view)
    return view


@action_handler
def replace(action):
    cbv = first_such(view for view in sublime.active_window().views()
                     if view.settings().get('livejs_view') == 'Code Browser')
    
    thru_technical_command(cbv, codebrowser.replace_value_node)(
        path=action['path'],
        new_value=action['newValue']
    )

    view = get_module_view(sublime.active_window())
    cmd = partial(thru_technical_command(view, persist.replace_value),
                  path=action['path'], new_value=action['newValue'])
    on_load(view, cmd)


@action_handler
def rename_key(action):
    cbv = first_such(view for view in sublime.active_window().views()
                     if view.settings().get('livejs_view') == 'Code Browser')
    
    thru_technical_command(cbv, codebrowser.replace_key_node)(
        path=action['path'],
        new_name=action['newName']
    )

    view = get_module_view(sublime.active_window())
    cmd = partial(thru_technical_command(view, persist.rename_key),
                  path=action['path'], new_name=action['newName'])
    on_load(view, cmd)


@action_handler
def delete(action):
    cbv = first_such(view for view in sublime.active_window().views()
                     if view.settings().get('livejs_view') == 'Code Browser')
    
    thru_technical_command(cbv, codebrowser.delete_node)(path=action['path'])

    view = get_module_view(sublime.active_window())
    cmd = partial(thru_technical_command(view, persist.delete),
                  path=action['path'])
    on_load(view, cmd)


@action_handler
def insert(action):
    cbv = first_such(view for view in sublime.active_window().views()
                     if view.settings().get('livejs_view') == 'Code Browser')
    
    thru_technical_command(cbv, codebrowser.insert_node)(
        path=action['path'], key=action['key'], value=action['value']
    )

    view = get_module_view(sublime.active_window())
    cmd = partial(
        thru_technical_command(view, persist.insert),
        path=action['path'], key=action['key'], value=action['value']
    )
    on_load(view, cmd)
