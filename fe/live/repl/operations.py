import json
import sublime

from .repl import Repl
from live.common.misc import first_or_none
from live.common.misc import gen_uid
from live.settings import setting
from live.shared.backend import interacts_with_backend
from live.shared.cursor import Cursor
from live.shared.js_cursor import StructuredCursor
from live.sublime.edit import edit_for
from live.sublime.edit import edits_self_view
from live.sublime.view_info import view_info_getter
from live.ws_handler import GetterThrewError
from live.ws_handler import ws_handler


def is_view_repl(view):
    return setting.view[view] == 'REPL'


def find_repl_view(window):
    return first_or_none(view for view in window.views() if is_view_repl(view))


def new_repl_view(window, module):
    view = window.new_file()
    setting.view[view] = 'REPL'
    view.set_name('LiveJS: REPL')
    view.set_scratch(True)
    view.assign_syntax('Packages/LiveJS/syntax/repl/JavaScript.sublime-syntax')

    repl = repl_for(view)
    repl.set_current_module(module)
    repl.inspection_space_id = gen_uid()
    
    repl.erase_all_insert_prompt()

    return view


repl_for = view_info_getter(Repl, is_view_repl)


# class Unrevealed:
#     """Unrevealed is used for getters (actual value is obtained lazily)

#     Unrevealed instance is always collapsed. When expanded it's substituted with smth
#     else, and the Unrevealed instance is gone forever.
#     """

#     def __init__(self, view, parent_id, prop, depth, region):
#         self.view = view
#         self.parent_id = parent_id
#         self.prop = prop
#         self.depth = depth
#         self.phid = add_phantom(self.view, region, self.on_navigate, False)

#     @property
#     def repl(self):
#         return repl_for(self.view)

#     @interacts_with_backend(edits_view=lambda self: self.view)
#     def on_navigate(self, href):
#         """Abandon this node and insert a new expanded one"""
#         error = jsval = None

#         try:
#             ws_handler.run_async_op('inspectGetterValue', {
#                 'spaceId': self.repl.inspection_space_id,
#                 'parentId': self.parent_id,
#                 'prop': self.prop
#             })
#             jsval = yield
#         except GetterThrewError as e:
#             error = e

#         [reg] = self.view.query_phantom(self.phid)
#         self.view.erase_phantom_by_id(self.phid)
#         self.phid = None
        
#         with self.repl.region_editing_off_then_reestablished():
#             self.view.erase(edit_for[self.view], reg)
#             cur = StructuredCursor(reg.a, self.view, depth=self.depth)
#             if jsval is not None:
#                 insert_js_value(cur, jsval)
#             else:
#                 cur.insert("throw new {}({})".format(
#                     error.exc_class_name,
#                     json.dumps(error.exc_message)
#                 ))
