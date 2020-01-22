from .settings import setting_module_id
from .settings import setting_view
from .module_browser import ModuleBrowser
from live.sublime_util.view_info import view_info_getter
from live.util import first_or_none


def is_view_module_browser(view):
    return setting_view[view] == 'Code Browser'


def module_browser_view_name(module):
    return "LiveJS: {}".format(module.name)


def find_module_browser_view(window, module):
    return first_or_none(
        view
        for view in window.views()
        if is_view_module_browser(view) and setting_module_id[view] == module.id
    )


def new_module_browser_view(window, module):
    view = window.new_file()
    setting_view[view] = 'Code Browser'
    setting_module_id[view] = module.id
    view.set_name(module_browser_view_name(module))
    view.set_scratch(True)
    view.set_read_only(True)
    view.assign_syntax('Packages/JavaScript/JavaScript.sublime-syntax')
    return view


module_browser_for = view_info_getter(ModuleBrowser, is_view_module_browser)
