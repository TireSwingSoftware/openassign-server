from __future__ import with_statement

import cPickle
import functools
import re
import inspect

from datetime import datetime, timedelta
from operator import itemgetter

import django.utils.unittest
import django.test

from celery import conf
from django.conf import settings

from pr_services import pr_time
from pr_services.object_manager import ObjectManager

import facade
import helpers

__all__ = ['common', 'mixins', 'helpers']

_ONEDAY = timedelta(days=1)

facade.import_models(locals(), globals())
get_auth_token_object = facade.subsystems.Utils.get_auth_token_object

# index of service methods' names by manager class type object
_SERVICE_METHODS = dict()

# XXX: use a function to hide stuff from the namespace
def _build_service_method_index():
    """Build an index of service methods for each manager class."""

    _member_name = itemgetter(0)
    exclude = frozenset(('login', 'check_password_against_policy',
                         'reset_password'))

    def _service_methods(member):
        name, value = member
        return name not in exclude and getattr(value, '_service_method', False)

    for name in facade.managers:
        manager_class = getattr(facade.managers, name)
        if issubclass(manager_class, ObjectManager):
            members = inspect.getmembers(manager_class)
            service_methods = filter(_service_methods, members)
            service_method_names = map(_member_name, service_methods)
            _SERVICE_METHODS[manager_class] = frozenset(service_method_names)

_build_service_method_index()


class ManagerAuthTokenWrapper(object):
    """
    Wrap ObjectManager service methods to automatically provide a specified auth token
    """

    def __init__(self, manager, token_getter):
        assert isinstance(manager, ObjectManager)
        assert callable(token_getter)
        self.manager = manager
        self.token_getter = token_getter
        self._service_methods = _SERVICE_METHODS[type(manager)]

    def _wrapped_method(self, method):
        @functools.wraps(method)
        def _wrapper(*args, **kwargs):
            if args and isinstance(args[0], AuthToken):
                return method(*args, **kwargs)
            token = kwargs.pop('auth_token', self.token_getter())
            try:
                return method(token, *args, **kwargs)
            except TypeError as e:
                msg = str(e)
                if 'takes exactly' in msg:
                    return method(*args, **kwargs)
                raise

        return _wrapper

    def __getattr__(self, name):
        attr = getattr(self.manager, name)
        if name in self._service_methods:
            return self._wrapped_method(attr)
        else:
            return attr


# Mapping of Manager names to Test class instance member names
# Ex. for UserManager the instance member is self.user_manager
# This dictionary will map UserManager to user_manager
_MANAGER_MEMBER_NAMES = dict()

# XXX: use a function to hide stuff from the namespace
def _build_manager_member_names():
    nocamel = re.compile('(.)([A-Z])')
    for manager_name in facade.managers:
        member_name = nocamel.sub(r'\1_\2', manager_name).lower()
        _MANAGER_MEMBER_NAMES[manager_name] = member_name

_build_manager_member_names()


class TestCase(django.test.TestCase):
    """
    Base class used to do *very* basic setup for power reg test cases.
    """

    def __init__(self, *args, **kwargs):
        super(TestCase, self).__init__(*args, **kwargs)
        self._flush_acls = True

    def setUp(self):
        super(TestCase, self).setUp()

        self._save_settings()
        self._setup_managers()

        # XXX: this is somewhat of an optimization for the tests
        # flush ACLs once for each test class but only after the
        # fixtures are loaded the first time.
        if self._flush_acls:
            facade.subsystems.Authorizer()._load_acls()
            self._flush_acls = False

        # Modify the celery configuration to run tasks eagerly for unit tests.
        self._always_eager = conf.ALWAYS_EAGER
        conf.ALWAYS_EAGER = True

    def tearDown(self):
        conf.ALWAYS_EAGER = self._always_eager
        self._restore_settings()
        super(TestCase, self).tearDown()

    def _save_settings(self):
        """Save configuration for restoring later if changes are made."""
        self._settings = dict()
        for key in dir(settings):
            if key == key.upper():
                self._settings[key] = getattr(settings, key)

    def _restore_settings(self):
        """Restore all configuration settings to their previous values."""
        for key, value in self._settings.iteritems():
            setattr(settings, key, value)

    def _get_auth_token(self, username, password='password'):
        """Perform user login and return the auth token object."""
        sid = self.user_manager.login(username, password)['auth_token']
        return get_auth_token_object(sid)

    def _setup_managers(self, include_admin=False):
        """
        Setup common managers for convenience in subclasses

        The instance members will have the same name as the manager but
        lowercase and underscored instead of CamelCase. The 'FooBarManager'
        will be foo_bar_manager.

        Args:
            include_admin: if True, an additional 'admin_foo_bar_manager'
            manager will be provided which wraps the foo_bar manager with an
            admin token such that all operations are expected to succeed.
            This can be used to conveniently setup a test context without
            having to worry about getting the correct token to do so.
        """
        get_default_token = lambda: self.auth_token
        get_admin_token = lambda: self.admin_token
        for manager_name in facade.managers:
            manager_class = getattr(facade.managers, manager_name)
            member_name = _MANAGER_MEMBER_NAMES[manager_name]
            manager = manager_class()
            if isinstance(manager, ObjectManager):
                default_manager = ManagerAuthTokenWrapper(manager, get_default_token)
                setattr(self, member_name, default_manager)
                if include_admin:
                    admin_manager = ManagerAuthTokenWrapper(manager, get_admin_token)
                    setattr(self, 'admin_%s' % member_name, admin_manager)
            else:
                setattr(self, member_name, manager)


