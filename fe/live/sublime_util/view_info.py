import sublime_plugin


__all__ = ['ViewInfoDiscarder']


# Information we associate with views.  Keep in mind that it's not persisted.
# On Sublime re-start, none of these data structures will be in memory but the
# views will be re-created.
#
# {plane_id: {view_id: DATA}}
view_planes = dict()


def make_view_info_getter(info_cls):
    plane_id = object()
    view_planes[plane_id] = {}

    def info_for(view):
        plane = view_planes[plane_id]
        vid = view.id()
        if vid not in plane:
            plane[vid] = info_cls(view)

        return plane[vid]

    return info_for


class ViewInfoDiscarder(sublime_plugin.EventListener):
    def on_close(self, view):
        for plane in view_planes:
            plane.pop(view.id(), None)
