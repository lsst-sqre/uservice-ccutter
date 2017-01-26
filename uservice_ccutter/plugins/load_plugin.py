"""Load a plugin module by name"""
import importlib
import sys
from apikit import BackendError
try:
    from importlib import ModuleNotFoundError
except ImportError:
    ModuleNotFoundError = ImportError


def load_plugin(plugin_name):
    """Load a named plugin.  Substitute "-" with "_" first.  If the module
    is already loaded, return it; if not, load it and then return the
    loaded module."""
    ctt = "." + plugin_name.lower().replace("-", "_")
    ctr = ".".join(__name__.split(".")[:-1])
    modname = ctr + ctt
    mod = None
    try:
        mod = sys.modules[modname]
    except KeyError:
        try:
            importlib.import_module(ctt, package=ctr)
        except ModuleNotFoundError as exc:
            raise BackendError(status_code=500,
                               reason="Internal Server Error",
                               content="Could not load plugin '%s': %s" %
                               (plugin_name, str(exc)))
        mod = sys.modules[modname]
    return mod
