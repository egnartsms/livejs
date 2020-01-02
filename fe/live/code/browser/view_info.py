import sublime
import sublime_plugin


__all__ = ['PerViewInfoDiscarder']


# Information we associate with codebrowser views.  Keep in mind that it's not persisted.
# On Sublime re-start, none of these data structures will be in memory, but the code
# browser views will be persisted.
per_view = dict()


class ViewInfo:
    view = None
    root = None
    node_being_edited = None
    is_editing = False
    new_node_parent = None
    new_node_position = None
    # How many characters before and after the editing region: (size_pre, size_post)
    edit_pre_post = None
    # How far the enclosing edit region extends from the edit region, to the left and
    # to the right.
    enclosing_edit_offsets = None

    def __init__(self, view):
        self.view = view

    def _pre_post_sizes(self, reg):
        return reg.a, self.view.size() - reg.b

    @property
    def is_editing_new_node(self):
        return self.is_editing and self.node_being_edited is None

    def edit_node(self, node):
        self.is_editing = True
        self.node_being_edited = node
        self.edit_pre_post = self._pre_post_sizes(node.region)
        self.enclosing_edit_offsets = (0, 0)

    def edit_new_node(self, parent, pos, region, enclosing_region):
        self.is_editing = True
        self.new_node_parent = parent
        self.new_node_position = pos
        self.edit_pre_post = self._pre_post_sizes(region)
        self.enclosing_edit_offsets = (
            region.a - enclosing_region.a,
            enclosing_region.b - region.b
        )

    def done_editing(self):
        self.is_editing = False
        self.node_being_edited = None
        self.new_node_position = None
        self.new_node_parent = None
        self.edit_pre_post = None
        self.enclosing_edit_offsets = None

    def enclosing_edit_reg(self, reg):
        return sublime.Region(reg.a - self.enclosing_edit_offsets[0],
                              reg.b + self.enclosing_edit_offsets[1])


def info_for(view):
    vid = view.id()
    if vid not in per_view:
        per_view[vid] = ViewInfo(view)

    return per_view[vid]


class PerViewInfoDiscarder(sublime_plugin.EventListener):
    def on_close(self, view):
        per_view.pop(view.id(), None)
