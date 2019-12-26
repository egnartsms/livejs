import sublime
import sublime_plugin

import os
import json
import re
from functools import partial

from live.gstate import ws_handler


class AddModule(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if view.settings().get('syntax') !=\
                'Packages/JavaScript/JavaScript.sublime-syntax':
            sublime.error_message("Not a JavaScript file")
            return

        if not view.file_name():
            sublime.error_message("This view does not correspond to a real file on disk")
            return

        intuitive_module_name = os.path.splitext(os.path.basename(view.file_name()))[0]
        self.window.show_input_panel(
            'New module name:', intuitive_module_name,
            partial(self.on_module_name_entered, view), None, None
        )

    def on_module_name_entered(self, view, module_name):
        if not re.match(r'^[a-zA-Z0-9-]+$', module_name):
            self.window.status_message("Invalid module name (should be alphanums)")
            return

        js = '$.addModule({name}, {source}, {path})'.format(
            name=json.dumps(module_name),
            source=json.dumps(view.substr(sublime.Region(0, view.size()))),
            path=json.dumps(view.file_name())
        )

        def callback(response):
            self.window.status_message("Module {} added!".format(module_name))

        ws_handler.request(js, callback)
