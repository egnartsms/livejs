"""Editing JSON and JavaScript files in Sublime views"""

import json

from live.shared.js_cursor import StructuredCursor


def json_root_in(view):
    return Entity(view, [])


class Entity:
    def __init__(self, view, path):
        self.view = view
        self.path = path

    def __getitem__(self, key):
        return Entity(self.view, self.path + [key])

    def append(self, item):
        cur = StructuredCursor(0, self.view, inside_what='array')

        for key in self.path:
            cur.enter()
            cur.goto_entry_keyed_by(json.dumps(key))

        cur.prepare_for_insertion_at_end()
        dump_py_as_json(cur, item)


def dump_py_as_json(cur, obj):
    def insert(obj):
        if isinstance(obj, dict):
            with cur.laying_out('object') as separate:
                for k, v in obj.items():
                    separate()
                    cur.insert(json.dumps(k))
                    cur.insert_keyval_sep()
                    insert(v)
        elif isinstance(obj, list):
            with cur.laying_out('array') as separate:
                for v in obj:
                    separate()
                    insert(v)
        elif isinstance(obj, (str, int, bool)):
            cur.insert(json.dumps(obj))
        else:
            raise RuntimeError("Unsupported object for insertion in JSON: {}".format(obj))

    insert(obj)
