from __future__ import with_statement

import cPickle
import functools
import re

import django.utils.unittest

from celery import conf
from datetime import datetime, timedelta
from django.conf import settings

from pr_services import pr_time
from pr_services.initial_setup import InitialSetupMachine
from pr_services.object_manager import ObjectManager

import facade
import helpers

__all__ = ['common', 'mixins', 'helpers']

class ManagerAuthTokenWrapper(object):
    """
    Wrap ObjectManager methods to automatically provide a specified auth token
    """

    WRAP_METHODS = ('create', 'batch_create', 'update', 'get_filtered', 'check_exists')

    def __init__(self, manager, token_getter):
        assert isinstance(manager, ObjectManager)
        assert callable(token_getter)
        self.manager = manager
        self.token_getter = token_getter

    def _wrapped_method(self, method):
        @functools.wraps(method)
        def _wrapper(*args, **kwargs):
            if args and isinstance(args[0], facade.models.AuthToken):
                return method(*args, **kwargs)
            token = kwargs.pop('auth_token', self.token_getter())
            return method(token, *args, **kwargs)

        return _wrapper

    def __getattr__(self, name):
        attr = getattr(self.manager, name)
        if name in self.WRAP_METHODS:
            return self._wrapped_method(attr)
        else:
            return attr

# make stdout and stderr use UTF-8 encoding so that printing out
# UTF-8 data while debugging doesn't choke

