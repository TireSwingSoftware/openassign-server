"""
This module contains the authorizer class, which is able
to answer the question of whether or not a particular
user has access to a particular attribute on a particular
model.
"""

try:
    import cPickle as pickle
except ImportError:
    import pickle

import collections
import inspect
import logging
import sys
import time

from collections import namedtuple, defaultdict
from functools import partial
from operator import itemgetter

from django.db.models import Model

from pr_services import exceptions

import facade

__all__ = ('Authorizer', )

_INVALID_ACTEE_TYPE_MSG = 'Invalid Actee Type'
_ATTR_NOT_UPDATED_MSG = 'Attributes not updated'

CREATE = 'c'
READ = 'r'
UPDATE = 'u'
DELETE = 'd'
ARBITRARY = 'a'
METHOD = 'm'

facade.import_models(locals(), globals())

_sentinel = object()
def defaultargvalue(method, argname):
    """
    Return the default value for argument `argname` in the signiture of `method`.
    If the argument does not exist an exception is raised. If there is no
    default value a sentinel object is returned to allow distinction between no
    default argument and a default argument with a None value.

    Raises:
        ValueError - if argument does not exist in method signiture
    """
    argspec = inspect.getargspec(method)
    argpos = argspec.args.index(argname) # throws the value exception
    if not argspec.defaults:
        return _sentinel
    # offset is the pos in argspec.args where default values begin
    offset = len(argspec.args) - len(argspec.defaults)
    if argpos >= offset:
        return argspec.defaults[argpos - offset]
    else:
        return _sentinel


class CheckMethodNotFound(Exception):
    pass

class CheckMethodWrapper(namedtuple('_CheckMethodWrapper',
                                    'method actee_required allow_guests')):
    """
    Structure for wrapping check method objects to expose a more efficient
    interface to access the properties we need when running the checks. Provides
    a thin interface to call the method checks with the appropriate handling.
    """

    @property
    def name(self):
        return self.method.func.__name__

    def __new__(cls, method_name, method_kwargs):
        """
        Args:
            method_name - A string representing the method name
            method_kwargs - the static parameters to pass to the check method
                         (defined by the role)
        """
        # TODO: decouple check methods from the authorizer by replacing the
        # method lookup mechanism with something a bit more sophisticated.
        if '.' in method_name:
            suite, _, method_name = method_name.rpartition('.')
            import_path = 'pr_services.authorizer.checks.%s' % suite
        else:
            import_path = 'pr_services.authorizer.checks'

        if import_path in sys.modules:
            module = sys.modules[import_path]
        else:
            module = __import__(import_path, fromlist=[method_name])
        try:
            method = getattr(module, method_name)
        except AttributeError:
            raise CheckMethodNotFound('%s.%s' % (import_path, method_name))

        # check if the actee is required/used by the check method.
        # it is considered to be required if the method has an argument
        # called 'actee' and that it does not default to None
        try:
            actee_required = defaultargvalue(method, 'actee') is not None
        except ValueError:
            actee_required = False

        # check if the method requires an auth token, if not allow guests
        try:
            allow_guests = defaultargvalue(method, 'auth_token') is None
        except ValueError:
            allow_guests = True

        # apply the method keyword arguments defined by the role
        method = partial(method, **method_kwargs)

        return super(CheckMethodWrapper, cls).__new__(cls, method,
                actee_required, allow_guests)

    def __call__(self, auth_token=None, actee=None, *args, **kwargs):
        if not isinstance(auth_token, AuthToken):
            if auth_token:
                raise exceptions.NotLoggedInException
            if not self.allow_guests:
                # fast-path: user is guest and guest is not allowed
                return False
        if self.actee_required and not actee:
            raise exceptions.InvalidActeeTypeException

        return self.method(auth_token=auth_token, actee=actee, *args, **kwargs)


