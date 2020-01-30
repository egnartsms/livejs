import os

from live.util.misc import Proxy


class Config:
    be_root = None  # set at plugin load time
    indent = 3
    s_indent = ' ' * indent
    bootstrapping_module_id = 'acc0b54988854dd9b5e74d269ea731e1'  # also hardcoded in BE
    bootstrapping_module_name = 'live'  # hardcoded in BE => renaming disabled
    bootstrapping_module_filename = 'live.js'

    @property
    def bootstrapping_module_filepath(self):
        return os.path.join(self.be_root, self.bootstrapping_module_filename)


config = Config()


def _get_ws_handler():
    from live.ws_handler import ws_handler
    return ws_handler


ws_handler = Proxy(_get_ws_handler)

fe_modules = []
