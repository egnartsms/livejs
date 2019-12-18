import sublime

import time


INTERVAL = 3000


class Saver:
    """Save all the files with JS source code that need to be persisted after changes.

    Current policy is the following:
       save if no saving requests were issued for a set time interval.
    """

    def __init__(self):
        self.views = []
        self.most_recent_request_moment = None
        # self.requested = False

    def request_save(self, view):
        if not any(vw == view for vw in self.views):
            self.views.append(view)
        if self.most_recent_request_moment is None:
            sublime.set_timeout(self._save, INTERVAL)
        self.most_recent_request_moment = time.perf_counter()

    def _save(self):
        elapsed = (time.perf_counter() - self.most_recent_request_moment) * 1000.0
        if elapsed < INTERVAL:
            sublime.set_timeout(self._save, INTERVAL)
        else:
            for view in self.views:
                view.run_command('save')
            del self.views[:]
            self.most_recent_request_moment = None
