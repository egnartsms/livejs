import sublime_plugin


__all__ = ['OnLoadListener']


registry = {}  # {view.id(): <callback>}


def on_load(view, do):
    if not view.is_loading():
        do()
    else:
        registry[view.id()] = do


class OnLoadListener(sublime_plugin.EventListener):
    def on_load(self, view):
        callback = registry.pop(view.id(), None)
        if callback is not None:
            callback()

    def on_close(self, view):
        """If the view closes before it's loaded, cancel the callback.
        
        Necessity for such a trick was not shown by practice, we rather want to have this
        for the peace of mind.
        """
        registry.pop(view.id(), None)