class TestCase(django.test.TestCase, django.utils.unittest.TestCase):
    """Super-class used to do basic setup for almost all power reg test cases.

    This is useful for getting authentication taken care of without duplicating
    a lot of code.

    """
    def setUp(self):
        # Save all configuration settings so they can be restored following the test.
        self._settings = dict((x, getattr(settings, x)) for x in dir(settings) if x == x.upper())
        initial_setup_args = getattr(self, 'initial_setup_args', [])
        initial_setup_kwargs = getattr(self, 'initial_setup_kwargs', {})
        InitialSetupMachine().initial_setup(*initial_setup_args, **initial_setup_kwargs)
        self.setup_managers()
        self.utils = facade.subsystems.Utils()
        self.admin_da = facade.models.DomainAffiliation.objects.get(username='admin', domain__name='local',
            default=True)
        self.admin_user = self.admin_da.user
        self.admin_token_str=self.user_manager.login('admin', 'admin')['auth_token']
        self.admin_token = facade.subsystems.Utils.get_auth_token_object(self.admin_token_str)
        self.auth_token = self.admin_token
        self.user1 = self.user_manager.create(self.admin_token, 'username', 'initial_password',
            'Mr.', 'Primo', 'Uomo', '555.555.5555', 'user1@acme-u.com', 'active', {'name_suffix': 'Sr.'})
        self.user1_auth_token = facade.subsystems.Utils.get_auth_token_object(self.user_manager.login('username',
            'initial_password')['auth_token'])
        self.user2 = self.user_manager.create(self.admin_token, 'otherusername', 'other_initial_password',
            'Mr.', 'Secundo', 'Duomo', '666.666.6666', 'user2@acme-u.com', 'active', {'name_suffix': 'Sr.'})
        self.user2_auth_token = facade.subsystems.Utils.get_auth_token_object(self.user_manager.login('otherusername',
            'other_initial_password')['auth_token'])
        self.region1 = self.region_manager.create(self.admin_token, 'Region 1')
        address_dict = {'label' : '123 Main St', 'locality' : 'Raleigh', 'region' : 'NC', 'postal_code' : '27615', 'country' : 'US'}
        self.venue1 = self.venue_manager.create(self.admin_token, 'Venue 1', '1253462', self.region1.id, {'address':address_dict})
        self.room1 = self.room_manager.create(self.admin_token, 'Room 1', self.venue1.id, 100)
        self.product_line1 = self.product_line_manager.create(self.admin_token, 'Product Line 1')
        self.right_now = datetime.utcnow().replace(microsecond=0, tzinfo=pr_time.UTC())
        self.one_day = timedelta(days=1)
        self.organization1 = self.organization_manager.create(self.admin_token, 'Organization 1')
        # Modify the celery configuration to run tasks eagerly for unit tests.
        self._always_eager = conf.ALWAYS_EAGER
        conf.ALWAYS_EAGER = True

    def tearDown(self):
        conf.ALWAYS_EAGER = self._always_eager
        # Restore all configuration settings to their previous values.
        map(lambda x: setattr(settings, x[0], x[1]), self._settings.iteritems())

    # XXX: should eventually go into mixins.py
    def create_instructor(self, title='Ms.', first_name='Teaching', last_name='Instructor', label='1234 Test Address Lane', locality='Testville',
            region='NC', postal_code='12345', country='US', phone='378-478-3845'):
        username = self.user_manager.generate_username('', first_name, last_name)
        email = username+'@electronsweatshop.com'
        shipping_address = {'label' : label, 'locality' : locality, 'postal_code' : postal_code, 'country' : country, 'region' : region}
        billing_address = shipping_address
        instructor_group_id = self.group_manager.get_filtered(self.admin_token, {'exact' : {'name' : 'Instructors'}})[0]['id']
        instructor = self.user_manager.create(self.admin_token, username, 'password', title, first_name, last_name, phone, email, 'active',
            {'name_suffix' : 'II', 'shipping_address' : shipping_address, 'billing_address' : billing_address, 'groups' : [instructor_group_id]})
        instructor_at = facade.models.AuthToken.objects.get(session_id__exact=self.user_manager.login(username, 'password')['auth_token'])
        return instructor, instructor_at

    # XXX: should eventually go into mixins.py
    def create_student(self, group='Students', title='Private', first_name='Learning', last_name='Student', label='1234 Test Address Lane', locality='Testville',
            region='NC', postal_code='12345', country='US', phone='378-478-3845'):
        username = self.user_manager.generate_username('', first_name, last_name)
        email = username+'@electronsweatshop.com'
        shipping_address = {'label' : label, 'locality' : locality, 'postal_code' : postal_code, 'country' : country, 'region' : region}
        billing_address = shipping_address
        optional_attributes = {
            'name_suffix' : 'Jr.',
            'shipping_address' : shipping_address,
            'billing_address' : billing_address,
        }
        if group:
            student_group_id = self.group_manager.get_filtered(self.admin_token, {'exact' : {'name' : group}})[0]['id']
            optional_attributes['groups'] = [student_group_id]
        student = self.user_manager.create(self.admin_token, username, 'password', title, first_name, last_name, phone, email, 'active', optional_attributes)
        student_at = facade.models.AuthToken.objects.get(session_id__exact=self.user_manager.login(username, 'password')['auth_token'])
        return student, student_at

    def setup_managers(self):
        """
        Setup common managers for convenience in subclasses

        The instance members will have the same name as the manager but
        lowercase and underscored instead of CamelCase. The 'FooBarManager'
        will be foo_bar_manager.

        An additional 'admin_foo_bar_manager' manager will be provided which
        wraps the foo_bar manager with an admin token such that all operations
        are expected to succeed. This can be used to conveniently setup a test
        context without having to worry about getting the correct token to
        do so.
        """
        get_default_token = lambda: self.auth_token
        get_admin_token = lambda: self.admin_token
        nocamel = re.compile('(.)([A-Z])')
        for manager_name in facade.managers:
            manager_class = getattr(facade.managers, manager_name)
            member_name = nocamel.sub(r'\1_\2', manager_name).lower()
            manager = manager_class()
            if isinstance(manager, ObjectManager):
                default_manager = ManagerAuthTokenWrapper(manager, get_default_token)
                setattr(self, member_name, default_manager)
                admin_manager = ManagerAuthTokenWrapper(manager, get_admin_token)
                setattr(self, 'admin_%s' % member_name, admin_manager)
            else:
                setattr(self, member_name, manager)


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


class RoleTestCase(TestCase):
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
        # XXX: we may want to think about handling this automatically
        facade.subsystems.Authorizer()._load_acls()
        return role, acl
