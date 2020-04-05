from .operations import module_browser_for


class ModuleBrowserCommandMixin:
    @property
    def mbrowser(self):
        return module_browser_for(self.view)
