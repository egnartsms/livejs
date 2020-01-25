from .module_browser import ModuleBrowser
from live.settings import setting
from live.sublime_util.view_info import view_info_getter
from live.util.misc import first_or_none


def is_view_module_browser(view):
    return setting.view[view] == 'Code Browser'


def module_browser_view_name(module):
    return "LiveJS: {}".format(module.name)


def new_module_browser_view(window, module):
    view = window.new_file()
    setting.view[view] = 'Code Browser'
    setting.module_id[view] = module.id
    view.set_name(module_browser_view_name(module))
    view.set_scratch(True)
    view.set_read_only(True)
    view.assign_syntax('Packages/JavaScript/JavaScript.sublime-syntax')

    return view


def find_module_browser_view(window, module):
    return first_or_none(
        view
        for view in window.views()
        if is_view_module_browser(view) and setting.module_id[view] == module.id
    )


module_browser_for = view_info_getter(ModuleBrowser, is_view_module_browser)
