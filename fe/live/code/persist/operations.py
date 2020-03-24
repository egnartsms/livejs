from copy import copy

from live.code.persist.saver import Saver
from live.shared.js_cursor import StructuredCursor
from live.sublime.edit import edits_view_arg


saver = Saver()


def insert_js_value(cur, jsval):
    def insert_object(obj):
        with cur.laying_out('object') as separate:
            for key, value in obj.items():
                separate()
                cur.insert(key)
                cur.insert_keyval_sep()
                insert_any(value)

    def insert_array(arr):
        with cur.laying_out('array') as separate:
            for value in arr:
                separate()
                insert_any(value)

    def insert_any(jsval):
        if jsval['type'] == 'leaf':
            cur.insert(jsval['value'])
        elif jsval['type'] == 'function':
            cur.insert_function(jsval['value'])
        elif jsval['type'] == 'object':
            insert_object(jsval['value'])
        elif jsval['type'] == 'array':
            insert_array(jsval['value'])
        else:
            raise RuntimeError("Unexpected jsval: {}".format(jsval))

    insert_any(jsval)


@edits_view_arg
def replace_value(view, path, new_value):
    cur = StructuredCursor.at_module_path(view, path)
    cur.erase_value()
    insert_js_value(cur, new_value)

    saver.request_save(view)


@edits_view_arg
def rename_key(view, path, new_name):
    cur = StructuredCursor.at_module_path(view, path)
    cur.erase_object_key()
    cur.insert(new_name)

    saver.request_save(view)


@edits_view_arg
def delete(view, path):
    cur = StructuredCursor.at_module_path(view, path)
    cur.delete_entry()

    saver.request_save(view)


@edits_view_arg
def insert(view, path, key, value):
    parent_path, n = path[:-1], path[-1]

    cur = StructuredCursor.at_module_path(view, parent_path)
    cur.prepare_for_insertion_at(n)

    if key is not None:
        cur.insert(key)
        cur.insert_keyval_sep()

    insert_js_value(cur, value)

    saver.request_save(view)
