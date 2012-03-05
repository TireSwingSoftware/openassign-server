"""
This module contains check methods for the authorizer that are specific to
method call authorizations.
"""

import inspect

from decorator import decorator
from operator import itemgetter

from django.core.exceptions import ObjectDoesNotExist

from pr_services.authorizer.checks import check
from pr_services.exceptions import InvalidActeeTypeException

import facade

facade.import_models(locals())

# Here goes a bit of hand waving to make everyone elses life a bit easier when
# making new check methods for method calls.
#
# To create a new check that authorizes a method call do as follows:
#
# @methodcheck
# def foo_check(..., **context):
#    ...
#

_unpack_context = itemgetter('__manager', '__method', '__args', '__kwargs')
def unpack_context(context):
    try:
        return _unpack_context(context)
    except KeyError:
        raise InvalidActeeTypeException()

def _check_context(context):
    """
    A helper for authorizer checks that authorize method calls.

    This checks the context for a check method and ensures that
    the following two conditions are met:

        1) A method call is being authorized. An InvalidActeeTypeException
           is raised if not.

        2) The context matches what was specified by the role if the role
           has specified a manager and method restriction in the check
           method 'parameters'.

           This restriction can be specified as follows:

           methods = [
               {'name': 'method.check_foo_method',
                'parameters': { 'restrict': 'FooManager.foo_method'}}
           ]
    """
    manager, method, args, kwargs = unpack_context(context)
    try:
        restrict_manager, restrict_method = context['restrict'].split('.')
        if (manager.__name__, method.__name__) != (restrict_manager, restrict_method):
            raise InvalidActeeTypeException()
    except KeyError:
        pass

    return manager, method, args, kwargs


def argpos(method, arg):
    spec = inspect.getargspec(method)
    return spec.args.index(arg)


def get_arg_from_context(context, argname):
    """
    Return the value of an argument being passed to a method currently
    being authorized.

    Use this if you need to access the values of arguments being passed to
    a service method but are not gauranteed to know the exact position of the
    argument. This may be the case when one check authorizes more than one
    method call.

    Args:
        context - the method call invocation context
        argname - name of an argument in the method being authorized
    """
    manager, method, args, kwargs = unpack_context(context)
    if argname in kwargs:
        return kwargs[argname]
    i = argpos(method, argname)
    return args[i-2] # self and auth_token are not part of call args


def methodcheck(func):
    """
    Decorator for functions that check method calls. This decorator serves two
    purposes.

    1) Ensure that the check invocation context is appropriate
       (see _check_context)

    2) It will mark the function being decorated for inclusion by the check
       method import machinery. Using this decorator means that you will
       *not* have to do anything special for the method to be available.
    """
    def method_check_wrapper(func, *args, **kwargs):
        _check_context(kwargs)
        return func(*args, **kwargs)
    func = decorator(method_check_wrapper, func)
    setattr(func, '_authorizer_check', True)
    return func


@methodcheck
def instructor_can_email_task_assignees(auth_token, **context):
    """Check that an instructor can send email to task assignees.

    This authorizes a method call which has a `task_id` argument.
    """
    task_id = get_arg_from_context(context, 'task_id')
    try:
        # get the surr for which the instructor is attempting to send email
        surr = SessionUserRoleRequirement.objects.get(id=task_id)
    except ObjectDoesNotExist:
        return False

    return SessionUserRoleRequirement.objects.filter(
            session=surr.session,
            session_user_role__name="Instructor",
            users__in=[auth_token.user_id]).exists()
