
try:
    import cPickle as pickle
except ImportError:
    import pickle

from functools import partial
from datetime import timedelta
from mock import Mock, patch

from django.db import models
from django.utils import timezone

from pr_services.exceptions import PermissionDeniedException
from pr_services.object_manager import ObjectManager
from pr_services.pr_models import PRModel
from pr_services.rpc.service import service_method, public_service_method
from pr_services.testlib import mixins, TestCase, GeneralTestCase, BasicTestCase

import facade
facade.import_models(locals(), globals())

RIGHT_NOW = timezone.now()
ONE_DAY = timedelta(days=1)

class TestAuthorizer(GeneralTestCase, mixins.RoleTestMixin):

    def test_flush(self):
        user = User.objects.get(id=2)
        auth_token = self._get_auth_token('user1', 'password')
        func = partial(self.authorizer.check_delete_permissions, auth_token, user)
        with self.assertRaises(PermissionDeniedException):
            func()

        role, acl = self.create_role({'User': { 'd': True }})
        func()

        ACMethodCall.objects.filter(acl=acl).delete()
        self.authorizer.flush()
        with self.assertRaises(PermissionDeniedException):
            func()

    def test_authorizer_caching(self):
        student_id, student_at = self.user1, self.user1_auth_token
        # The admin should be allowed to create a group, but not a student
        the_group = self.group_manager.create('The group!')
        # By using the same authorizer to check the admin and the student on
        # the same object, we can ensure that the caching works as intended
        self.authorizer.check_create_permissions(self.admin_token, the_group)
        with self.assertRaises(PermissionDeniedException):
            self.authorizer.check_create_permissions(student_at, the_group)
        with self.assertRaises(PermissionDeniedException):
            self.group_manager.create(student_at, 'The other group!')

    def test_merge_acls(self):
        def get_admin_acl():
            admin_role = Role.objects.get(name='Admin')
            acl = admin_role.acls.all()[0]
            return acl, pickle.loads(str(acl.acl))
        acl, acl_dict = get_admin_acl()
        self.assertNotIn('annual_beer_consumption', acl_dict['User']['r'])
        self.assertNotIn('Beer', acl_dict)
        acl_updates = {
                        'User' : {
                            'r' : set(('annual_beer_consumption',)),
                        },
                        'Beer' : {
                            'c' : True,
                            'r' : set(('name', 'brewery', 'style', 'IBU',)),
                            'u' : set(),
                            'd' : False,
                        }
        }
        acl.merge_updates(acl_updates)
        acl, acl_dict = get_admin_acl()
        self.assertIn('annual_beer_consumption', acl_dict['User']['r'])
        self.assertIn('first_name', acl_dict['User']['r'])
        self.assertIn('Beer', acl_dict)
        self.assertIn('IBU', acl_dict['Beer']['r'])
        self.assertEquals(len(acl_dict['Beer']['u']), 0)
        self.assertTrue(acl_dict['Beer']['c'])


class TestAuthorizerSanity(BasicTestCase, mixins.RoleTestMixin):
    fixtures = BasicTestCase.fixtures + ['unprivileged_user']

    def test_change_group(self):
        user = User.objects.get(id=2)
        auth_token = self._get_auth_token('user1', 'password')
        admin_group = Group.objects.get(name="Super Administrators")
        user.groups.add(admin_group)
        self.authorizer.check_delete_permissions(auth_token, user)
        user.groups.remove(admin_group)
        with self.assertRaises(PermissionDeniedException):
            self.authorizer.check_delete_permissions(auth_token, user)

    def test_unauthorizable_type(self):
        bad_privs = {'FooBar': { 'c': True }}
        with self.assertRaises(TypeError):
            self.create_role(bad_privs)

    def test_inheritence(self):
        class A(PRModel):
            foo = models.CharField(max_length=255)
        class B(A):
            bar = models.IntegerField()

        a, b = A(), B()
        with patch.object(facade.models, 'A', A, create=True):
            privs = {'A': {
                'r': set(('foo', )),
                'u': set(('foo', )),
            }}
            role, acl = self.create_role(privs)
            self.authorizer.check_read_permissions(None, a, ('foo',))
            self.authorizer.check_update_permissions(None, a, ('foo', ))
            self.authorizer.check_read_permissions(None, b, ('foo',))
            self.authorizer.check_update_permissions(None, b, ('foo', ))
            self.delete_role(role)

        with patch.object(facade.models, 'B', B, create=True):
            privs = {'B': {
                'r': set(('foo', 'bar')),
                'u': set(('foo', 'bar'))
            }}
            self.create_role(privs)
            self.authorizer.check_read_permissions(None, b, ('foo', 'bar'))
            self.authorizer.check_update_permissions(None, b, ('foo', 'bar'))


