import json
import sublime

from live.shared.backend import interacts_with_backend
from live.shared.cursor import Cursor
from live.shared.js_cursor import StructuredCursor
from live.sublime.edit import edit_for
from live.sublime.edit import edits_view
from live.sublime.misc import is_multiline_region
from live.ws_handler import GetterThrewError
from live.ws_handler import ws_handler


PHANTOM_HTML_TEMPLATE = '''
<body id="inspectee">
    <style>
     a {{
        display: block;
        text-decoration: none;
     }}
    </style>
    <div>{contents}</div>
</body>
'''


def add_inspectee_phantom(view, region, contents, on_navigate):
    return view.add_phantom(
        '', region, PHANTOM_HTML_TEMPLATE.format(contents=contents),
        sublime.LAYOUT_INLINE, on_navigate
    )


def _release_subtree(ihost, inspectee):
    desc_ids = list(inspectee.descendant_ids(include_self=False))
    if desc_ids:
        ws_handler.run_async_op('releaseInspecteeIds', {
            'spaceId': ihost.inspection_space_id,
            'inspecteeIds': desc_ids
        })
        yield


@interacts_with_backend(edits_view=lambda ihost: ihost.view)
def collapse_inspectee(ihost, inspectee):
    yield from _release_subtree(ihost, inspectee)

    ihost.replace_inspectee(inspectee, lambda: _collapse_inspectee(ihost, inspectee))


def _collapse_inspectee(ihost, inspectee):
    [reg] = ihost.view.query_phantom(inspectee.phantom_id)
    ihost.view.erase(edit_for[ihost.view], reg)

    cur = Cursor(reg.a, ihost.view)
    cur.push()
    cur.insert(jsval_placeholder(inspectee.type))
    region = cur.pop_region()
    collapsed = ihost.make_collapsed_inspectee(
        js_id=inspectee.id,
        depth=inspectee.depth,
        region=region
    )
    return collapsed, region


@interacts_with_backend(edits_view=lambda ihost: ihost.view)
def expand_inspectee(ihost, inspectee):
    ws_handler.run_async_op('reinspectObject', {
        'spaceId': ihost.inspection_space_id,
        'inspecteeId': inspectee.id
    })
    jsval = yield

    ihost.replace_inspectee(inspectee, lambda: _expand_inspectee(ihost, inspectee, jsval))


def _expand_inspectee(ihost, inspectee, jsval):
    [reg] = ihost.view.query_phantom(inspectee.phantom_id)
    ihost.view.erase(edit_for[ihost.view], reg)

    cur = StructuredCursor(reg.a, ihost.view, depth=inspectee.depth)
    cur.push()
    expanded = insert_js_value(ihost, cur, jsval)
    return expanded, cur.pop_region()


@edits_view(lambda ihost: ihost.view)
def collapse_function_inspectee(ihost, fn_inspectee):
    ihost.replace_inspectee(
        fn_inspectee, lambda: _collapse_function_inspectee(ihost, fn_inspectee)
    )


def _collapse_function_inspectee(ihost, fn_inspectee):
    [reg] = ihost.view.query_phantom(fn_inspectee.phantom_id)
    ihost.view.erase(edit_for[ihost.view], reg)

    cur = Cursor(reg.a, ihost.view)
    cur.push()
    cur.insert(jsval_placeholder('function'))
    region = cur.pop_region()
    new_inspectee = ihost.make_collapsed_function_inspectee(
        js_id=fn_inspectee.id,
        source=fn_inspectee.source,
        depth=fn_inspectee.depth,
        region=region
    )
    return new_inspectee, region


@edits_view(lambda ihost: ihost.view)
def expand_function_inspectee(ihost, fn_inspectee):
    ihost.replace_inspectee(
        fn_inspectee, lambda: _expand_function_inspectee(ihost, fn_inspectee)
    )


def _expand_function_inspectee(ihost, fn_inspectee):
    [reg] = ihost.view.query_phantom(fn_inspectee.phantom_id)
    ihost.view.erase(edit_for[ihost.view], reg)

    cur = StructuredCursor(reg.a, ihost.view, depth=fn_inspectee.depth)
    cur.push()
    cur.insert_function(fn_inspectee.source)
    region = cur.pop_region()
    new_inspectee = ihost.make_expanded_function_inspectee(
        js_id=fn_inspectee.id,
        source=fn_inspectee.source,
        depth=fn_inspectee.depth,
        region=region
    )
    return new_inspectee, region


