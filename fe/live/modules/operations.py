import sublime

from live.gstate import fe_modules, config
from live.comm import communicates_with_be
from .datastructures import Module


@communicates_with_be
def synch_modules_with_be():
    be_modules = yield 'sendModules', {}

    if len(be_modules) == 1:
        # BE has no loaded modules (the bootstrapping one is not counted)
        [mdl] = be_modules
        if mdl['name'] != config.live_module_name or mdl['path'] is not None:
            sublime.error_message("BE's modules are corrupted, consider refreshing")
            return

        if len(fe_modules) <= 1:
            # FE has no modules, either
            reset_fe_modules()
        else:
            # BE has no modules but FE does have modules: FE -> BE
            yield from load_fe_modules_into_be()
    else:
        # BE has modules. In this case no matter what we have here on the FE side,
        # we should substitute it with the BE data.
        fe_modules[:] = [
            Module(name=be_m['name'], path=be_m['path'])
            for be_m in be_modules
        ]


def load_modules(modules):
    yield 'loadModules', {
        'modules': [
            {
                'name': m.name,
                'path': m.path,
                'source': file_contents(m.path)
            }
            for m in modules
        ]
    }
    fe_modules.extend(modules)


def file_contents(filepath):
    with open(filepath, 'r') as fl:
        return fl.read()


def reset_fe_modules():
    """Reset FE modules to the single bootstrapping module"""
    fe_modules[:] = [
        Module(name=config.live_module_name,
               path=config.live_module_filepath)
    ]


def load_fe_modules_into_be():
    modules = [m for m in fe_modules if m.name != config.live_module_name]
    reset_fe_modules()
    yield from load_modules(modules)
