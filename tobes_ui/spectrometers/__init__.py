"""All the different spectrometer implementations supported by tobes"""
import importlib
import os
import pkgutil
import sys

__all__ = []
_failed_plugins = {}

def failed_plugins():
    """Returns dict of failed plugins and the reason they failed"""
    return _failed_plugins.copy()

__all__.append('failed_plugins')

def _load_plugins():
    for _, name, _ in pkgutil.iter_modules([os.path.dirname(__file__)]):
        module_name = f"{__name__}.{name}"
        try:
            mod = importlib.import_module(module_name)
            setattr(sys.modules[__name__], name, mod)
            __all__.append(name)
        except ImportError as ex:
            _failed_plugins[name] = str(ex)
        except Exception as ex:  # pylint: disable=broad-exception-caught
            _failed_plugins[name] = f"Unexpected error: {ex}"

_load_plugins()