@interacts_with_backend(edits_view=lambda ihost: ihost.view)
def expand_unrevealed_inspectee(ihost, unrevealed):
    error = jsval = None

    try:
        ws_handler.run_async_op('inspectGetterValue', {
            'spaceId': ihost.inspection_space_id,
            'parentId': unrevealed.parent_id,
            'prop': unrevealed.prop
        })
        jsval = yield
    except GetterThrewError as e:
        error = e

    ihost.replace_inspectee(
        unrevealed,
        lambda: _expand_unrevealed_inspectee(ihost, unrevealed, jsval, error)
    )


def _expand_unrevealed_inspectee(ihost, unrevealed, jsval, error):
    [region] = ihost.view.query_phantom(unrevealed.phantom_id)
    ihost.view.erase(edit_for[ihost.view], region)

    cur = StructuredCursor(region.a, ihost.view, depth=unrevealed.depth)
    cur.push()

    if jsval is not None:
        new_node = insert_js_value(ihost, cur, jsval)
    else:
        cur.insert("throw new {}({})".format(
            error.exc_class_name,
            json.dumps(error.exc_message)
        ))
        new_node = None

    return new_node, cur.pop_region()


def insert_js_value(ihost, cur, jsval):
    def insert_object(jsval):
        cur.push()

        if 'value' not in jsval:
            cur.insert(jsval_placeholder('object'))
            return ihost.make_collapsed_inspectee(
                js_id=jsval['id'],
                depth=cur.depth,
                region=cur.pop_region()
            )

        child_nodes = []
        with cur.laying_out('object') as separate:
            for key, value in jsval['value'].items():
                separate()
                cur.insert(key)
                cur.insert_keyval_sep()
                child_node = insert_any(value)
                if child_node is not None:
                    child_nodes.append(child_node)

        return ihost.make_expanded_inspectee(
            js_id=jsval['id'],
            js_type='object',
            child_nodes=child_nodes,
            depth=cur.depth,
            region=cur.pop_region()
        )

    def insert_array(jsval):
        cur.push()

        if 'value' not in jsval:
            cur.insert(jsval_placeholder('array'))
            return ihost.make_collapsed_inspectee(
                js_id=jsval['id'],
                depth=cur.depth,
                region=cur.pop_region()
            )

        child_nodes = []
        with cur.laying_out('array') as separate:
            for value in jsval['value']:
                separate()
                child_node = insert_any(value)
                if child_node is not None:
                    child_nodes.append(child_node)

        return ihost.make_expanded_inspectee(
            js_id=jsval['id'],
            js_type='array',
            child_nodes=child_nodes,
            depth=cur.depth,
            region=cur.pop_region()
        )

    def insert_function(jsval):
        cur.push()
        
        if '\n' in jsval['value']:
            cur.insert(jsval_placeholder('function'))
            fn = ihost.make_collapsed_function_inspectee
        else:
            cur.insert_function(jsval['value'])
            fn = ihost.make_expanded_function_inspectee

        return fn(
            js_id=jsval['id'],
            source=jsval['value'],
            depth=cur.depth,
            region=cur.pop_region()
        )

    def insert_unrevealed(jsval):
        cur.push()
        cur.insert(jsval_placeholder('unrevealed'))
        return ihost.make_unrevealed_inspectee(
            prop=jsval['prop'],
            depth=cur.depth,
            region=cur.pop_region()
        )

    def insert_any(jsval):
        if jsval['type'] == 'object':
            return insert_object(jsval)
        elif jsval['type'] == 'array':
            return insert_array(jsval)
        elif jsval['type'] == 'function':
            return insert_function(jsval)
        elif jsval['type'] == 'unrevealed':
            return insert_unrevealed(jsval)
        elif jsval['type'] == 'leaf':
            cur.insert(jsval['value'])
            return None
        else:
            raise RuntimeError("Unexpected jsval: {}".format(jsval))

    return insert_any(jsval)


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
        raise RuntimeError


