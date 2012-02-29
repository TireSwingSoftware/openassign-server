
import os.path
import re
import sys
import types

import facade
import settings

VALID_MODULE_NAME = re.compile(r'[_a-z]\w*\.py$', re.IGNORECASE)

def check(func):
    """Decorator for authorizer check functions."""
    setattr(func, '_authorizer_check', True)
    return func

def get_name_from_path(path):
    path = os.path.splitext(os.path.normpath(path))[0]
    _relpath = os.path.relpath(path, settings.PROJECT_ROOT)
    return _relpath.replace(os.sep, '.')

def get_module_from_name(name):
    __import__(name)
    return sys.modules[name]

def get_checks_in_module(module):
    for name in dir(module):
        if name.startswith('_'):
            continue
        obj = getattr(module, name)
        if hasattr(obj, '_authorizer_check'):
            assert callable(obj) and isinstance(obj, types.FunctionType)
            yield obj

def discover_authorizer_checks(startpath=None):
    if not startpath:
        startpath = os.path.dirname(__file__)
    thisdir = os.path.dirname(__file__)
    thisname = get_name_from_path(thisdir)
    for path, dirs, files in os.walk(startpath):
        for name in files:
            if not VALID_MODULE_NAME.match(name):
                continue
            if name == '__init__.py':
                fullpath = path
            else:
                fullpath = os.path.join(path, name)

            name = get_name_from_path(fullpath)
            module = get_module_from_name(name)
            for check in get_checks_in_module(module):
                shortname = '%s.%s' % (name[len(thisname)+1:], check.__name__)
                yield shortname, check

def import_authorizer_checks():
    ACCheckMethod = facade.models.ACCheckMethod
    ACCheckMethod.objects.all().delete()
    for name, check in discover_authorizer_checks():
        ACCheckMethod.objects.create(name=name,
                title=name, description=check.__doc__ or name)
