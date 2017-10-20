"""Load a plugin module by name.
"""
import sys
import importlib
try:
    # Python 3.6+
    from importlib import ModuleNotFoundError
except ImportError:
    ModuleNotFoundError = ImportError
from apikit import BackendError


def load_plugin(plugin_name):
    """Load a named plugin.  Substitute "-" with "_" first.  If the module
    is already loaded, return it; if not, load it and then return the
    loaded module.
    """
    project_type = "." + plugin_name.lower().replace("-", "_")
    module_path = ".".join(__name__.split(".")[:-1]) + ".projecttypes"
    if module_path not in sys.modules:
        importlib.import_module(module_path)
    modname = module_path + project_type
    try:
        mod = sys.modules[modname]
    except KeyError:
        try:
            importlib.import_module(project_type, package=module_path)
        except ModuleNotFoundError as exc:
            raise BackendError(status_code=500,
                               reason="Internal Server Error",
                               content="Could not load plugin '%s': %s" %
                               (plugin_name, str(exc)))
        mod = sys.modules[modname]
    return mod
