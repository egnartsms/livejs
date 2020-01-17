from live.sublime_util.view_info import defaultable_view_info_getter


class ModuleBrowserInfo:
    def __init__(self, view):
        self.view = view
        self.root = None
        self.node_being_edited = None
        self.is_editing = False
        self.new_node_parent = None
        self.new_node_position = None

    @property
    def is_editing_new_node(self):
        return self.is_editing and self.node_being_edited is None

    def edit_node(self, node):
        self.is_editing = True
        self.node_being_edited = node

    def edit_new_node(self, parent, pos, region):
        self.is_editing = True
        self.new_node_parent = parent
        self.new_node_position = pos

    def done_editing(self):
        self.is_editing = False
        self.node_being_edited = None
        self.new_node_position = None
        self.new_node_parent = None


info_for = defaultable_view_info_getter(ModuleBrowserInfo)
