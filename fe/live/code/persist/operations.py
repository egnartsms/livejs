from copy import copy

from live.code.common import make_js_value_inserter
from .cursor import Cursor, ROOT_NESTING
from .saver import Saver


saver = Saver()


def replace_value(view, edit, path, new_value):
    cur = Cursor.at_value(path, view, edit)
    cur.push_region()
    cur.moveto_entry_end()
    cur.pop_erase()
    
    itr = make_js_value_inserter(cur, new_value, ROOT_NESTING + len(path))
    while next(itr, None):
        pass

    saver.request_save(view)


def rename_key(view, edit, path, new_name):
    cur = Cursor.at_key(path, view, edit)
    cur.push_region()
    cur.skip('[^:]+')
    cur.pop_erase()
    cur.insert(new_name)

    saver.request_save(view)


def delete(view, edit, path):
    cur = Cursor.at_entry(path, view, edit)
    
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

    saver.request_save(view)


def insert(view, edit, path, key, value):
    nesting = ROOT_NESTING + len(path)
    
    def insert_at(cur):
        if key is not None:
            cur.insert(key)
            cur.sep_keyval(nesting)
        for _ in make_js_value_inserter(cur, value, nesting):
            pass

    cur, found = Cursor.at_entry_or_end(path, view, edit)
    if (key is not None) != cur.is_inside_object:
        raise RuntimeError("Object/array insert mismatch")

    if not found:
        # It's gonna be either a single element or the last element
        prec = copy(cur)
        prec.skip_sep_bwd()
        if prec.prec_char in '[{':
            # The single element
            cur.erase(prec.pos)
            cur.sep_initial(nesting)
            insert_at(cur)
            cur.sep_terminal(nesting)
        else:
            # The last element
            prec.sep_inter(nesting)
            insert_at(prec)
    else:
        # What's before cur does not matter. Just insert the new node and then sep_inter()
        insert_at(cur)
        cur.sep_inter(nesting)

    saver.request_save(view)