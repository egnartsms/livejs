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

    def insert_leaf(jsval):
        cur.push()
        cur.insert(jsval['value'])
        return ihost.make_leaf_inspectee(depth=cur.depth, region=cur.pop_region())

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
            return insert_leaf(jsval)
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


def replace_inspectee(ihost, old_node, do):
    def wrap_do():
        new_node, new_region = do()

        assert new_node.parent_node is None

        parent = old_node.parent_node
        if parent is not None:
            parent.child_nodes.remove(old_node)
            old_node.parent_node = None
            parent.child_nodes.add(new_node)
            new_node.parent_node = parent

        return new_node, new_region

    ihost.replace_inspectee(old_node, wrap_do)


def release_subtree(ihost, node, include_self=False):
    desc_ids = list(descendant_ids(node, include_self))
    if desc_ids:
        ws_handler.run_async_op('releaseInspecteeIds', {
            'spaceId': ihost.inspection_space_id,
            'inspecteeIds': desc_ids
        })
        yield


def descendant_ids(node, include_self):
    if include_self and hasattr(node, 'id'):
        yield node.id

    child_nodes = getattr(node, 'child_nodes', ())
    for node in child_nodes:
        yield from descendant_ids(node, include_self=True)


EXPANDED_PHANTOM_CONTENTS = '<a href="collapse/expand">\u2014</a>'
COLLAPSED_PHANTOM_CONTENTS = '<a href="collapse/expand">+</a>'


class Inspectee:
    def __init__(self, ihost, region):
        self.ihost = ihost
        self.parent_node = None

        contents = self._get_phantom_contents(region)
        if contents:
            self.phantom_id = add_inspectee_phantom(
                ihost.view, region, contents, self.on_navigate
            )

    def on_navigate(self, href):
        raise NotImplementedError

    def _get_phantom_contents(self, region):
        return ''


class LeafInspectee(Inspectee):
    def __init__(self, ihost, depth, region):
        super().__init__(ihost, region)


class ExpandedInspectee(Inspectee):
    def __init__(self, ihost, js_id, js_type, child_nodes, depth, region):
        super().__init__(ihost, region)

        self.id = js_id
        self.type = js_type
        self.depth = depth

        self.child_nodes = set(child_nodes)
        for child in self.child_nodes:
            child.parent_node = self

    def _get_phantom_contents(self, region):
        if is_multiline_region(region,  self.ihost.view):
            return EXPANDED_PHANTOM_CONTENTS
        else:
            return ''

    @interacts_with_backend(edits_view=lambda self: self.ihost.view)
    def on_navigate(self, href):
        yield from self._on_navigate(href)

    def _on_navigate(self, href):
        yield from release_subtree(self.ihost, self)
        replace_inspectee(self.ihost, self, self._collapse)

    def _collapse(self):
        [reg] = self.ihost.view.query_phantom(self.phantom_id)
        self.ihost.view.erase(edit_for[self.ihost.view], reg)

        cur = Cursor(reg.a, self.ihost.view)
        cur.push()
        cur.insert(jsval_placeholder(self.type))
        region = cur.pop_region()
        collapsed = self.ihost.make_collapsed_inspectee(
            js_id=self.id, depth=self.depth, region=region
        )
        return collapsed, region


class CollapsedInspectee(Inspectee):
    def __init__(self, ihost, js_id, depth, region):
        super().__init__(ihost, region)
        self.id = js_id
        self.depth = depth

    def _get_phantom_contents(self, region):
        return COLLAPSED_PHANTOM_CONTENTS

    @interacts_with_backend(edits_view=lambda self: self.ihost.view)
    def on_navigate(self, href):
        yield from self._on_navigate(href)

    def _on_navigate(self, href):
        ws_handler.run_async_op('reinspectObject', {
            'spaceId': self.ihost.inspection_space_id,
            'inspecteeId': self.id
        })
        jsval = yield
        replace_inspectee(self.ihost, self, lambda: self._expand(jsval))

    def _expand(self, jsval):
        [reg] = self.ihost.view.query_phantom(self.phantom_id)
        self.ihost.view.erase(edit_for[self.ihost.view], reg)

        cur = StructuredCursor(reg.a, self.ihost.view, depth=self.depth)
        cur.push()
        expanded = insert_js_value(self.ihost, cur, jsval)
        return expanded, cur.pop_region()


