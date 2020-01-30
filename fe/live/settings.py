from live.sublime_util.misc import ViewSetting


class setting:
    view = ViewSetting('livejs_view')
    """Type of LiveJS view this is.

    Possible values are:
      'Code Browser'
      'REPL'
    """
    
    module_id = ViewSetting('livejs_module_id')
    """ID of the module the module browser view is for"""

    cur_module_id = ViewSetting('livejs_cur_module_id')
    """ID of the current module (REPL views)"""
