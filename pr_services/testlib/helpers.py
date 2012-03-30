"""
Convenient routines for facilitating common test operations.
"""

import functools

from decorator import decorator
from operator import itemgetter

from django.core.management import call_command

from pr_services import pr_time
from pr_services.exceptions import PermissionDeniedException

__all__ = (
    'datestring',
    'expectPermissionDenied',
    'load_fixtures',
    'object_dict',
    'sorted_id',
    )

def expectPermissionDenied(func):
    """
    Function decorator for wrapping test methods which cause a
    PermissionDeniedException to be raised.

    Example test method:

    @expectPermissionDenied
    def test_foo_denied(self):
        # raise a PermissionDeniedException here
        do_something_wrong()
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        self.assertRaises(PermissionDeniedException,
                func, self, *args, **kwargs)
    return wrapper


def load_fixtures(*fixtures):
    """
    Decorator for loading fixtures for a single test method.

    Example:
        class FooTest(TestCase):
            # fixtures for all test methods
            fixtures = ['some_big_fixture']

            def test_foo(self):
                ...

            @load_fixtures('small_fixture1', 'small_fixture2')
            def test_bar(self):
                # do something testy
                ...
    """
    @decorator
    def wrapper(func, self, *args, **kwargs):
        # 'commit = False' tells the loaddata command to not use its
        # own transaction management
        extra_fixtures = [f for f in fixtures if not f in self.fixtures]
        if extra_fixtures:
            call_command('loaddata', *extra_fixtures,
                    **{'verbosity': 0, 'commit': False})
        return func(self, *args, **kwargs)
    return wrapper


def object_dict(obj, attributes):
    """
    Create a dictionary based on the specified `attributes` of object `obj`.

    Args:
        obj: A model object
        attributes: A list of attributes to include in the result dict

    Return:
        a dictionary with `attributes` as keys and values from `obj`

    Example:
        examobj = Exam.objects.create(name='Foo')
        object_dict(examobj, ('id', 'name'))
        >>> {'id': 1, 'name': foo}
    """
    _hasattr = functools.partial(hasattr, obj)
    keys = filter(_hasattr, attributes)
    d = dict.fromkeys(keys)
    for key in d:
        d[key] = getattr(obj, key)
    return d


def datestring(d):
    """Convert date to string format using UTC tzinfo"""
    return d.replace(tzinfo=pr_time.UTC()).isoformat()


sorted_id = functools.partial(sorted, key=itemgetter('id'))
