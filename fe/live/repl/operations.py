import sublime


import collections
import json

from live.util import first_such
from .nodes import Node


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


BE_RESPONSE_STR = '''
{
    "type": "object",
    "id": 102,
    "value": {
        "__proto__": {
            "type": "object",
            "id": 1
        },
        "name": {
            "type": "leaf",
            "value": "\\"John\\""
        },
        "age": {
            "type": "leaf",
            "value": "30"
        },
        "isMale": {
            "type": "leaf",
            "value": "true"
        },
        "howToFind": {
            "type": "leaf",
            "value": "/ab(?=c)/"
        },
        "stringRepr": {
            "type": "function",
            "value": "function ({mid, path, codeNewValue}) {\\n            let \\n               {parent, key} = $.parentKeyAt($.modulesRoot(mid), path),\\n               newValue = $.evalExpr(codeNewValue);\\n         \\n            parent[key] = newValue;\\n         \\n            $.persist({\\n               type: 'replace',\\n               mid,\\n               path,\\n               newValue: $.prepareForSerialization(newValue)\\n            });\\n            $.respondSuccess();\\n         }"
        },
        "formerJobs": {
            "type": "array",
            "id": 103
        }
    }
}
'''

BE_RESPONSE = json.loads(BE_RESPONSE_STR, object_pairs_hook=collections.OrderedDict)


def insert_js_value(view, inserter):
    """Create Node instances which are inaccessible as of now.

    They exist only for the sake of phantoms
    """
    def insert_object():
        while True:
            cmd, args = next(inserter)
            if cmd == 'pop':
                Node(view, args.jsval, args.region)
                return

            insert_any(*next(inserter))

    def insert_array():
        while True:
            cmd, args = next(inserter)
            if cmd == 'pop':
                Node(view, args.jsval, args.region)
                return

            insert_any(cmd, args)

    def insert_any(cmd, args):
        if cmd == 'push_object':
            insert_object()
        elif cmd == 'push_array':
            insert_array()
        elif cmd == 'leaf':
            if args.jsval['type'] == 'function':
                Node(view, args.jsval, args.region)
        else:
            assert 0, "Inserter yielded unexpected command: {}".format(cmd)

    insert_any(*next(inserter))
