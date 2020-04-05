from live.browser.module_browser import ModuleBrowser
from live.common.misc import first_or_none
from live.settings import setting
from live.sublime.view_info import view_info_getter


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


def module_browser_view_for_module_id(window, module_id):
    return first_or_none(
        view
        for view in window.views()
        if is_view_module_browser(view) and setting.module_id[view] == module_id
    )


module_browser_for = view_info_getter(ModuleBrowser, is_view_module_browser)
