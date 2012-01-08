"""
Convenient routines for facilitating common test operations.
"""

import functools

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
