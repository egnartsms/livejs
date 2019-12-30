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
