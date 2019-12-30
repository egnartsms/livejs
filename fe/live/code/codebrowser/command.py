import sublime_plugin


class ModuleBrowserCommand(sublime_plugin.TextCommand):
    @property
    def mid(self):
        return self.view.settings().get('livejs_module_id')

    def set_status_be_pending(self):
        self.view.set_status('livejs_pending', "LiveJS: back-end is processing..")