class ACLWrapper(namedtuple('_ACLWrapper', 'object privs methods')):
    """
    A wrapper around ACL and ACMethodCall model objects to expose a more
    efficient interface for the type of access required by the authorizer.
    """

    def check(self, auth_token=None, actee=None, *args, **kwargs):
        """
        Execute the check methods for the acl structure `self` represents using
        `auth_token` and `actee` if required. If the operation is an update, a
        keyword argument `update_dict` should be passed with a dictionary of
        changed key-value pairs.

        Args:
            auth_token - an auth token for the user performing the operation
            actee - *optional* object being acted on
            update_dict - *optional* dict of attribute updates used only for
                         update operations.

        Returns:
            The result of all check method results ANDed together
        """

        # Process each ACL method and log the entire process
        # ignore InvalidActeeTypeException but ensure that in order
        # to return True the following conditions must be met:
        #
        #   1) at least one check has a valid actee type
        #   2) all checks accepting actee type, return True (logical AND)
        log = facade.subsystems.Authorizer.logger
        valid_type = False
        log.add_row(('Actee Type:', type(actee).__name__,
            '(op=%s)' % kwargs['op']))
        for method in self.methods:
            role_name = self.object.role.name
            log_entry = [role_name, method.name]
            try:
                result = method(auth_token, actee, *args, **kwargs)
                valid_type = True
                log_entry.append(result)
                log.add_row(log_entry)
                if not result:
                    # short-circuit if method check fails
                    log.add_row(('Result:', 'DENIED', ''))
                    log.commit()
                    return False
            except exceptions.InvalidActeeTypeException:
                log_entry.append(_INVALID_ACTEE_TYPE_MSG)
                log.add_row(log_entry)
            except exceptions.AttributeNotUpdatedException:
                #XXX: is this catch still necessary?
                log_entry.append(_ATTR_NOT_UPDATED_MSG)
                log.add_row(log_entry)
        # at this point no acl check method has returned False
        # all acl check methods passed or raised an exception
        message = 'GRANTED' if valid_type else 'DENIED'
        log.add_row(('Result:', message, ''))
        log.commit()
        return valid_type


class ACLCache(object):
    """
    A simple authorizer-specific caching mechanism for efficiently storing all
    ACL objects and related models.

    ACLs are partitioned into several dicts for each of the crud operations
    allowing more efficient lookup for ACLs given an operation and a specific
    type.
    """

    # a timestamp for when the cache was last updated
    timestamp = None

    # a two-dimensional dictionary of acls where the dimensions of the
    # mapping are [type of operation ie. CREATE] [ operation specific key ]
    _acls = None

    def __len__(self):
        return len(self.acls)

    def __init__(self):
        """Load all ACL related objects from the database."""
        def acldict():
            return defaultdict(list)

        # grab all the methods first sine we can do this in one query
        method_cols = ('acl', 'ac_check_method__name', 'ac_check_parameters')
        method_call_items = itemgetter(*method_cols)
        aclmethods = defaultdict(list)
        for method_call in ACMethodCall.objects.values(*method_cols):
            acl, method_name, kwargs = method_call_items(method_call)
            kwargs = pickle.loads(str(kwargs)) if kwargs else {}
            method = CheckMethodWrapper(str(method_name), kwargs)
            aclmethods[acl].append(method)

        c, r, u, d = acldict(), acldict(), acldict(), acldict()
        a, m = acldict(), acldict()

        # grab all the acl objects in one more query
        for acl in ACL.objects.select_related():
            privs = pickle.loads(str(acl.acl))
            cached_acl = ACLWrapper(acl, privs, aclmethods[acl.id])
            for actee_type, priv in privs.iteritems():
                if hasattr(facade.models, actee_type):
                    # XXX: it is critical for the integrity of the authorizer
                    # that acls *not* be added to these maps unless they
                    # are capable of granting the relevant permission
                    if priv.get(CREATE, None):
                        c[actee_type].append(cached_acl)
                    if priv.get(READ, None):
                        r[actee_type].append(cached_acl)
                    if priv.get(UPDATE, None):
                        u[actee_type].append(cached_acl)
                    if priv.get(DELETE, None):
                        d[actee_type].append(cached_acl)
                elif getattr(facade.managers, actee_type, None):
                    # handle manager method permissions
                    for method_name in priv['methods']:
                        manager_class = getattr(facade.managers, actee_type)
                        assert hasattr(manager_class, method_name)
                        # (manager name, method_name)
                        m[(actee_type, method_name)].append(cached_acl)
                else:
                    raise TypeError("unauthorizable type %s" % actee_type)

            # handle arbitrary permissions
            if acl.arbitrary_perm_list:
                serialized = str(acl.arbitrary_perm_list)
                arbitrary_perms = frozenset(pickle.loads(serialized))
                for perm in arbitrary_perms:
                    a[perm].append(cached_acl)

        self._acls = {
            CREATE: c, READ: r, UPDATE: u, DELETE: d,
            ARBITRARY: a,
            METHOD: m
        }
        self.timestamp = time.time()

    def collect(self, op, key):
        """
        Return a list of acls relevant for `op` given `key`.

        For create, read, update, or delete operations the key is the actee
        object and this method runs with worst-case O(m) complexity where m is
        the depth of the actee's type heirarchy.

        For method operations the key is a 2-tuple of
        (manager class name, method name). Access is O(1)

        For arbitrary permissions the key is a string
        representing the permission. Access is O(1).

        Args:
            op - the operation being performed, a single character in 'crud'
            key - an operation specific acl key. For crud operations this is
                  the actee. For method operations, (manager name, method name).
                  For arbitrary permissions, the permission name.

        Returns:
            A list of cached ACL objects (See `ACLWrapper` above)
        """
        if op in (METHOD, ARBITRARY):
            return self._acls[op].get(key, ())

        if op in (CREATE, READ, UPDATE, DELETE):
            acls = self._acls[op]
            typeobj = key if isinstance(key, type) else type(key) # key is actee
            name = typeobj.__name__
            if name in acls:
                return acls[name]
            else:
                for basetype in inspect.getmro(typeobj):
                    name = basetype.__name__
                    if name in acls:
                        return acls[name]
                else:
                    return ()
        else:
            assert False


