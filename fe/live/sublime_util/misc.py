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


def is_point_inside(point, reg, strict=False):
    if strict:
        return point > reg.a and point < reg.b
    else:
        return point >= reg.a and point <= reg.b


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
