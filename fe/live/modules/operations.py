from .datastructures import Module
from live.comm import interacts_with_be
from live.gstate import config
from live.gstate import fe_modules


@interacts_with_be()
def synch_modules_with_be():
    be_modules = yield 'sendModules', {}

    if len(be_modules) == 1:
        # BE has no loaded modules (the bootstrapping one is not counted)
        if len(fe_modules) <= 1:
            # FE has no modules, either
            reset_fe_modules()
        else:
            # BE has no modules but FE does have modules: FE -> BE
            yield from load_fe_modules_into_be()
    else:
        # BE has modules. In this case no matter what we have here on the FE side,
        # we should substitute it with the BE data.
        set_fe_modules(be_modules)


def load_modules_request(modules):
    return 'loadModules', {
        'modules': [
            {
                'id': m.id,
                'name': m.name,
                'path': m.path,
                'source': file_contents(m.path)
            }
            for m in modules
        ]
    }


def file_contents(filepath):
    with open(filepath, 'r') as fl:
        return fl.read()


def reset_fe_modules():
    """Reset FE modules to the single bootstrapping module"""
    fe_modules[:] = [Module.bootstrapping()]


def set_fe_modules(be_modules):
    """Set FE modules to whatever we received from BE"""
    reset_fe_modules()
    fe_modules.extend(
        Module(id=be_m['id'], name=be_m['name'], path=be_m['path'])
        for be_m in be_modules
        if be_m['id'] != config.bootstrapping_module_id
    )


def load_fe_modules_into_be():
    modules = [m for m in fe_modules if not m.is_bootstrapping]
    yield load_modules_request(modules)
