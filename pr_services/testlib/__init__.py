from __future__ import with_statement

import cPickle
import functools
import re
import inspect

from datetime import datetime, timedelta
from operator import itemgetter

import django.utils.unittest

from django import test
from django.conf import settings
from django.core import cache, mail
from django.core.management import call_command
from django.db import transaction, connection, connections, DEFAULT_DB_ALIAS
from celery import conf

from pr_services import pr_time
from pr_services.object_manager import ObjectManager

import facade
import helpers
import mixins

__all__ = (
    'FixtureTestCase',
    'BasicTestCase',
    'GeneralTestCase',
    'RoleTestCase'
    'TestCase',
)

_ONEDAY = timedelta(days=1)

facade.import_models(locals(), globals())
get_auth_token_object = facade.subsystems.Utils.get_auth_token_object

_DEFAULT_AUTHORIZER = facade.subsystems.Authorizer()

class ManagerAuthTokenWrapper(object):
    """
    Wrap ObjectManager service methods to automatically provide a specified auth token
    """
    def __init__(self, manager, token_getter):
        assert isinstance(manager, ObjectManager)
        assert callable(token_getter)
        self.manager = manager
        self.token_getter = token_getter

    def _wrapped_method(self, method):
        spec = inspect.getargspec(method)
        @functools.wraps(method)
        def wrapper(*args, **kwargs):
            if 'auth_token' in kwargs:
                auth_token = kwargs.pop('auth_token')
                return method(auth_token, *args, **kwargs)
            if ((args and isinstance(args[0], AuthToken)) or
                len(args) >= len(spec.args) - 1):
                return method(*args, **kwargs)
            auth_token = self.token_getter()
            return method(auth_token, *args, **kwargs)
        return wrapper

    def __getattr__(self, name):
        obj = getattr(self.manager, name)
        if callable(obj) and hasattr(obj, '_service_method'):
            return self._wrapped_method(obj)
        else:
            return obj


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

class FixtureTestCase(test.TransactionTestCase):

    @classmethod
    def setUpClass(cls):
        if not test.testcases.connections_support_transactions():
            raise NotImplementedError('%s requires DB with transaction '
                                      'capability.' % cls.__name__)
        for db in cls._databases():
            transaction.enter_transaction_management(using=db)
            transaction.managed(True, using=db)
        cls._fixture_setup()

    @classmethod
    def tearDownClass(cls):
        for db in cls._databases():
            if transaction.is_dirty(using=db):
                transaction.commit(using=db)
            transaction.leave_transaction_management(using=db)

    @classmethod
    def _fixture_setup(cls):
        for db in cls._databases():
            if hasattr(cls, 'fixtures'):
                if getattr(cls, '_fb_should_setup_fixtures', True):
                    call_command('syncdb', verbosity=0, interactive=False)
                    call_command('flush', verbosity=0, interactive=False,
                            database=db)
                    call_command('loaddata', *cls.fixtures, verbosity=0,
                            commit=False, database=db)
            elif not hasattr(cls, '_fb_should_setup_fixtures'):
                call_command('syncdb', verbosity=0, interactive=False)
                call_command('flush', verbosity=0, interactive=False,
                        database=db)
            transaction.commit(using=db)

    def _pre_setup(self):
        cache.cache.clear()
        test.testcases.disable_transaction_methods()
        self._urlconf_setup()
        mail.outbox = []
        from django.contrib.sites.models import Site
        Site.objects.clear_cache()

    def _post_teardown(self):
        test.testcases.restore_transaction_methods()
        for db in self._databases():
            transaction.rollback(using=db)
        self._urlconf_teardown()

    @classmethod
    def _databases(cls):
        if getattr(cls, 'multi_db', False):
            databases = connections
        else:
            databases = [DEFAULT_DB_ALIAS]
        return databases


class TestCase(FixtureTestCase):
    """
    Base class used to do *very* basic setup for power reg test cases.
    """

    def __init__(self, *args, **kwargs):
        super(TestCase, self).__init__(*args, **kwargs)
        self.authorizer = _DEFAULT_AUTHORIZER

    def setUp(self):
        super(TestCase, self).setUp()

        self._save_settings()
        self._setup_managers()
        self.authorizer.flush()

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


class RoleTestCase(BasicTestCase, mixins.RoleTestMixin):
    __metaclass__ = RoleTestCaseMetaclass

