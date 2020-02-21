import os
import re
import sublime

from .datastructures import Project
from live.comm import interacts_with_be
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


@interacts_with_be()
def on_be_connected():
    assign_window_for_livejs_project()

    be_projects = yield 'getProjects', {}

    if len(be_projects) == 1:
        # BE has no loaded projects besides livejs itself
        if len(fe_projects) == 1:
            # FE has no projects either
            pass
        else:
            # FE --> BE
            yield from fe_to_be()
    else:
        # BE has loaded projects. In this case no matter what we have here on the FE side,
        # we should substitute it with the BE data.
        be_to_fe(be_projects)


def fe_to_be():
    for proj in fe_projects:
        if proj.id == config.livejs_project_id:
            continue

        project_id = yield 'loadProject', {
            'name': proj.name,
            'path': proj.path,
            'modulesData': get_project_modules_contents(proj.path)
        }
        if project_id != proj.id:
            sublime.error_message(
                "Failed to load project {}: ID mismatch".format(proj.name)
            )
            raise RuntimeError


def be_to_fe(be_projects):
    del fe_projects[:]

    for proj_data in be_projects:
        fe_projects.append(
            Project(
                id=proj_data['id'],
                name=proj_data['name'],
                path=proj_data['path']
            )
        )