class FuncExpandedInspectee(Inspectee):
    def __init__(self, ihost, js_id, source, depth, region):
        super().__init__(ihost, region)
        self.id = js_id
        self.source = source
        self.depth = depth

    def _get_phantom_contents(self, region):
        if is_multiline_region(region,  self.ihost.view):
            return EXPANDED_PHANTOM_CONTENTS
        else:
            return ''

    @edits_view(lambda self: self.ihost.view)
    def on_navigate(self, href):
        self._on_navigate(href)

    def _on_navigate(self, href):
        replace_inspectee(self.ihost, self, self._collapse)

    def _collapse(self):
        [reg] = self.ihost.view.query_phantom(self.phantom_id)
        self.ihost.view.erase(edit_for[self.ihost.view], reg)

        cur = Cursor(reg.a, self.ihost.view)
        cur.push()
        cur.insert(jsval_placeholder('function'))
        region = cur.pop_region()
        new_inspectee = self.ihost.make_collapsed_function_inspectee(
            js_id=self.id,
            source=self.source,
            depth=self.depth,
            region=region
        )
        return new_inspectee, region


class FuncCollapsedInspectee(Inspectee):
    def __init__(self, ihost, js_id, source, depth, region):
        super().__init__(ihost, region)
        self.id = js_id
        self.source = source
        self.depth = depth

    def _get_phantom_contents(self, region):
        return COLLAPSED_PHANTOM_CONTENTS

    @edits_view(lambda self: self.ihost.view)
    def on_navigate(self, href):
        return self._on_navigate(href)

    def _on_navigate(self, href):
        replace_inspectee(self.ihost, self, self._expand)

    def _expand(self):
        [reg] = self.ihost.view.query_phantom(self.phantom_id)
        self.ihost.view.erase(edit_for[self.ihost.view], reg)

        cur = StructuredCursor(reg.a, self.ihost.view, depth=self.depth)
        cur.push()
        cur.insert_function(self.source)
        region = cur.pop_region()
        new_inspectee = self.ihost.make_expanded_function_inspectee(
            js_id=self.id,
            source=self.source,
            depth=self.depth,
            region=region
        )
        return new_inspectee, region


class UnrevealedInspectee(Inspectee):
    def __init__(self, ihost, prop, depth, region):
        super().__init__(ihost, region)
        self.prop = prop
        self.depth = depth
        self.region = region

    def _get_phantom_contents(self, region):
        return COLLAPSED_PHANTOM_CONTENTS

    @interacts_with_backend(edits_view=lambda self: self.ihost.view)
    def on_navigate(self, href):
        yield from self._on_navigate(href)

    def _on_navigate(self, href):
        error = jsval = None

        try:
            ws_handler.run_async_op('inspectGetterValue', {
                'spaceId': self.ihost.inspection_space_id,
                'parentId': self.parent_node.id,
                'prop': self.prop
            })
            jsval = yield
        except GetterThrewError as e:
            error = e

        replace_inspectee(self.ihost, self, lambda: self._expand(jsval, error))

    def _expand(self, jsval, error):
        [region] = self.ihost.view.query_phantom(self.phantom_id)
        self.ihost.view.erase(edit_for[self.ihost.view], region)

        cur = StructuredCursor(region.a, self.ihost.view, depth=self.depth)
        cur.push()

        if jsval is not None:
            new_inspectee = insert_js_value(self.ihost, cur, jsval)
        else:
            cur.insert("throw new {}({})".format(
                error.exc_class_name,
                json.dumps(error.exc_message)
            ))
            new_inspectee = None

        return new_inspectee, cur.pop_region()


class InspectionHostBase:
    def make_leaf_inspectee(self, depth, region):
        return LeafInspectee(self, depth, region)

    def make_collapsed_inspectee(self, js_id, depth, region):
        return CollapsedInspectee(self, js_id, depth, region)
    
    def make_expanded_inspectee(self, js_id, js_type, child_nodes, depth, region):
        return ExpandedInspectee(self, js_id, js_type, child_nodes, depth, region)

    def make_collapsed_function_inspectee(self, js_id, source, depth, region):
        return FuncCollapsedInspectee(self, js_id, source, depth, region)

    def make_expanded_function_inspectee(self, js_id, source, depth, region):
        return FuncExpandedInspectee(self, js_id, source, depth, region)

    def make_unrevealed_inspectee(self, prop, depth, region):
        return UnrevealedInspectee(self, prop, depth, region)

    @property
    def view(self):
        raise NotImplementedError

    @property
    def inspection_space_id(self):
        raise NotImplementedError

    def replace_inspectee(self, old_node, do):
        do()
