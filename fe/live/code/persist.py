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


def insert(view, edit, path, key, value):
    parent_nesting = ROOT_NESTING + len(path) - 1
    
    def insert_at(cur):
        if key is not None:
            cur.insert(key)
            cur.insert(': ')
        for _ in make_js_value_inserter(cur, value, parent_nesting + 1):
            pass

    cur, found = PersistCursor.at_entry_or_end(path, view, edit)
    if (key is not None) != cur.is_inside_object:
        raise RuntimeError("Object/array insert mismatch")

    if not found:
        # It's gonna be either a single element or the last element
        prec = copy(cur)
        prec.skip_sep_bwd()
        if prec.prec_char in '[{':
            # The single element
            cur.erase(prec.pos)
            cur.sep_initial(parent_nesting)
            insert_at(cur)
            cur.sep_terminal(parent_nesting)
        else:
            # The last element
            prec.sep_inter(parent_nesting)
            insert_at(prec)
    else:
        # What's before cur does not matter. Just insert the new node and then sep_inter()
        insert_at(cur)
        cur.sep_inter(parent_nesting)

    # Just saving does not work, we have to do it after the current command completes
    sublime.set_timeout(lambda: view.run_command('save'), 0)