class Authorizer(object):
    """
    The default authorizer for the PR system. It determines based on an
    auth_token and access controls defined as part of a role, whether or not
    the user represented by the auth_token has the privileges to perform an
    operation.

    Currently supported authorization types:

        - create, read, update, and delete for any PRModel object.

        - method invokation for ObjectManager methods wrapped with
          the @service_method decorator.

        - arbitrary permissions
    """

    acls = ACLCache()
    logger = facade.subsystems.Logger('pr_services.authorizer', logging.getLevelName('TRACE'))

    @classmethod
    def flush(cls):
        """Flush all cached ACLs and reload them from the database."""
        # XXX: this assignment is atomic so other threads reading from the
        # current cache (if there is one) will continue doing so until they
        # request a new reference. This will allow for uninterupted iteration
        # of the acl dict and/or sub-dicts.
        cls.acls = ACLCache()

    @classmethod
    def check_method_call(cls, auth_token, manager, method,
            call_args=(), call_kwargs=None):
        """
        Check if the `auth_token` user has access to call `method` on
        `manager`, an instance of ObjectManager.

        Args:
            auth_token - the auth token of the user performing the operation
            manager - an instance of ObjectManager or subclass
            method - the method which will be called (a python function object)
            args - a tuple of arguments passed to `method`
            kwargs - a dict of keyword arguments passed to `method`

        Raises:
            PermissionDeniedException - For insufficient privileges
        """
        # cant use the facade for this import and it has to happen here
        # since Authorizer is used in ObjectManager
        from pr_services.object_manager import ObjectManager

        if not (isinstance(manager, type) and
                issubclass(manager, ObjectManager)):
            if isinstance(manager, ObjectManager):
                manager = manager.__class__
            elif isinstance(manager, basestring):
                manager = getattr(facade.managers, manager)
            else:
                raise TypeError("invalid manager type '%s'" % type(manager).__name__)

        if isinstance(method, basestring):
            method = getattr(manager, method)
        if not callable(method):
            raise TypeError("invalid method type '%s'" % type(method).__name__)

        key = (manager.__name__, method.__name__)
        acls = cls.acls.collect(METHOD, key)
        # XXX: For backwards compatibility method checks will be permissive by
        # default unless there exists one ACL which checks the method
        if not acls: # fast-path: many methods wont have ACLs
            return

        # the underscores are to prevent name collisions with the method
        # 'parameters' defined as part of the role
        context = dict(
            __manager=manager,
            __method=method,
            __args=call_args,
            __kwargs=call_kwargs or {})

        if not any(acl.check(auth_token, op=METHOD, **context) for acl in acls):
            raise exceptions.PermissionDeniedException()

    @classmethod
    def check_arbitrary_permissions(cls, auth_token, permission):
        """
        Check if the `auth_token` user has access to an arbitrary `permission`.
        If not, an exception is raised.

        Args:
            permission - A string representing the arbitrary permission

        Raises:
            PermissionDeniedException - For insufficient privileges
        """
        assert isinstance(permission, str)

        acls = cls.acls.collect(ARBITRARY, permission)
        if not any(acl.check(auth_token, None, op=ARBITRARY) for acl in acls):
            raise exceptions.PermissionDeniedException()

    @classmethod
    def check_create_permissions(cls, auth_token, actee):
        """
        Check if the `auth_token` user has create permissions for `actee`.
        An exception is raised if not.

        Args:
            actee - the object being created

        Raises:
            PermissionDeniedException - For insufficient privileges
        """
        assert isinstance(actee, Model) or issubclass(actee, Model)

        acls = cls.acls.collect(CREATE, actee)
        if not any(acl.check(auth_token, actee, op=CREATE) for acl in acls):
            raise exceptions.PermissionDeniedException()

    @classmethod
    def _check_attributes(cls, op, auth_token, actee, attributes):
        """
        Check that the `auth_token` user is authorized to perform `op` on the
        specified `attributes` of `actee`.
        """
        assert attributes and op in 'crud'
        assert isinstance(actee, Model) or issubclass(actee, Model)

        if not isinstance(attributes, collections.Set):
            attributes = frozenset(attributes)

        authorized = cls.get_authorized_attributes(op, auth_token, actee, attributes)
        if not authorized:
            raise exceptions.PermissionDeniedException()

        denied = attributes - authorized
        if denied:
            raise exceptions.PermissionDeniedException(denied, actee._meta.object_name)

    @classmethod
    def check_read_permissions(cls, auth_token, actee, attributes):
        """
        Check that the `auth_token` user has permission to read `attributes`
        of `actee`. An exception is raised if not.

        For a comprehensive list of all authorized fields,
        use the `get_authorized_attributes` method instead.

        Args:
            actee - the object being acted upon
            attributes - a set of attributes to read

        Raises:
            PermissionDeniedException - For insufficient privileges
        """
        cls._check_attributes(READ, auth_token, actee, attributes)

    @classmethod
    def check_update_permissions(cls, auth_token, actee, update_dict):
        """
        Checks that the `auth_token` user has permission to update `actee` using
        key-value pairs from `update_dict` as the object's attributes.

        An exception is raised if the user does not have sufficient privileges.

        For a comprehensive list of all authorized fields,
        use the `get_authorized_attributes` method instead.

        Args:
            actee - the object being acted upon
            update_dict - a dict of attributes (name-value pairs) to update

        Raises:
            PermissionDeniedException - For insufficient privileges
        """
        cls._check_attributes(UPDATE, auth_token, actee, update_dict)

    @classmethod
    def check_delete_permissions(cls, auth_token, actee):
        """
        Checks if the `auth_token` user has permission to delete `actee`. An
        exception is raised if not.

        Args:
            actee - the object being deleted

        Raises:
            PermissionDeniedException - For insufficient privileges
        """
        assert isinstance(actee, Model) or issubclass(actee, Model)

        acls = cls.acls.collect(DELETE, actee)
        if not any(acl.check(auth_token, actee, op=DELETE) for acl in acls):
            raise exceptions.PermissionDeniedException()

    @classmethod
    def get_authorized_attributes(cls, op, auth_token, actee, requested, update_dict=None):
        """
        Returns a list of fields for which the `auth_token` user has permission
        to perform the operation `op` on the actee.

        Args:
            op - the operation being performed, 'r' (read) or 'u' (update)
            actee - the object being acted on
            requested - a subset of attributes to verify
            update_dict - a dict of attributes (name-value pairs) to update

        Returns:
            A list of fields that the user is authorized to access.
        """
        assert op in 'ru'
        assert isinstance(actee, Model) or issubclass(actee, Model)

        actee_type = actee._meta.object_name
        authorized = set()
        if not isinstance(requested, collections.Set):
            requested = frozenset(requested)

        acls = cls.acls.collect(op, actee)
        for acl in acls:
            crud = acl.privs.get(actee_type)
            if not crud:
                for basetype in inspect.getmro(type(actee)):
                    crud = acl.privs.get(basetype.__name__, None)
                    if crud:
                        break
                else:
                    continue
            attributes = crud[op]
            if requested and not any(f in attributes
                    for f in requested if f not in authorized):
                # short-circuit: skip the methods if there are no attributes
                continue
            if not acl.check(auth_token, actee, update_dict=update_dict, op=op):
                # method checks failed
                continue
            authorized.update(attributes)
            if requested and authorized >= requested:
                # all requested attributes are authorized
                return requested
        # return the intersection of authorized and requested attributes
        return authorized & requested if requested else authorized

# vim:tabstop=4 shiftwidth=4 expandtab