class InspectionHostBase:
    @property
    def view(self):
        raise NotImplementedError

    @property
    def inspection_space_id(self):
        raise NotImplementedError

    def replace_inspectee(self, old_node, do):
        new_node, new_region = do()

        parent = old_node.parent_node
        if parent is None:
            return

        parent.child_nodes.remove(old_node)
        if new_node is not None:
            parent.child_nodes.add(new_node)

    def make_collapsed_inspectee(self, js_id, depth, region):
        return CollapsedInspectee(self, js_id, depth, region)

    def make_expanded_inspectee(self, js_id, js_type, child_nodes, depth, region):
        if is_multiline_region(region, self.view):
            return ExpandedInspectee(self, child_nodes, js_id, js_type, depth, region)
        else:
            return PhantomlessInspectee(self, child_nodes, js_id)

    def make_collapsed_function_inspectee(self, js_id, source, depth, region):
        return FuncCollapsedInspectee(self, js_id, source, depth, region)

    def make_expanded_function_inspectee(self, js_id, source, depth, region):
        if is_multiline_region(region, self.view):
            return FuncExpandedInspectee(self, js_id, source, depth, region)
        else:
            return PhantomlessInspectee(self, [], js_id)

    def make_unrevealed_inspectee(self, prop, depth, region):
        return UnrevealedInspectee(self, prop, depth, region)


class Inspectee:
    def __init__(self, ihost):
        self.ihost = ihost
        self.parent_node = None


class ChildfulInspectee(Inspectee):
    def __init__(self, ihost, child_nodes):
        super().__init__(ihost)
        self.child_nodes = set(child_nodes)
        for child in self.child_nodes:
            child.parent_node = self

    def descendant_ids(self, include_self):
        """Generate all the self.child_nodes' IDs and IDs of their descendants.

        Common for several inspectee implementation classes.
        """
        if include_self:
            yield self.id

        for child in self.child_nodes:
            yield from child.descendant_ids(include_self=True)


class ChildlessInspectee(Inspectee):
    def descendant_ids(self, include_self):
        if include_self:
            yield self.id


EXPANDED_PHANTOM_CONTENTS = '<a href="collapse/expand">\u2014</a>'
COLLAPSED_PHANTOM_CONTENTS = '<a href="collapse/expand">+</a>'


class PhantomlessInspectee(ChildfulInspectee):
    def __init__(self, ihost, child_nodes, js_id):
        super().__init__(ihost, child_nodes)
        self.id = js_id


class ExpandedInspectee(ChildfulInspectee):
    def __init__(self, ihost, child_nodes, js_id, js_type, depth, region):
        super().__init__(ihost, child_nodes)
        self.id = js_id
        self.type = js_type
        self.depth = depth
        self.phantom_id = add_inspectee_phantom(
            ihost.view, region, EXPANDED_PHANTOM_CONTENTS, self.on_navigate
        )

    def on_navigate(self, href):
        if href == 'collapse/expand':
            collapse_inspectee(self.ihost, self)


class CollapsedInspectee(ChildlessInspectee):
    def __init__(self, ihost, js_id, depth, region):
        super().__init__(ihost)
        self.id = js_id
        self.depth = depth
        self.phantom_id = add_inspectee_phantom(
            ihost.view, region, COLLAPSED_PHANTOM_CONTENTS, self.on_navigate
        )

    def on_navigate(self, href):
        if href == 'collapse/expand':
            expand_inspectee(self.ihost, self)


class FuncExpandedInspectee(ChildlessInspectee):
    def __init__(self, ihost, js_id, source, depth, region):
        super().__init__(ihost)
        self.id = js_id
        self.source = source
        self.depth = depth
        self.phantom_id = add_inspectee_phantom(
            ihost.view, region, EXPANDED_PHANTOM_CONTENTS, self.on_navigate
        )

    def on_navigate(self, href):
        if href == 'collapse/expand':
            collapse_function_inspectee(self.ihost, self)


class FuncCollapsedInspectee(ChildlessInspectee):
    def __init__(self, ihost, js_id, source, depth, region):
        super().__init__(ihost)
        self.id = js_id
        self.source = source
        self.depth = depth
        self.phantom_id = add_inspectee_phantom(
            ihost.view, region, COLLAPSED_PHANTOM_CONTENTS, self.on_navigate
        )

    def on_navigate(self, href):
        if href == 'collapse/expand':
            expand_function_inspectee(self.ihost, self)


class UnrevealedInspectee(ChildlessInspectee):
    def __init__(self, ihost, prop, depth, region):
        super().__init__(ihost)
        self.prop = prop
        self.depth = depth
        self.region = region
        self.phantom_id = add_inspectee_phantom(
            ihost.view, region, COLLAPSED_PHANTOM_CONTENTS, self.on_navigate
        )

    @property
    def parent_id(self):
        return self.parent_node.id

    def on_navigate(self, href):
        if href == 'collapse/expand':
            expand_unrevealed_inspectee(self.ihost, self)

    def descendant_ids(self, include_self):
        return ()
