"""When we need to perform some operation on a Sublime buffer (view), we have to run a
(text) command.  This is the only way to get an Edit object necessary for modifications.
This module contains what is called the Technical command, which is what it sounds: just a
meaningless command that jumps into whatever callback you substitute for it, and passes
the View and Edit object as keywords"""
import sublime_plugin


__all__ = ['LivejsTechnicalCommand']


technical_command_callback = None


def run_technical_command(view, callback):
    global technical_command_callback

    technical_command_callback = callback
    try:
        view.run_command('livejs_technical')
    finally:
        technical_command_callback = None


class LivejsTechnicalCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        technical_command_callback(view=self.view, edit=edit)
