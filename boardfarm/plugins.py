import importlib
import pkgutil


def find_plugins():
    '''
    Returns a dictionary of all boardfarm plugins.
    key = name of plugin (string)
    value = imported module
    '''
    result = {}
    for finder, name, ispkg in pkgutil.iter_modules():
        if name.startswith('boardfarm_'):
            result[name] = importlib.import_module(name)
    return result
