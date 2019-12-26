from live.util import Proxy


class Config:
    be_root = None
    indent = 3
    s_indent = ' ' * indent
    live_module_filename = 'live.js'


config = Config()


def _get_ws_handler():
    from live.ws_handler import ws_handler
    return ws_handler


ws_handler = Proxy(_get_ws_handler)
