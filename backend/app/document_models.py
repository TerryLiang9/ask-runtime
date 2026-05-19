from importlib import import_module
import sys

_module = import_module("app.knowledge.models")
sys.modules[__name__] = _module

