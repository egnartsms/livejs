import json
import os.path
import sublime

from live.gstate import config
from live.gstate import fe_projects
from live.settings import setting
from live.util.misc import first_or_none


def assign_window_for_livejs_project():
    for window in sublime.windows():
        if setting.project_id[window] == config.livejs_project_id:
            return

    setting.project_id[sublime.active_window()] = config.livejs_project_id


def window_for_project_id(project_id):
    return first_or_none(
        wnd for wnd in sublime.windows() if setting.project_id[wnd] == project_id
    )


def project_for_window(window):
    project_id = setting.project_id[window]
    if not project_id:
        return None

    return project_by_id(project_id)


def validate_window_project_loaded(window):
    if not project_for_window(window):
        sublime.status_message("This window is not associated with any LiveJS project")
        return False

    return True


def project_by_id(project_id):
    return first_or_none(p for p in fe_projects if p.id == project_id)


def read_project_file_at(root):
    with open(os.path.join(root, config.project_file_name), 'r') as fobj:
        return json.load(fobj)
