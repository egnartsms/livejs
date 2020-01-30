import uuid

from live.gstate import fe_modules, config
from live.util.misc import first_or_none


class Module:
    def __init__(self, id, name, path):
        self.id = id or uuid.uuid4().hex
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
        return first_or_none(m for m in fe_modules if m.id == mid)

    @staticmethod
    def with_name(name):
        return first_or_none(m for m in fe_modules if m.name == name)
