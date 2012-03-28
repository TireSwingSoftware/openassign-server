"""
A library of mixins for common boilerplate operations that are performed as part
of a test routine.

All mixin classes can be implemented in any order or combination as long as the
implementing class is a subclass of pr_services.testlib.TestCase.

Note: You may not need to use the mixins directly as they are already
implemented within the test cases in the `common` suites.
"""

import uuid

try:
    import cPickle as pickle
except ImportError:
    import pickle

from datetime import datetime, timedelta
from functools import partial
from operator import attrgetter

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

import facade

facade.import_models(locals())

__all__= (
    'ExamTestMixin',
    'RoleTestMixin',
    'EventTestMixin',
    'ResourceTestMixin',
    'UserTestMixin'
)

class ExamTestMixin:
    def _create_exam(self, name=None, title=None, organization_id=None,
            opts=None, **kwargs):
        name = name or kwargs.pop('name')
        title = title or kwargs.pop('title')
        opts = opts or {}
        opts.update(kwargs)
        if not organization_id:
            organization_id = self.organization1.id
        return self.exam_manager.create(self.admin_token, name, title,
                organization_id, opts)

    def _create_question_pool(self, exam=None, title=None, opts=None, **kwargs):
        exam = exam or kwargs.pop('exam')
        exam = getattr(exam, 'pk', exam)
        title = title or kwargs.pop('title')
        opts = opts or {}
        opts.update(kwargs)
        return self.question_pool_manager.create(self.admin_token, exam, title,
                                                 opts)

    def _create_question(self, question_pool=None, question_type=None,
                         label=None, opts=None, **kwargs):
        question_pool = question_pool or kwargs.pop('question_pool')
        question_pool = getattr(question_pool, 'pk', question_pool)
        question_type = question_type or kwargs.pop('question_type')
        label = label or kwargs.pop('label')
        opts = opts or {}
        opts.update(kwargs)
        return self.question_manager.create(self.admin_token, question_pool,
                                            question_type, label, opts)

    def _create_answer(self, question=None, label=None, opts=None, **kwargs):
        question = question or kwargs.pop('question')
        question = getattr(question, 'pk', question)
        label = label or kwargs.pop('label', None)
        opts = opts or {}
        opts.update(kwargs)
        return self.answer_manager.create(self.admin_token, question, label,
                                          opts)


class RoleTestMixin:
    def create_role(self, privs=None, check_methods=None,
            arbitrary_perms=None, name=None):
        create_role = Role.objects.create
        create_acl = ACL.objects.create
        create_method_call = ACMethodCall.objects.create
        methods = ACCheckMethod.objects

        if not privs:
            privs = {}
        for actee_type, crud in privs.iteritems():
            if hasattr(facade.models, actee_type):
                crud.setdefault('c', False)
                crud.setdefault('r', set())
                crud.setdefault('u', set())
                crud.setdefault('d', False)

        if not name:
            name = 'Test Role %s' % uuid.uuid4()
        role = create_role(name=name)
        acl = create_acl(role=role, acl=pickle.dumps(privs))
        if arbitrary_perms:
            acl.arbitrary_perm_list = pickle.dumps(arbitrary_perms)
        if not check_methods:
            check_methods = (('auth.actor_is_anybody', None),)
        self.addCleanup(self.delete_role, role)
        for name, params in check_methods:
            try:
                method = methods.get(name=name)
            except ObjectDoesNotExist:
                method = methods.create(name=name, title=name)
                self.addCleanup(method.delete)
            method_call = create_method_call(acl=acl,
                    ac_check_method=method,
                    ac_check_parameters=pickle.dumps(params or {}))
            method_call.save()
            self.addCleanup(method_call.delete)
        acl.save()
        self.authorizer.flush()
        return role, acl

    def delete_role(self, role):
        ACMethodCall.objects.filter(acl__role__id=role.id).delete()
        ACL.objects.filter(role__id=role.id).delete()
        Role.objects.filter(id=role.id).delete()
        self.authorizer.flush()



