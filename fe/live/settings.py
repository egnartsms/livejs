from live.sublime_util.misc import ViewSetting


class setting:
    view = ViewSetting('livejs_view')
    """Type of LiveJS view this is.

    Possible values are:
      'Code Browser'
      'REPL'
    """
    
    module_id = ViewSetting('livejs_module_id')
    """ID of the module this view is related to:
        * for module browser views, this is the respective module's ID
        * for REPL views, this is the ID of the current module
    """

    module_name = ViewSetting('livejs_module_name')
    """For REPL views, this is the name of the current module

    It's not enough to have module ID only, because Module objects are volatile, and
    a REPL may need to operate in a disconnected/dissynchronized state yet it should
    preserve the module name for the prompt.
    """
