from live.gstate import fe_modules, config
from live.util import first_or_none


_module_id_counter = 1


def gen_new_module_id():
    global _module_id_counter

    _module_id_counter += 1
    return _module_id_counter


def set_module_counter(val):
    global _module_id_counter
    _module_id_counter = val


class Module:
    def __init__(self, id, name, path):
        self.id = gen_new_module_id() if id is None else id
        self.name = name
        self.path = path

    @classmethod
    def bootstrapping(cls):
        return cls(
            id=config.bootstrapping_module_id,
            name=config.bootstrapping_module_name,
            path=config.bootstrapping_module_filepath
        )

    @property
    def is_bootstrapping(self):
        return self.id == config.bootstrapping_module_id

    @staticmethod
    def with_id(mid):
        module = first_or_none(m for m in fe_modules if m.id == mid)
        assert module is not None, "Not found a module with ID: {}".format(mid)
        return module
