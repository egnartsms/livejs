"""When we need to perform some operation on a Sublime buffer (view), we have to run a
(text) command.  This is the only way to get an Edit object necessary for modifications.
This module contains what is called the Technical command, which is what it sounds: just a
meaningless command that jumps into whatever callback you substitute for it, and passes
the View and Edit object as keywords"""

from functools import partial

import sublime_plugin


__all__ = ['LivejsTechnicalCommand']


technical_command_callback = None


def thru_technical_command(view, final_callback):
    def callback(*args, **kwargs):
        global technical_command_callback
        technical_command_callback = partial(final_callback, *args, **kwargs)
        try:
            view.run_command('livejs_technical')
        finally:
            technical_command_callback = None

    return callback


class LivejsTechnicalCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        technical_command_callback(view=self.view, edit=edit)
