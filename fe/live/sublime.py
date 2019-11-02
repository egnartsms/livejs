import os
import traceback

try:
    import sublime
    import sublime_plugin

    g_insublime = True
except ImportError:
    g_insublime = False


from live.http_server import serve
from live.eventloop import EventLoop


g_el = EventLoop()


@g_el.coroutine_exc_handler
def coroutine_exc_handler(itr, exc):
    print("Coroutine {} failed:".format(itr))
    traceback.print_exception(type(exc), exc, exc.__traceback__)


@g_el.eventloop_msg_handler
def eventloop_msg_handler(msg):
    print("Eventloop says:", msg)


def is_server_running():
    return g_el.is_coroutine_running('server')


def start_server():
    global g_el

    be_root = os.path.realpath(os.path.join(__file__, '../../../be'))
    print("BE root:", be_root)

    if not is_server_running():
        print("Starting the server...")
        g_el.add_coroutine(serve(8001, be_root), 'server')
        print("Started")


def stop_server():
    global g_el

    if is_server_running():
        print("Stopping the server...")
        g_el.force_quit_all_coroutines()
        print("Stopped")


def plugin_loaded():
    global g_el
    print("Loading LiveJS...")
    assert not g_el.is_running
    g_el.run_in_new_thread()
    start_server()
    print("Loaded")


def plugin_unloaded():
    global g_el
    print("Unloading LiveJS...")
    stop_server()
    g_el.stop(stop_all_coroutines=True)
    print("Unloaded")


if g_insublime:
    class ToggleServerCommand(sublime_plugin.TextCommand):
        def run(self, edit):
            global g_co, g_el
            if is_server_running():
                stop_server()
            else:
                start_server()

            # if g_srv is None:
            #     start_server()
            # else:
            #     stop_server()
            # if 'server' in g_el.named_coroutines:
            #     stop_server()
            # else:
            #     start_server()


    class InsertItCommand(sublime_plugin.TextCommand):
        def run(self, edit, text):
            def do():
                import time; time.sleep(5.0)
            sublime.set_timeout_async(do, 0)
            self.view.insert(edit, self.view.size(), text + '!en')