class BasicTestCase(TestCase):
    """
    Basic test case which loads the default initial setup objects and exposes a
    few simple primitives.
    """

    fixtures = [
        'initial_setup_default',
    ]

    def setUp(self):
        super(BasicTestCase, self).setUp()
        self._setup_admin_token()

        self.utils = facade.subsystems.Utils()
        self.right_now = datetime.utcnow().replace(microsecond=0, tzinfo=pr_time.UTC())
        self.one_day = _ONEDAY

    def _setup_admin_token(self):
        """Create an easy-access auth token with the admin user."""
        da = DomainAffiliation.objects.get(username='admin', domain__name='local', default=True)
        self.admin_user = da.user

        self.admin_token = self._get_auth_token('admin', 'admin')
        # default the general auth token to administrator
        self.auth_token = self.admin_token

    def _setup_managers(self):
        """See `TestCase._setup_managers`."""
        super(BasicTestCase, self)._setup_managers(include_admin=True)


class GeneralTestCase(BasicTestCase):
    """
    Legacy test class for backwards compatability with existing tests that do not
    make use of newer fixtures.
    """

    fixtures = [
        'initial_setup_default',
        'legacy_objects',
    ]

    def setUp(self):
        super(GeneralTestCase, self).setUp()

        # create instance variables for our 4 test users
        # self.user1
        # self.user1_auth_token
        # ...
        # self.user4
        # self.user4_auth_token
        for i in range(1, 5):
            user = User.objects.get(id=i + 1)
            username = 'user%d' % i
            sid = self.user_manager.login(username, 'password')['auth_token']
            setattr(self, username, user)
            setattr(self, username + '_auth_token', get_auth_token_object(sid))

        # create some other useful objects
        self.region1 = Region.objects.get(name='Region 1')
        self.venue1 = Venue.objects.get(name='Venue 1')
        self.room1 = Room.objects.get(name='Room 1')
        self.product_line1 = ProductLine.objects.get(name='Product Line 1')
        self.organization1 = Organization.objects.get(name='Organization 1')


class RoleTestCaseMetaclass(type):
    def __new__(cls, name, bases, attrs):
        check_permission_denied = attrs.get('CHECK_PERMISSION_DENIED', [])
        for func_name in check_permission_denied:
            func = attrs.get(func_name, None)
            if not func:
                for base in bases:
                    if hasattr(base, func_name):
                        func = getattr(base, func_name)
                        break
                if not func:
                    raise AttributeError("attribute '%s' not found" % func_name)
            if not callable(func):
                raise ValueError("attribute '%s' not callable" % func_name)
            attrs[func_name] = helpers.expectPermissionDenied(func)
        return type.__new__(cls, name, bases, attrs)


class RoleTestCase(BasicTestCase):
    __metaclass__ = RoleTestCaseMetaclass

    def create_quick_user_role(self, name, acl_dict):
        create_role = facade.models.Role.objects.create
        create_acl = facade.models.ACL.objects.create
        methods = facade.models.ACCheckMethod.objects
        ACMethodCall = facade.models.ACMethodCall

        for model, crud in acl_dict.iteritems():
            crud.setdefault('c', False)
            crud.setdefault('r', set())
            crud.setdefault('u', set())
            crud.setdefault('d', False)

        role = create_role(name=name)
        acl = create_acl(role=role, acl=cPickle.dumps(acl_dict))
        method = methods.get(name='actor_is_anybody')
        method_call = ACMethodCall.objects.create(acl=acl,
                ac_check_method=method,
                ac_check_parameters=cPickle.dumps({}))

        method_call.save()

#XXX: if we're going to call this, the method should be public
        facade.subsystems.Authorizer()._load_acls()

        def _cleanup():
            method_call.delete()
            acl.delete()
            role.delete()
            facade.subsystems.Authorizer()._load_acls()
        self.addCleanup(_cleanup)

        return role, acl
