"""
Convenient routines for facilitating common test operations.
"""

import functools

from django.core.management import call_command

from pr_services.exceptions import PermissionDeniedException


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

    wrapper.__doc__ = "check permission denied for %s" % (
            func.__doc__ or func.__name__)

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
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            call_command('loaddata', *fixtures,
                    **{'verbosity': 0})
            return func(*args, **kwargs)
        return wrapper
    return decorator

