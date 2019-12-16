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


def get_root_view(window):
    filename = os.path.join(config.be_root, config.root_module)
    root_view = window.find_open_file(filename)
    if root_view is None:
        focused_view = window.active_view()
        root_view = window.open_file(filename)
        window.focus_view(focused_view)
    return root_view


@action_handler
def replace(action):
    cbv = first_such(view for view in sublime.active_window().views()
                     if view.settings().get('livejs_view') == 'Code Browser')
    
    thru_technical_command(cbv, codebrowser.replace_value_node)(
        path=action['path'],
        new_value=action['newValue']
    )

    root_view = get_root_view(sublime.active_window())
    cmd = partial(thru_technical_command(root_view, persist.replace_value),
                  path=action['path'], new_value=action['newValue'])
    on_load(root_view, cmd)


@action_handler
def rename_key(action):
    cbv = first_such(view for view in sublime.active_window().views()
                     if view.settings().get('livejs_view') == 'Code Browser')
    
    thru_technical_command(cbv, codebrowser.replace_key_node)(
        path=action['path'],
        new_name=action['newName']
    )

    root_view = get_root_view(sublime.active_window())
    cmd = partial(thru_technical_command(root_view, persist.rename_key),
                  path=action['path'], new_name=action['newName'])
    on_load(root_view, cmd)


@action_handler
def delete(action):
    cbv = first_such(view for view in sublime.active_window().views()
                     if view.settings().get('livejs_view') == 'Code Browser')
    
    thru_technical_command(cbv, codebrowser.delete_node)(path=action['path'])

    root_view = get_root_view(sublime.active_window())
    cmd = partial(thru_technical_command(root_view, persist.delete),
                  path=action['path'])
    on_load(root_view, cmd)


@action_handler
def insert(action):
    cbv = first_such(view for view in sublime.active_window().views()
                     if view.settings().get('livejs_view') == 'Code Browser')
    
    thru_technical_command(cbv, codebrowser.insert_node)(
        path=action['path'], key=action['key'], value=action['value']
    )

    root_view = get_root_view(sublime.active_window())
    cmd = partial(
        thru_technical_command(root_view, persist.insert),
        path=action['path'], key=action['key'], value=action['value']
    )
    on_load(root_view, cmd)
