"""module: boardfarm.plugins."""
import importlib
import pkgutil
from importlib import import_module


def find_plugins():
    """
    Return a dictionary of all boardfarm plugins.

    key = name of plugin (string)
    value = imported module
    """
    result = {}
    for finder, name, ispkg in pkgutil.iter_modules():
        if name.startswith("boardfarm_"):
            result[name] = importlib.import_module(name)
    return result


def walk_library(module, filter_pkgs=[]):
    module_list = []

    def _walk_library(module):
        for info in pkgutil.walk_packages(module.__path__):
            if all(i not in info.name for i in filter_pkgs):
                mod = import_module(".".join([module.__name__, info.name]))
                if info.ispkg:
                    _walk_library(mod)
                else:
                    module_list.append(mod)

    _walk_library(module)
    return module_list
