from live.util import first_such


def find_repl(window):
    return first_such(
        view for view in window.views()
        if view.settings().get('livejs_view') == 'REPL'
    )


def new_repl(window):
    repl = window.new_file()
    repl.settings().set('livejs_view', 'REPL')
    repl.set_name('LiveJS: REPL')
    repl.set_scratch(True)
    repl.assign_syntax('Packages/LiveJS/LiveJS REPL.sublime-syntax')
    return repl