class EventTestMixin:
    def _create_event(self, start=None, end=None, org=None,
            optional_attributes={}, as_admin=True):
        """as_admin should be true when not explicitly testing event creation"""
        if as_admin:
            create_event = self.admin_event_manager.create
        else:
            create_event = self.event_manager.create

        if not start:
            start = self.right_now
        if not end:
            end = start + self.one_day
        if not org:
            org = self.organization1

        if isinstance(start, datetime):
            start = start.date()
        if isinstance(end, datetime):
            end = end.date()

        event_dict = {
            'title': 'Some Event',
            'description': 'An Event',
            'start': start,
            'end': end,
        }
        event = create_event(name_prefix='Foo', organization=org.id,
                optional_attributes=optional_attributes, **event_dict)
        event_dict.update({'organization': org})
        return event, event_dict

    def _create_session(self, event, start=None, end=None,
            resource=None, resource_type=None, as_admin=False):
        if as_admin:
            create_session = self.admin_session_manager.create
        else:
            create_session = self.session_manager.create

        if not start:
            start = self.right_now
        if not end:
            end = start + timedelta(hours=1)

        session_dict = {
            'start': start,
            'end': end,
            'status': 'active',
            'confirmed': True,
            'default_price': 123,
            'shortname': 'Short Name',
            'fullname': 'Full Name',
        }
        session = create_session(event=event.id, **session_dict)
        if resource:
            if as_admin:
                add_res = self.admin_session_resource_type_requirement_manager.create
            else:
                add_res = self.session_resource_type_requirement_manager.create

            add_res(session.id, resource_type.id, 0, 1, [resource.id])

        session_dict.update({'event': event.id})
        return session, session_dict

    def _create_sessions_with_schedule(self, event, schedule=None,
            resource=None, resource_type=None, as_admin=True):

        if not schedule:
        # set the session starts relative to the event start
        # build a venue schedule with sessions spread out lasting an hour each
            from datetime import time
            start = datetime.combine(event.start, time())
            start = timezone.make_aware(start, timezone.utc)
            schedule = [(start + timedelta(hours=i), start + timedelta(hours=i+1))
                            for i in range(1, 8, 3)]

        # create the sessions
        create_session = partial(self._create_session, event,
                resource=resource, resource_type=resource_type, as_admin=True)

        sessions = [create_session(start, end) for start, end in schedule]

        return sessions, schedule


class ResourceTestMixin:
    def _create_resource(self, name, optional_attributes=None, as_admin=True):
        if as_admin:
            create_resource = self.admin_resource_manager.create
            create_resource_type = self.admin_resource_type_manager.create
        else:
            create_resource = self.resource_manager.create
            create_resource_type = self.resource_type_manager.create

        res = create_resource(name, optional_attributes)
        res_type = create_resource_type(name, {'resources': {'add': [res.id]}})
        return res, res_type


class UserTestMixin:
    USER_COMPARE_KEYS = frozenset(('title', 'first_name', 'last_name', 'phone',
                                   'email', 'status', 'name_suffix', 'url',
                                   'alleged_organization'))

    def user_as_dict(self, user):
        user_dict = dict.fromkeys(self.USER_COMPARE_KEYS)
        for key in user_dict:
            user_dict[key] = getattr(user, key)
        return user_dict

    def create_user(self, save=True, compare=False, create_update_dict={},
            opt_dict={}, as_admin=False):
        num_users = getattr(self, '_num_test_users', 0)
        create_dict = {
            'username': 'MrUserNumber%d' % num_users,
            'initial_password': 'initial_password',
            'title': 'Mr.',
            'first_name': 'first_name',
            'last_name': 'last_name',
            'phone': '555.555.5555',
            'email': 'user-number-%d@foo-bar.org' % num_users,
            'status': 'pending'
        }
        create_dict.update(create_update_dict)
        setattr(self, '_num_test_users', num_users + 1)

        if as_admin:
            create_user = partial(self.admin_user_manager.create,
                optional_attributes=opt_dict, **create_dict)
        else:
            create_user = partial(self.user_manager.create,
                optional_attributes=opt_dict, **create_dict)

        if compare:
            compare_dict = dict.fromkeys(self.USER_COMPARE_KEYS)
            for key in compare_dict:
                if key in create_dict:
                    compare_dict[key] = create_dict[key]
                elif key in opt_dict:
                    compare_dict[key] = opt_dict[key]
            if save:
                user = create_user()
                return (user, create_dict, compare_dict)
            else:
                return create_dict, compare_dict
        elif save:
            user = create_user()
            return (user, create_dict)
        else:
            return create_dict

    def create_users(self, n=5, create_update_dict={}, opt_dict={},
            compare=True, as_admin=False):
        create_dicts, compare_dicts, usernames = [], [], []
        for i in range(n):
            create_dict, compare_dict = self.create_user(save=False,
                    compare=True, create_update_dict=create_update_dict,
                    opt_dict=opt_dict, as_admin=as_admin)
            create_dicts.append(create_dict)
            compare_dicts.append(compare_dict)
            usernames.append(create_dict['username'])

        if as_admin:
            self.admin_user_manager.batch_create(create_dicts)
        else:
            self.user_manager.batch_create(create_dicts)

        DomainAffiliation = facade.models.DomainAffiliation
        affiliations = DomainAffiliation.objects.filter(
                username__in=usernames).select_related('user')
        users = map(attrgetter('user'), affiliations.order_by('username'))
        if compare:
            return users, compare_dicts
        else:
            return users

