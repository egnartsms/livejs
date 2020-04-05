from live.common.misc import first_or_none
from live.common.misc import gen_uid
from live.repl.repl import Repl
from live.settings import setting
from live.sublime.view_info import view_info_getter


def is_view_repl(view):
    return setting.view[view] == 'REPL'


def find_repl_view(window):
    return first_or_none(view for view in window.views() if is_view_repl(view))


def new_repl_view(window, module):
    view = window.new_file()
    setting.view[view] = 'REPL'
    view.set_name('LiveJS: REPL')
    view.set_scratch(True)
    view.assign_syntax('Packages/LiveJS/syntax/repl/JavaScript.sublime-syntax')

    repl = repl_for(view)
    repl.set_current_module(module)
    repl.inspection_space_id = gen_uid()
    
    repl.erase_all_insert_prompt()

    return view


repl_for = view_info_getter(Repl, is_view_repl)
