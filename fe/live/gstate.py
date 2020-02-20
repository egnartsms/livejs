from live.util.misc import Proxy


class Config:
    port = 8088
    indent = 3
    s_indent = ' ' * indent
    max_gui_freeze = 50e-3

    livejs_project_id = 'a559f0f3ff8744bb944f1dda48650b4f'

    # set at plugin load time
    be_root = None
    livejs_project = None


config = Config()

ws_handler = Proxy()

projects = []  # LiveJS is appended on plugin start
