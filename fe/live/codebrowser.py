import re
from collections import OrderedDict

import sublime_plugin
import sublime

from live.config import config
from live.util import tracking_last


class JsNode(list):
    is_leaf = False
    
    def __init__(self, is_object, mypath):
        super().__init__()
        self.is_object = is_object
        self.mypath = mypath

    @property
    def key_reg_keys(self):
        assert self.is_object
        return self.mypath + '.keys'
    
    @property
    def key_reg_values(self):
        assert self.is_object
        return self.mypath + '.values'

    @property
    def key_reg_items(self):
        assert not self.is_object
        return self.mypath + '.items'

    def human_readable(self):
        if self.is_object:
            return '{' + ','.join([x.human_readable() for x in self]) + '}'
        else:
            return '[' + ','.join([x.human_readable() for x in self]) + ']'

    def __repr__(self):
        return '#<jsnode: {}>'.format(self.human_readable())


class JsLeaf:
    is_leaf = True

    def __init__(self, mypath):
        self.mypath = mypath

    def human_readable(self):
        return 'x'

    def __repr__(self):
        return '#<jsleaf>'


per_view = dict()


class ViewInfo:
    root = None

    def __init__(self):
        pass


def info_for(view):
    vid = view.id()
    if vid not in per_view:
        per_view[vid] = ViewInfo()

    return per_view[vid]


class PerViewInfoDiscarder(sublime_plugin.EventListener):
    def on_close(self, view):
        print("view on_close()!")
        vid = view.id()
        if vid in per_view:
            del per_view[vid]


def path_join(path, n):
    if path:
        return '{}.{}'.format(path, n)
    else:
        return str(n)


def reset(view, edit, resp):
    root = info_for(view).root
    if root is not None:
        erase_regions(view, root)

    view.erase(edit, sublime.Region(0, view.size()))
    root = JsNode(is_object=True, mypath='')
    reg_keys, reg_values = [], []
    
    for i, (key, value) in enumerate(resp):
        x0 = view.size()
        view.insert(edit, view.size(), key)
        x1 = view.size()
        reg_keys.append(sublime.Region(x0, x1))

        view.insert(edit, view.size(), ' =\n')

        x0 = view.size()
        jsnode = insert_js_unit(view, edit, value, str(i))
        x1 = view.size()
        reg_values.append(sublime.Region(x0, x1))
        root.append(jsnode)
        
        view.insert(edit, view.size(), '\n\n')

    view.add_regions(root.key_reg_keys, reg_keys, '', '', sublime.HIDDEN)
    view.add_regions(root.key_reg_values, reg_values, '', '', sublime.HIDDEN)

    info_for(view).root = root

    view.set_read_only(True)
    view.window().focus_view(view)


def insert_js_unit(view, edit, obj, path):
    nesting = 0

    def insert(s):
        view.insert(edit, view.size(), s)

    def indent():
        insert(config.s_indent * nesting)

    def insert_unit(obj, path):
        if isinstance(obj, list):
            return insert_array(obj, path)
        
        assert isinstance(obj, OrderedDict), "Got non-dict: {}".format(obj)
        leaf = obj.get('__leaf_type__')
        if leaf == 'js-value':
            insert(obj['value'])
            return JsLeaf(path)
        elif leaf == 'function':
            insert_function(obj['value'])
            return JsLeaf(path)
        else:
            assert leaf is None
            return insert_object(obj, path)

    def insert_array(arr, path):
        nonlocal nesting

        reg_items, jsnode = [], JsNode(is_object=False, mypath=path)

        if not arr:
            insert("[]")
            return jsnode

        insert("[\n")
        nesting += 1
        for i, item in enumerate(arr):
            indent()
            x0 = view.size()
            subnode = insert_unit(item, path_join(path, i))
            x1 = view.size()
            reg_items.append(sublime.Region(x0, x1))
            jsnode.append(subnode)

            insert(",\n")
        nesting -= 1
        indent()
        insert("]")

        view.add_regions(jsnode.key_reg_items, reg_items, '', '', sublime.HIDDEN)

        return jsnode

    def insert_object(obj, path):
        nonlocal nesting

        reg_keys, reg_values, jsnode = [], [], JsNode(is_object=True, mypath=path)

        if not obj:
            insert("{}")
            return jsnode

        insert("{\n")
        nesting += 1
        for i, (k, v) in enumerate(obj.items()):
            indent()
            x0 = view.size()
            insert(k)
            x1 = view.size()
            reg_keys.append(sublime.Region(x0, x1))

            insert(': ')
            x0 = view.size()
            subnode = insert_unit(v, path_join(path, i))
            x1 = view.size()
            reg_values.append(sublime.Region(x0, x1))
            jsnode.append(subnode)

            insert(',\n')
        nesting -= 1
        indent()
        insert("}")

        view.add_regions(jsnode.key_reg_keys, reg_keys, '', '', sublime.HIDDEN)
        view.add_regions(jsnode.key_reg_values, reg_values, '', '', sublime.HIDDEN)

        return jsnode

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
        
        insert(line0)
        insert('\n')
        for line, islast in tracking_last(lines):
            indent()
            if not re.match(r'^\s*$', line):
                insert(line[n:])
            if not islast:
                insert('\n')

    return insert_unit(obj, path)


def erase_regions(view, jsnode):
    def erase(node):
        if node.is_leaf:
            return

        for subnode in node:
            erase(subnode)

        if node.is_object:
            view.erase_regions(node.key_reg_keys)
            view.erase_regions(node.key_reg_values)
        else:
            view.erase_regions(node.key_reg_items)

    erase(jsnode)


def find_innermost_region(view, x):
    obj = info_for(view).root
    reg = None

    while not obj.is_leaf:
        if obj.is_object:
            print(obj.key_reg_values)
            regs = view.get_regions(obj.key_reg_values)
        else:
            print(obj.key_reg_values)
            regs = view.get_regions(obj.key_reg_items)

        print("regs:", regs, "obj", obj)

        assert len(regs) == len(obj)

        for subreg, subobj in zip(regs, obj):
            if subreg.contains(x):
                obj = subobj
                reg = subreg
                break
        else:
            raise Exception("Not inside a leaf object")

    return obj, reg
