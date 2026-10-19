"""Load a repo script (guard.py, safe-run, heat, ...) as a module.

SourceFileLoader.load_module() is gone in Python 3.15. The loader is passed
explicitly because safe-run, heat, fleet and thermal-report have no .py suffix,
so spec_from_file_location() would not pick one. Works on /usr/bin/python3
(3.9), which is what the LaunchAgent runs.
"""
import importlib.machinery
import importlib.util
import sys


def load_source(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod          # load_module() registered it as well
    spec.loader.exec_module(mod)
    return mod