class TestAuthorizerChecks(BasicTestCase, mixins.RoleTestMixin):

    def setUp(self):
        super(TestAuthorizerChecks, self).setUp()
        self.user = User.objects.get(id=1)
        self.func = partial(self.authorizer.check_delete_permissions,
                actee=self.user, auth_token=None)

    def test_guests_allowed(self):
        # these are wrapped because we need real python functions
        allowed_mock = Mock(return_value=True)
        def allowed(actee, *args, **kwargs):
            return allowed_mock()

        allowed2_mock = Mock(return_value=True)
        def allowed2(auth_token=None, *args, **kwargs):
            return allowed2_mock()

        # sanity check
        with self.assertRaises(PermissionDeniedException):
            self.func()

        patch_spec = dict(create=True, allowed=allowed, allowed2=allowed2)
        with patch.multiple('pr_services.authorizer.checks', **patch_spec):
            check_methods = (('allowed', None), ('allowed2', None))
            self.create_role({'User': {'d': True}}, check_methods)
            self.func()
            self.assertTrue(allowed_mock.called)
            self.assertTrue(allowed2_mock.called)

    def test_guest_not_allowed(self):
        # this is wrapped because we need a real python function
        not_allowed_mock = Mock()
        def not_allowed(auth_token, *args, **kwargs):
            return not_allowed_mock()

        # sanity check
        with self.assertRaises(PermissionDeniedException):
            self.func()

        patch_spec = dict(create=True, not_allowed=not_allowed)
        with patch.multiple('pr_services.authorizer.checks', **patch_spec):
            self.create_role({'User': {'d': True}}, (('not_allowed', None),))
            with self.assertRaises(PermissionDeniedException):
                self.func()
            self.assertFalse(not_allowed_mock.called)

    def test_actee_required(self):
        mock = Mock()
        def check_method(auth_token, actee, *args, **kwargs):
            return mock()

        check_arbitrary_permissions = self.authorizer.check_arbitrary_permissions
        patch_spec = dict(create=True, check_method=check_method)
        with patch.multiple('pr_services.authorizer.checks', **patch_spec):
            self.create_role(check_methods=(('check_method', None), ),
                    arbitrary_perms=['do_some_foo'])
            with self.assertRaises(PermissionDeniedException):
                check_arbitrary_permissions(self.auth_token, 'do_some_foo')
            self.assertFalse(mock.called)

    def test_actee_not_required(self):
        mock1 = Mock(return_value=True)
        def notrequired1(auth_token, actee=None, *args, **kwargs):
            return mock1()
        mock2 = Mock(return_value=True)
        def notrequired2(auth_token, *args, **kwargs):
            return mock2()

        func = partial(self.authorizer.check_arbitrary_permissions,
                auth_token=self.auth_token, permission='do_some_foo')
        patch_spec = dict(create=True, notrequired1=notrequired1,
                notrequired2=notrequired2)
        with patch.multiple('pr_services.authorizer.checks', **patch_spec):
            check_methods = (('notrequired1', None), ('notrequired2', None))
            self.create_role(check_methods=check_methods,
                    arbitrary_perms=['do_some_foo'])
            func()
            self.assertTrue(mock1.called)
            self.assertTrue(mock2.called)



class TestMethodCheck(BasicTestCase):
    class FakeManager(ObjectManager):
        @public_service_method
        def public_foo(self, arg=None):
            pass

        @service_method
        def service_foo(self, auth_token=None, arg=None):
            pass

        @service_method
        def service_bar(self, auth_token=None, arg=None):
            pass

    def setUp(self):
        super(TestMethodCheck, self).setUp()
        self.manager = self.FakeManager()
        self.manager.authorizer = self.authorizer
        setattr(facade.managers, 'FakeManager', self.FakeManager)

    def tearDown(self):
        delattr(facade.managers, 'FakeManager')
        super(TestMethodCheck, self).tearDown()


class TestMethodCheckSemantics(TestMethodCheck):
    def test_bad_args(self):
        test_args = [
            (TypeError, ()), # no args
            (TypeError, (None, None)), # no manager
            (TypeError, (None, None, None)), # no method
            (TypeError, (None, self.manager, object())), # not callable
            (TypeError, (None, self.user_manager, 'login')), # is public
            (TypeError, (None, object(), 'foo')), # not instance of ObjectManager
            (AttributeError, (None, self.manager, 'authorizer')), # not servicemethod
            (AttributeError, (None, 'NonExistentManager', 'foo')),
            (AttributeError, (None, 'FakeManager', 'nonexistent_method')),
        ]
        for exc_type, args in test_args:
            with self.assertRaises(exc_type):
                self.authorizer.check_method_call(*args)

    def test_good_args(self):
        auth_token = self.auth_token
        test_args = [
            (None, 'FakeManager', 'service_foo'),
            (auth_token, 'FakeManager', 'service_foo'),
            (auth_token, self.manager, 'service_foo', (1,2,3), {'bar': True}),
            (auth_token, self.manager, self.manager.service_foo),
        ]
        for args in test_args:
            result = facade.subsystems.Authorizer.check_method_call(*args)
            assert result is None

