import os.path
from functools import partial

import sublime


from live.config import config
from live.util import first_such
from live import server
from live.code import persist, codebrowser
from live.sublime_util.technical_command import thru_technical_command
from live.sublime_util.on_view_loaded import on_load


@server.action_handler('edit')
def edit(action):
    cbv = first_such(view for view in sublime.active_window().views()
                     if view.settings().get('livejs_view') == 'Code Browser')
    
    thru_technical_command(cbv, codebrowser.replace_node)(
        path=action['path'],
        new_value=action['newValue']
    )

    filename = os.path.join(config.be_root, config.root_module)
    root_view = cbv.window().find_open_file(filename)
    if root_view is None:
        focused_view = cbv.window().active_view()
        root_view = cbv.window().open_file(filename)
        cbv.window().focus_view(focused_view)

    tech = partial(thru_technical_command(root_view, persist.handle_edit_action),
                   path=action['path'], new_value=action['newValue'])
    on_load(root_view, tech)
