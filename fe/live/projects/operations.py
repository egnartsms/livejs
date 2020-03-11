import glob
import os
import re
import sublime

from live.gstate import config
from live.gstate import fe_projects
from live.settings import setting
from live.util.misc import file_contents
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


def get_project_modules_contents(root):
    """Return all .js files in a given project root folder

    :return: [{'name', 'src'}]
    """
    res = []

    for fname in os.listdir(root):
        mo = re.match(r'(\w+)\.js$', fname)
        if mo:
            res.append({
                'name': mo.group(1),
                'src': file_contents(os.path.join(root, mo.group()))
            })

    return res


def get_project_file_path(folder):
    return glob.glob(os.path.join(folder, '*.live.js'))
