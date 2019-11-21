import sublime


def set_viewport_position(view, pos, animate=True):
    """Set the viewport position.

    Keep trying to set it until the view.viewport_position() returns what we try to set
    """
    def set_():
        view.set_viewport_position(pos, animate)
        sublime.set_timeout(check_, 0)

    def check_():
        vp = view.viewport_position()
        if vp != pos:
            sublime.set_timeout(set_, 0)

    sublime.set_timeout(set_, 0)
