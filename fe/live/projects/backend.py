import sublime

from live.gstate import config
from live.gstate import fe_projects
from live.projects.datastructures import Project
from live.projects.operations import assign_window_for_livejs_project
from live.shared.backend import interacts_with_backend
from live.ws_handler import ws_handler


@ws_handler.on_connected()
@interacts_with_backend()
def on_backend_connected():
    assign_window_for_livejs_project()

    ws_handler.run_async_op('getProjects', {})
    be_projects = yield

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

        proj_data = proj.read_project_data()
        ws_handler.run_async_op('loadProject', {
            'projectPath': proj.path,
            'project': proj_data,
            'sources': {
                module['id']: proj.module_contents(module['name'])
                for module in proj_data['modules']
            }
        })
        yield


def be_to_fe(be_projects):
    fe_projects[:] = [
        Project(
            id=proj_data['id'],
            name=proj_data['name'],
            path=proj_data['path']
        )
        for proj_data in be_projects
    ]
