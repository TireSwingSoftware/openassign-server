
import inspect
import os.path
import re
import sys
import types

from decorator import decorator

import facade
import settings

from pr_services.exceptions import InvalidActeeTypeException

VALID_MODULE_NAME = re.compile(r'[_a-z]\w*\.py$', re.IGNORECASE)

def check(*args, **kwargs):
    """Decorator for authorizer check functions to reduce boilerplate
    operations and provide filtering by actee types while raising
    InvalidActeeTypeException when appropriate.

    Example:
        @check(Foo, Bar)
        def some_check_function(auth_token, actee, *args, **kwargs):
            # this is only called when the actee is a Foo or Bar object
            pass

    Keyword Arguments:
        pre_hooks: A sequence of functions which will be executed before the
                   check function being decorated. If any hook returns False,
                   the check will short-circuit and return False.

        post_hooks: A sequence of functions which will be executed after the
                    check function being decorated. If any function returns
                    False, the check will return False.
    """
    pre_hooks = kwargs.get('pre_hooks', None)
    post_hooks = kwargs.get('post_hooks', None)
    if len(args) == 1 and isinstance(args[0], types.FunctionType):
        func = args[0]
        setattr(func, '_authorizer_check', True)
        setattr(func, '_check_types', None)
        return func

    check_types = args
    def check_wrapper(func):
        spec = inspect.getargspec(func)
        actee_argpos = spec.args.index('actee')
        def inner(func, *args, **kwargs):
            actee = kwargs.get('actee', None)
            if not actee:
                actee = args[actee_argpos]
            if not isinstance(actee, check_types):
                raise InvalidActeeTypeException(actee)
            if pre_hooks:
                if not all(h(func, *args, **kwargs) for h in pre_hooks):
                    return False
            result = func(*args, **kwargs)
            if post_hooks:
                if not all(h(func, result, *args, **kwargs) for h in post_hooks):
                    return False
            return result
        func = decorator(inner, func)
        setattr(func, '_authorizer_check', True)
        setattr(func, '_check_types', check_types)
        return func
    return check_wrapper


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
