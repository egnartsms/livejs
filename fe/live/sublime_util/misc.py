import contextlib
import sublime


def set_selection(view, to=None, to_all=None, show=False):
    assert (to is None) != (to_all is None)

    view.sel().clear()
    if to_all is not None:
        view.sel().add_all(to_all)
    else:
        view.sel().add(to)

    if show:
        view.show(view.sel(), True)


def set_viewport_position(view, pos, animate=True):
    """Set the viewport position.

    Keep trying to set it until the view.viewport_position() returns what we try to set
    """
    def set_():
        view.set_viewport_position(pos, animate=animate)
        sublime.set_timeout(check_, 0)

    def check_():
        vp = view.viewport_position()
        if vp != pos:
            sublime.set_timeout(set_, 0)

    sublime.set_timeout(set_, 0)


@contextlib.contextmanager
def viewport_position_preserved(view):
    old = view.viewport_position()
    yield
    set_viewport_position(view, old, animate=False)


def is_point_inside(point, reg, strict=False):
    if strict:
        return point > reg.begin() and point < reg.end()
    else:
        return point >= reg.begin() and point <= reg.end()


def is_subregion(sub, sup, strict=False):
    return is_point_inside(sub.a, sup, strict) and is_point_inside(sub.b, sup, strict)


def _get_settings(vs):
    if isinstance(vs, sublime.View):
        return vs.settings()
    elif isinstance(vs, sublime.Settings):
        return vs
    else:
        assert False


class ViewSetting:
    def __init__(self, name):
        self.name = name

    def __getitem__(self, vs):
        return _get_settings(vs).get(self.name)

    def __setitem__(self, vs, value):
        _get_settings(vs).set(self.name, value)


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


@contextlib.contextmanager
def cursors_rowcol_preserved_on_replace(view, replaced_region):
    """Preserve (row, col) positions of sel() cursors after replacing a region"""
    if not any(r.intersects(replaced_region) for r in view.sel()):
        yield
        return

    old_rowcols = []
    for r in view.sel():
        if is_point_inside(r.a, replaced_region, strict=True):
            a = view.rowcol(r.a)
        else:
            a = None

        if is_point_inside(r.b, replaced_region, strict=True):
            b = view.rowcol(r.b)
        else:
            b = None

        old_rowcols.append((a, b))

    old_sel_len = len(view.sel())
    old_size = view.size()

    yield

    assert len(view.sel()) == old_sel_len, "Number of cursors changed"

    new_end = replaced_region.end() + view.size() - old_size
    new_selection = []
    
    for reg, (a_rowcol, b_rowcol) in zip(view.sel(), old_rowcols):
        if a_rowcol is None:
            a = reg.a
        else:
            a = min(new_end, view.text_point(*a_rowcol))
        
        if b_rowcol is None:
            b = reg.b
        else:
            b = min(new_end, view.text_point(*b_rowcol))

        new_selection.append(sublime.Region(a, b))

    set_selection(view, to_all=new_selection)
