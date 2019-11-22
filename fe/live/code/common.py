import re
from collections import OrderedDict

from live.config import config
from live.util import tracking_last


def inserting_js_value(cur, jsval, nesting):
    def indent():
        cur.insert(config.s_indent * nesting)

    def insert_any(jsval):
        if isinstance(jsval, list):
            yield from insert_array(jsval)
            return
        
        assert isinstance(jsval, OrderedDict), "Got non-dict: {}".format(jsval)
        leaf = jsval.get('__leaf_type__')
        if leaf == 'js-value':
            cur.insert(jsval['value'])
            yield 'leaf'
        elif leaf == 'function':
            insert_function(jsval['value'])
            yield 'leaf'
        else:
            assert leaf is None
            yield from insert_object(jsval)

    def insert_array(arr):
        nonlocal nesting

        yield 'push_array'
        if not arr:
            cur.insert("[]")
            yield 'pop'
            return

        cur.insert("[\n")
        nesting += 1
        for item in arr:
            indent()
            x0 = cur.pos
            yield from insert_any(item)
            x1 = cur.pos
            yield (x0, x1)

            cur.insert(",\n")
        nesting -= 1
        indent()
        cur.insert("]")

        yield 'pop'

    def insert_object(obj):
        nonlocal nesting

        yield 'push_object'

        if not obj:
            cur.insert("{}")
            yield 'pop'
            return

        cur.insert("{\n")
        nesting += 1
        for k, v in obj.items():
            indent()
            x0 = cur.pos
            cur.insert(k)
            x1 = cur.pos
            yield (x0, x1)

            cur.insert(': ')
            x0 = cur.pos
            yield from insert_any(v)
            x1 = cur.pos
            yield (x0, x1)

            cur.insert(',\n')
        nesting -= 1
        indent()
        cur.insert("}")

        yield 'pop'

    def insert_function(source):
        # The last line of a function contains a single closing brace and is indented at
        # the same level as the whole function.  This of course depends on the formatting
        # style but it works for now and is very simple.
        i = source.rfind('\n')
        if i == -1:
            pass

        i += 1
        n = 0
        while i + n < len(source) and ord(source[i + n]) == 32:
            n += 1

        line0, *lines = source.splitlines()
        
        cur.insert(line0)
        if lines:
            cur.insert('\n')

        for line, islast in tracking_last(lines):
            indent()
            if not re.match(r'^\s*$', line):
                cur.insert(line[n:])
            if not islast:
                cur.insert('\n')

    yield from insert_any(jsval)
