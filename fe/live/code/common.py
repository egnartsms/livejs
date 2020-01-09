import sublime

import re
import contextlib

from live.util import tracking_last, FreeObj


def make_js_value_inserter(cur, jsval, nesting):
    """Return a generator that inserts JS values with given cursor and yields commands.
    
    :param nesting: nesting of jsval at point of insertion.

    Yields the following commands:

      * 'push_object', None: starting to lay out a js object
      * 'push_array', None: starting to lay out a js array
      * 'pop', args: finished to lay out whatever the current thing was
                    (object or array)
      * 'leaf', args: just inserted a leaf value
    
    args is an object with attributes:
      * region
      * jsval
      * nesting
    """
    def insert_any(jsval, nesting):
        cur.push_region()

        if jsval['type'] == 'leaf':
            cur.insert(jsval['value'])
            yield 'leaf', FreeObj(region=cur.pop_region(), jsval=jsval, nesting=nesting)
        elif jsval['type'] == 'unrevealed':
            cur.insert(jsval_placeholder('unrevealed'))
            yield 'leaf', FreeObj(region=cur.pop_region(), jsval=jsval, nesting=nesting)
        elif jsval['type'] == 'function':
            insert_function(jsval['value'], nesting)
            yield 'leaf', FreeObj(region=cur.pop_region(), jsval=jsval, nesting=nesting)
        elif jsval['type'] == 'object':
            yield from insert_object(jsval, nesting)
            yield 'pop', FreeObj(region=cur.pop_region(), jsval=jsval, nesting=nesting)
        elif jsval['type'] == 'array':
            yield from insert_array(jsval, nesting)
            yield 'pop', FreeObj(region=cur.pop_region(), jsval=jsval, nesting=nesting)
        else:
            cur.pop_region()
            assert 0, "Unknown type: {}".format(jsval['type'])

    def insert_array(arr, nesting):
        yield 'push_array', None

        if 'value' not in arr:
            # This array is non-tracked, so value must be fetched separately
            cur.insert("[...]")
            return

        if not arr['value']:
            cur.insert("[]")
            return

        cur.insert("[")
        cur.sep_initial(nesting + 1)
        for item, islast in tracking_last(arr['value']):
            yield from insert_any(item, nesting + 1)
            (cur.sep_terminal if islast else cur.sep_inter)(nesting + 1)
        cur.insert("]")

    def insert_object(obj, nesting):
        yield 'push_object', None

        if 'value' not in obj:
            # This object is non-tracked, so value must be fetched separately
            cur.insert("{...}")
            return

        if not obj['value']:
            cur.insert("{}")
            return

        cur.insert("{")
        cur.sep_initial(nesting + 1)
        for (k, v), islast in tracking_last(obj['value'].items()):
            cur.push_region()
            cur.insert(k)
            yield 'leaf', FreeObj(region=cur.pop_region(), jsval=k)

            cur.sep_keyval(nesting + 1)

            yield from insert_any(v, nesting + 1)

            (cur.sep_terminal if islast else cur.sep_inter)(nesting + 1)
        cur.insert("}")

    def insert_function(source, nesting):
        # The last line of a function contains a single closing brace and is indented at
        # the same level as the whole function.  This of course depends on the formatting
        # style but it works for now and is very simple.
        i = source.rfind('\n') + 1
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

    yield from insert_any(jsval, nesting)


def jsval_placeholder(jsval_type):
    if jsval_type == 'object':
        return "{...}"
    elif jsval_type == 'array':
        return "[...]"
    elif jsval_type == 'function':
        return "func {...}"
    elif jsval_type == 'unrevealed':
        return "(...)"
    else:
        assert 0


@contextlib.contextmanager
def read_only_set_to(view, new_status):
    old_status = view.is_read_only()
    view.set_read_only(new_status)
    yield
    view.set_read_only(old_status)


def add_hidden_regions(view, key, regs):
    """Marker region is a hidden"""
    view.add_regions(key, regs, '', '', sublime.HIDDEN)


@contextlib.contextmanager
def hidden_region_list(view, key):
    region_list = view.get_regions(key)
    yield region_list
    add_hidden_regions(view, key, region_list)
