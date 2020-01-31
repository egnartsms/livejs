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


def view_info_getter(info_cls, is_applicable_to):
    plane = {}
    view_planes.append(plane)

    def get(view):
        if view.id() not in plane:
            if is_applicable_to(view):
                plane[view.id()] = info_cls(view)
            else:
                return None

        return plane[view.id()]

    return get
