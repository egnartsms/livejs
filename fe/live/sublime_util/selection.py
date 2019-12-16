def set_selection(view, to_reg=None, to_regs=None, show=False):
    if (to_reg is None) == (to_regs is None):
        raise RuntimeError

    view.sel().clear()
    if to_reg is not None:
        view.sel().add(to_reg)
    else:
        view.sel().add_all(to_regs)

    if show:
        view.show(view.sel(), True)
