class Config:
    port = 8088
    indent = 3
    s_indent = ' ' * indent
    max_gui_freeze = 50e-3

    livejs_project_id = 'a559f0f3ff8744bb944f1dda48650b4f'
    project_file_name = 'project.live.json'

    # set at plugin load time
    be_root = None
    livejs_project = None


config = Config()

fe_projects = []  # LiveJS is appended on plugin start
