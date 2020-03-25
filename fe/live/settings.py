from live.sublime.misc import Setting


class setting:
    view = Setting('livejs_view')
    """Type of LiveJS view this is.

    Possible values are:
      'Code Browser'
      'REPL'
    """
    
    project_id = Setting('livejs_project_id')
    """ID of the project with which a Sublime window is associated"""

    module_id = Setting('livejs_module_id')
    """ID of the module the module browser view is for"""

    cur_module_id = Setting('livejs_cur_module_id')
    """ID of the current module (REPL views)"""

    cur_module_name = Setting('livejs_cur_module_name')
    """Name of the current module (REPL views)"""

    inspection_space_id = Setting('livejs_inspection_space_id')
    """For REPLs, this is the REPL's unique inspection space identifier."""