class TestMethodCheckPermissions(TestMethodCheck, mixins.RoleTestMixin):

    def setUp(self):
        super(TestMethodCheckPermissions, self).setUp()
        self.check_method_call = Mock(wraps=self.authorizer.check_method_call)
        self.authorizer.check_method_call = self.check_method_call

    def test_service_method(self):
        assert not self.check_method_call.called
        args = ('Foo',)
        self.manager.service_foo(self.auth_token, *args)
        self.check_method_call.assert_called_once_with(
                auth_token=self.auth_token,
                manager=self.manager,
                method=self.manager.service_foo,
                call_args=args, call_kwargs={})

    def test_public_method_not_checked(self):
        self.manager.public_foo()
        assert not self.check_method_call.called

    def test_check_acl(self):
        # these are wrapped because we need real python functions
        foo_mock = Mock(return_value=False)
        def foo_check(auth_token=None, *args, **kwargs):
            return foo_mock()

        bar_mock = Mock(return_value=False)
        def bar_check(auth_token=None, *args, **kwargs):
            return bar_mock()

        spec = dict(create=True, foo_check=foo_check, bar_check=bar_check)
        with patch.multiple('pr_services.authorizer.checks', **spec):
            self.create_role({
                'FakeManager': {
                    'methods': set(('service_foo', ))
                }
            }, (('foo_check', None), ('bar_check', None)))

            self.assertFalse(self.check_method_call.called)

            with self.assertRaises(PermissionDeniedException):
                # both check methods return false
                self.manager.service_foo()

            self.assertTrue(foo_mock.called)
            self.assertFalse(bar_mock.called)
            self.assertEquals(self.check_method_call.call_count, 1)
            self.authorizer.flush()

            foo_mock.return_value = True
            with self.assertRaises(PermissionDeniedException):
                # one check method returns false
                self.manager.service_foo()

            self.assertTrue(foo_mock.called)
            self.assertTrue(bar_mock.called)
            self.assertEquals(self.check_method_call.call_count, 2)
            self.authorizer.flush()

            bar_mock.return_value = True
            self.manager.service_foo()
            self.assertTrue(foo_mock.called)
            self.assertTrue(bar_mock.called)
            self.assertEquals(self.check_method_call.call_count, 3)
            self.authorizer.flush()


class TestOrgRoleChecks(TestCase):

    fixtures = [
        'barebones_orgrole'
    ]

    CHECKS = 'pr_services.authorizer.checks.membership.orgrole.ORGROLE_CHECKS'

    def setUp(self):
        super(TestOrgRoleChecks, self).setUp()
        self.user = User.objects.get(id=2)
        self.org = Organization.objects.get(name='Foo')
        self.auth_token = self._get_auth_token('user1')

    def test_assignment(self):
        task = Task.objects.create(organization=self.org, name='Foo')
        assignment = Assignment.objects.create(user=self.user, task=task)

        check = Mock(return_value=True)
        with patch.dict(self.CHECKS, Assignment=[check]):
            self.authorizer.check_create_permissions(self.auth_token, assignment)
        assert check.called

    def test_exam(self):
        exam = Exam.objects.create(organization=self.org, name='Foo')

        check = Mock(return_value=True)
        with patch.dict(self.CHECKS, Exam=[check]):
            self.authorizer.check_create_permissions(self.auth_token, exam)
        assert check.called

    def test_enrollment(self):
        curr = Curriculum.objects.create(name='Foo', organization=self.org)
        enroll = CurriculumEnrollment.objects.create(curriculum=curr,
                start=RIGHT_NOW, end=RIGHT_NOW + ONE_DAY)

        check = Mock(return_value=True)
        with patch.dict(self.CHECKS, CurriculumEnrollment=[check]):
            self.authorizer.check_create_permissions(self.auth_token, enroll)
        assert check.called

    def test_session(self):
        event = Event.objects.create(start=RIGHT_NOW, end=RIGHT_NOW + ONE_DAY,
                name='Foo Event', organization=self.org)
        sess = Session.objects.create(start=RIGHT_NOW, end=RIGHT_NOW + ONE_DAY,
                title='Foo', shortname='Foo', event=event, default_price=100)

        check = Mock(return_value=True)
        with patch.dict(self.CHECKS, Session=[check]):
            self.authorizer.check_create_permissions(self.auth_token, sess)
        assert check.called


    def test_event(self):
        event = Event.objects.create(start=RIGHT_NOW, end=RIGHT_NOW + ONE_DAY,
                name='Foo Event', organization=self.org)

        check = Mock(return_value=True)
        with patch.dict(self.CHECKS, Event=[check]):
            self.authorizer.check_create_permissions(self.auth_token, event)
        assert check.called

    def test_user(self):
        user = User.objects.create(title='Mr.', first_name='John',
                last_name='Doe', email='john@doe.com')

        check = Mock(return_value=True)
        with patch.dict(self.CHECKS, User=[check]):
            self.authorizer.check_create_permissions(self.auth_token, user)
        assert check.called

    def test_userorgrole(self):
        uorgrole = UserOrgRole.objects.create(owner=self.user,
                organization=self.org,
                role=OrgRole.objects.create(name='Foo Role'))

        check = Mock(return_value=True)
        with patch.dict(self.CHECKS, UserOrgRole=[check]):
            self.authorizer.check_create_permissions(self.auth_token, uorgrole)
        assert check.called
