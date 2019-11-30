from copy import copy

import sublime

from live.code.common import make_js_value_inserter
from live.code.persist_cursor import PersistCursor, ROOT_NESTING


def replace_value(view, edit, path, new_value):
    cur = PersistCursor.at_value(path, view, edit)
    beg = cur.pos
    cur.moveto_entry_end()
    cur.erase(beg)
    
    itr = make_js_value_inserter(cur, new_value, ROOT_NESTING + len(path))
    while next(itr, None):
        pass

    # Just saving does not work, we have to do it after the current command completes
    sublime.set_timeout(lambda: view.run_command('save'), 0)


def rename_key(view, edit, path, new_name):
    cur = PersistCursor.at_key(path, view, edit)
    beg = cur.pos
    cur.skip('[^:]+')
    cur.erase(beg)
    cur.insert(new_name)

    # Just saving does not work, we have to do it after the current command completes
    sublime.set_timeout(lambda: view.run_command('save'), 0)


def delete(view, edit, path):
    cur = PersistCursor.at_entry(path, view, edit)
    
    prec = copy(cur)
    prec.skip_sep_bwd()

    folw = copy(cur)
    folw.moveto_next_entry_or_end()

    is_first = prec.prec_char in '[{'
    is_last = folw.char in ']}'

    if is_first and is_last:
        prec.erase(folw.pos)
    elif is_last:
        cur.moveto_entry_end()
        prec.erase(cur.pos)
    else:
        cur.erase(folw.pos)

    # Just saving does not work, we have to do it after the current command completes
    sublime.set_timeout(lambda: view.run_command('save'), 0)
