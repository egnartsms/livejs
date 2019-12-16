import sublime

import re
import contextlib
from collections import OrderedDict

from live.util import tracking_last


def make_js_value_inserter(cur, jsval, nesting):
    """Return a generator that inserts JS values with given cursor and yields commands.
    
    :param nesting: nesting of jsval at point of insertion.

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
    def insert_any(jsval, nesting):
        if isinstance(jsval, list):
            yield from insert_array(jsval, nesting)
            return
        
        assert isinstance(jsval, OrderedDict), "Got non-dict: {}".format(jsval)
        leaf = jsval.get('__leaf_type__')
        if leaf == 'js-value':
            cur.insert(jsval['value'])
            yield 'leaf'
        elif leaf == 'function':
            insert_function(jsval['value'], nesting)
            yield 'leaf'
        else:
            assert leaf is None
            yield from insert_object(jsval, nesting)

    def insert_array(arr, nesting):
        yield 'push_array'
        if not arr:
            cur.insert("[]")
            yield 'pop'
            return

        cur.insert("[")
        cur.sep_initial(nesting + 1)
        for item, islast in tracking_last(arr):
            cur.push_region()
            yield from insert_any(item, nesting + 1)
            yield cur.pop_region()
            (cur.sep_terminal if islast else cur.sep_inter)(nesting + 1)
        cur.insert("]")

        yield 'pop'

    def insert_object(obj, nesting):
        yield 'push_object'

        if not obj:
            cur.insert("{}")
            yield 'pop'
            return

        cur.insert("{")
        cur.sep_initial(nesting + 1)
        for (k, v), islast in tracking_last(obj.items()):
            cur.push_region()
            cur.insert(k)
            yield cur.pop_region()

            cur.sep_keyval(nesting + 1)

            cur.push_region()
            yield from insert_any(v, nesting + 1)
            yield cur.pop_region()

            (cur.sep_terminal if islast else cur.sep_inter)(nesting + 1)
        cur.insert("}")

        yield 'pop'

    def insert_function(source, nesting):
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

    yield from insert_any(jsval, nesting)


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
