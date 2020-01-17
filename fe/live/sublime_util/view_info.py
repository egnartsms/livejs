import sublime_plugin


__all__ = ['ViewInfoDiscarder']


# Information we associate with views.  Keep in mind that it's not persisted.
# On Sublime re-start, none of these data structures will be in memory but the
# views will be re-created.
#
# [{view_id: <info instance>}]
view_planes = []


class ViewInfoDiscarder(sublime_plugin.EventListener):
    def on_close(self, view):
        for plane in view_planes:
            plane.pop(view.id(), None)


def defaultable_view_info_getter(info_cls):
    plane = {}
    view_planes.append(plane)

    def get(view):
        vid = view.id()
        if vid not in plane:
            plane[vid] = info_cls(view)

        return plane[vid]

    return get


class ViewInfoPlane:
    def __init__(self):
        self._plane = {}
        view_planes.append(self._plane)
