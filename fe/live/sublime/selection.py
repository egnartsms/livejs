import contextlib
import sublime

from live.sublime.misc import is_point_inside


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
def viewport_position_preserved(view, animate=False):
    vp = view.viewport_position()
    yield
    set_viewport_position(view, vp, animate=animate)


@contextlib.contextmanager
def selection_rowcol_preserved_on_replace(view, replaced_region):
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


@contextlib.contextmanager
def selection_rowcol_globally_preserved(view):
    old_rowcols = [(view.rowcol(r.a), view.rowcol(r.b)) for r in view.sel()]
    yield
    new_selection = [
        sublime.Region(view.text_point(*a_rowcol), view.text_point(*b_rowcol))
        for a_rowcol, b_rowcol in old_rowcols
    ]
    set_selection(view, to_all=new_selection)


@contextlib.contextmanager
def viewport_and_selection_globally_preserved(view):
    with viewport_position_preserved(view), selection_rowcol_globally_preserved(view):
        yield
