import os
from threading import Thread

import sublime
import sublime_plugin

from .live.server import LiveJsHttpServer, RequestHandler


g_srv = None
g_thread = None


def server_entry_point():
    g_srv.serve_forever()


class ToggleServerCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        global g_srv, g_thread

        if g_srv is None:
            print("Starting the server...")
            g_srv = LiveJsHttpServer(('127.0.0.1', 8000), RequestHandler)
            g_thread = Thread(target=server_entry_point)
            g_thread.start()
            print("Done")
        else:
            print("Stopping the server...")
            g_srv.shutdown()
            g_srv = None
            g_thread = None
            print("Done")
