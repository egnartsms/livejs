import contextlib
import sublime

from live.code.cursor import Cursor
from live.shared.backend import interacts_with_backend
from live.settings import setting
from live.sublime.edit import edit_for
from live.sublime.edit import edits_self_view
from live.sublime.misc import add_hidden_regions
from live.sublime.misc import read_only_set_to
from live.sublime.region_edit import RegionEditHelper
from live.sublime.selection import set_selection
from live.ws_handler import ws_handler


class Repl:
    EDIT_REGION_KEY = 'edit'

    def __init__(self, view):
        self.view = view
        self.reh = None
        # When user moves back and forth between his inputs
        self.n_inputs_back = -1
        self.pending_last_input = ''

    @property
    def cur_module_id(self):
        return setting.cur_module_id[self.view]

    @property
    def cur_module_name(self):
        return setting.cur_module_name[self.view]

    def set_current_module(self, module):
        setting.cur_module_id[self.view] = module.id
        setting.cur_module_name[self.view] = module.name

    @property
    def inspection_space_id(self):
        return setting.inspection_space_id[self.view]

    @inspection_space_id.setter
    def inspection_space_id(self, value):
        setting.inspection_space_id[self.view] = value

    @property
    def is_ready(self):
        return self.reh is not None

    @property
    def cur_prompt(self):
        return self.cur_module_name + '> '

    @property
    def edit_region(self):
        [reg] = self.view.get_regions(self.EDIT_REGION_KEY)
        return reg

    @edit_region.setter
    def edit_region(self, reg):
        add_hidden_regions(self.view, self.EDIT_REGION_KEY, [reg])

    @property
    def is_selection_within_edit_region(self):
        return self.reh is not None and self.reh.is_selection_within

    def replace_edit_region_contents(self, s):
        ereg = self.edit_region
        with read_only_set_to(self.view, False):
            self.view.replace(edit_for[self.view], ereg, s)
        self.edit_region = sublime.Region(ereg.a, ereg.a + len(s))

    def _set_reh(self):
        self.reh = RegionEditHelper(
            self.view,
            edit_region_getter=lambda: self.edit_region,
            edit_region_setter=lambda reg: setattr(self, 'edit_region', reg)
        )
        self.reh.set_read_only()

    def insert_prompt(self, cur):
        cur.insert(self.cur_prompt)
        self.edit_region = sublime.Region(cur.pos)
        self._set_reh()
        self.n_inputs_back = -1
        self.pending_last_input = ''

    def reinsert_prompt(self):
        user_io = UserInputOutputInfo(self.view)
        with self.region_editing_off_then_reestablished():
            self.view.replace(edit_for[self.view], user_io.prompt_regs[-1],
                              self.cur_prompt)

    @edits_self_view
    def erase_all_insert_prompt(self):
        cur = Cursor(0, self.view)
        cur.erase(self.view.size())
        self.insert_prompt(cur)

    def prepare_for_activation(self):
        """Prepare a pre-existing REPL view to continue functioning"""
        if self.is_ready:
            return

        user_io = UserInputOutputInfo(self.view)
        self.edit_region = user_io.input_reg(-1)
        self._set_reh()

    def ensure_modifications_within_edit_region(self):
        """Undo any modifications outside edit region"""
        if self.reh is not None:
            self.reh.undo_modifications_outside_edit_region()

    def set_view_read_only(self):
        """Set the REPL view's read_only status depending on current selection"""
        if self.reh is not None:
            self.reh.set_read_only()

    @contextlib.contextmanager
    def region_editing_off_then_reestablished(self):
        self.reh = None
        self.view.set_read_only(False)
        try:
            yield
        finally:
            self._set_reh()

    @edits_self_view
    def to_prev_prompt(self):
        user_io = UserInputOutputInfo(self.view)

        if -self.n_inputs_back == user_io.num_of_inputs:
            return False  # already at oldest user input

        if self.n_inputs_back == -1:
            self.pending_last_input = self.view.substr(self.edit_region)

        self.n_inputs_back -= 1
        user_input = self.view.substr(user_io.input_reg(self.n_inputs_back)).strip()
        self.replace_edit_region_contents(user_input)
        set_selection(self.view, to=self.edit_region.b, show=True)

        return True

    @edits_self_view
    def to_next_prompt(self):
        user_io = UserInputOutputInfo(self.view)

        if self.n_inputs_back == -1:
            return False  # already at newest user input

        self.n_inputs_back += 1
        if self.n_inputs_back == -1:
            user_input = self.pending_last_input
            self.pending_last_input = ''
        else:
            user_input = self.view.substr(user_io.input_reg(self.n_inputs_back)).strip()

        self.replace_edit_region_contents(user_input)
        set_selection(self.view, to=self.edit_region.b, show=True)

        return True

    @interacts_with_backend()
    def delete_inspection_space(self):
        ws_handler.run_async_op('deleteInspectionSpace', {
            'spaceId': self.inspection_space_id
        })
        yield


class UserInputOutputInfo:
    """Helper class that knows where are prompt regions and result regions in a REPL"""

    def __init__(self, view):
        prompt_regs = view.find_by_selector('punctuation.separator.livejs-repl.prompt')
        result_regs = view.find_by_selector('punctuation.separator.livejs-repl.result')
        if len(prompt_regs) != len(result_regs) + 1:
            sublime.error_message("REPL view is broken (number of prompts and results do "
                                  "not match.")
            raise RuntimeError

        self.prompt_regs = prompt_regs
        self.result_regs = result_regs
        self.view_size = view.size()

    @property
    def num_of_inputs(self):
        return len(self.prompt_regs)

    def input_reg(self, n_inputs_back):
        idx = len(self.prompt_regs) + n_inputs_back
        if n_inputs_back == -1:
            return sublime.Region(self.prompt_regs[idx].b, self.view_size)
        else:
            return sublime.Region(self.prompt_regs[idx].b, self.result_regs[idx].a)
