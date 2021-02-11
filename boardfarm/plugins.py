"""module: boardfarm.plugins."""

import inspect
import pkgutil
from importlib import import_module, util

import pluggy

from .exceptions import CodeError


def find_plugins():
    """Return a dictionary of all boardfarm plugins."""
    return {
        name: import_module(name)
        for _finder, name, _ispkg in pkgutil.iter_modules()
        if name.startswith("boardfarm_")
    }


def walk_library(module, filter_pkgs=None):
    """Return a list of all sub modules present inside input module.

    :param module: Module to scan for sub modules
    :type module: module
    :param filter_pkgs: ignore listed packages while scanning, defaults to None
    :type filter_pkgs: list(str), optional
    :return: list of scanned sub modules
    :rtype: list(module)
    """
    module_list = []
    if filter_pkgs is None:
        filter_pkgs = []

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


class BFPluginManager(pluggy.PluginManager):
    """Derived implementation of PluginManager for boardfarm."""

    _pm_instances = {}

    def __new__(cls, name="boardfarm", implprefix=None, *args, **kwargs):
        """Ensure returning single instances of Plugin Manger for each name."""
        if name not in cls._pm_instances:
            cls._pm_instances[name] = object.__new__(cls, *args, **kwargs)
        return cls._pm_instances[name]

    @classmethod
    def remove_plugin_manager(cls, name):
        """Use it to remove feature plugin managers only."""
        if name == "boardfarm":
            raise CodeError("Cannot remove boardfarm plugin manager")
        cls._pm_instances.pop(name, None)

    def __init__(self, project_name="boardfarm", implprefix=None):
        """Initialize a pluggy PluginManager for boardfarm plugins."""
        super().__init__(project_name, implprefix)

    def _inspect_classes(self, module, **filter_keys):
        return [
            obj
            for _, obj in inspect.getmembers(module)
            if inspect.isclass(obj)
            and all(getattr(obj, k, "") == v for k, v in filter_keys.items())
        ]

    def fetch_impl_classes(self, filter="base"):
        result = {}
        for name in ["boardfarm"] + list(find_plugins().keys()):
            # then register hook implementation classes as plugins
            try:
                mod_impl = util.find_spec(f"{name}.lib.hooks")
            except ModuleNotFoundError:
                continue
            if mod_impl:
                spec_impls = walk_library(mod_impl.loader.load_module())
                for mod in spec_impls:
                    for impl in self._inspect_classes(mod, impl_type=filter):
                        result[f"{name}.{impl.__name__}"] = impl()
        return result

    def load_hook_specs(self, filter="base"):
        """Load all static hooks from each Boardfarm Plugin."""
        for name in ["boardfarm"] + list(find_plugins().keys()):
            # first load the base hook specs
            try:
                mod_spec = util.find_spec(f"{name}.lib.specs")
            except ModuleNotFoundError:
                continue
            if mod_spec:
                spec_mods = walk_library(mod_spec.loader.load_module())
                for mod in spec_mods:
                    for spec in self._inspect_classes(mod, spec_type=filter):
                        self.add_hookspecs(spec)

    def load_all_impl_classes(self, filter="base"):
        """Load all hook implementations in one-shot.

        Useful in case of base hook implementations
        """
        for _, impl in self.fetch_impl_classes(filter).items():
            self.register(impl)
