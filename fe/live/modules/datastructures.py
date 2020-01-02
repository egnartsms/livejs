from live.gstate import fe_modules, config
from live.util import first_such, eraise


_module_id_counter = 1


def gen_new_module_id():
    global _module_id_counter

    _module_id_counter += 1
    return _module_id_counter


def set_module_counter(val):
    global _module_id_counter
    _module_id_counter = val


class Module:
    __slots__ = ('id', 'name', 'path')

    def __init__(self, **attrs):
        for k, v in attrs.items():
            setattr(self, k, v)
        if 'id' not in attrs:
            self.id = gen_new_module_id()

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
        module = first_such(m for m in fe_modules if m.id == mid)
        if module is None:
            eraise("Not found a module with ID: {}", mid)

        return module
