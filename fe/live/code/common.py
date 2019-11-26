import sublime

import re
from collections import OrderedDict

from live.util import tracking_last


def make_js_value_inserter(cur, jsval, nesting):
    """Return a generator that inserts JS values with given cursor and yields commands.
    
    Yields the following commands:
      'leaf': just inserted a leaf js value
      'push_object': just started to lay out a js object
      'push_array': just started to lay out a js array
      'pop': finished to lay out whatever the current thing was (object or array)
      sublime.Region(beg, end): Sublime region that the most recent object occupies (see
                                example below).

    The object {a: 1, b: [20, 30]} would lead to following commands generated:

    push_object
    <(a, b) of 'a'>
    leaf
    <(a, b) of '1'>
    <(a, b) of 'b'>
    push_array
    leaf
    <(a, b) of 20>
    leaf
    <(a, b) of 30>
    pop
    <(a, b) of [20, 30]>
    pop
    """
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
            cur.indent(nesting)
            x0 = cur.pos
            yield from insert_any(item)
            x1 = cur.pos
            yield sublime.Region(x0, x1)

            cur.insert(",\n")
        nesting -= 1
        cur.indent(nesting)
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
            cur.indent(nesting)
            x0 = cur.pos
            cur.insert(k)
            x1 = cur.pos
            yield sublime.Region(x0, x1)

            cur.insert(': ')
            x0 = cur.pos
            yield from insert_any(v)
            x1 = cur.pos
            yield sublime.Region(x0, x1)

            cur.insert(',\n')
        nesting -= 1
        cur.indent(nesting)
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
            cur.indent(nesting)
            if not re.match(r'^\s*$', line):
                cur.insert(line[n:])
            if not islast:
                cur.insert('\n')

    yield from insert_any(jsval)
