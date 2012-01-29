# -*- coding: utf-8 -*-
"""
non-RPC unit tests for Power Reg
"""

from __future__ import with_statement

import cPickle
import cStringIO
import hashlib
import inspect
import operator
import os
import time
import urllib2

from datetime import datetime, date, timedelta
from functools import partial
from operator import attrgetter, itemgetter

import django.test.client
import django.utils.dateformat
import django.utils.unittest

from django.conf import settings
from django.core import mail
from django.core.urlresolvers import reverse
from django.utils import simplejson as json
from django.utils.unittest import skipIf, skipUnless

from cookiecache import CookieCache
from initial_setup import InitialSetupMachine, default_read_fields
from pr_services import exceptions
from pr_services import pr_time
from pr_services.gettersetter import Getter, Setter
from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import (service_method, wrap_service_method,
        RpcService, create_rpc_service)
from pr_services.testlib import (GeneralTestCase, RoleTestCase, BasicTestCase,
        TestCase)
from pr_services.testlib import mixins
from pr_services.testlib.helpers import expectPermissionDenied, load_fixtures
from pr_services.utils import UnicodeCsvWriter

import facade


# import all models into our namespace
facade.import_models(locals(), globals())

##############################################################################
#
# Let the unit tests begin!
#
##############################################################################

class TestAuthorizer(GeneralTestCase):
    def test_authorizer_caching(self):
        student_id, student_at = self.user1, self.user1_auth_token
        # The admin should be allowed to create a group, but not a student
        the_group = self.group_manager.create('The group!')
        authorizer = facade.subsystems.Authorizer()
        # By using the same authorizer to check the admin and the student on the same object, we can ensure that the caching works as intended
        authorizer.check_create_permissions(self.admin_token, the_group)
        self.assertRaises(exceptions.PermissionDeniedException, authorizer.check_create_permissions, student_at, the_group)
        self.assertRaises(exceptions.PermissionDeniedException, self.group_manager.create, student_at, 'The other group!')

    def test_merge_acls(self):
        def get_admin_acl():
            admin_role = Role.objects.get(name='Admin')
            acl = admin_role.acls.all()[0]
            return acl, cPickle.loads(str(acl.acl))
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

class TestAuthToken(GeneralTestCase):
    def test_user_related_name(self):
        da = DomainAffiliation.objects.get(username='admin', domain__name='local')
        self.assertEquals(len(da.auth_tokens.all()), 1)
        self.assertEquals(da.auth_tokens.all()[0].id, self.admin_token.id)
        new_admin_token = AuthToken.objects.get(session_id=self.user_manager.login('admin', 'admin')['auth_token'])
        self.assertEquals(len(da.auth_tokens.all()), 2)

        admin_users_auth_tokens = da.auth_tokens.values_list('session_id', flat=True)
        self.assertTrue(self.admin_token.session_id in admin_users_auth_tokens)
        self.assertTrue(new_admin_token.session_id in admin_users_auth_tokens)

    def test_caching(self):
        auth_token = self.user1_auth_token
        ret = AuthToken.objects.get(session_id=auth_token.session_id)
        self.assertEquals(auth_token.id, ret.id)
        self.assertEquals(auth_token.session_id, ret.session_id)
        # by now it should be cached, so let's try again
        ret = AuthToken.objects.get(session_id=auth_token.session_id)
        self.assertEquals(auth_token.id, ret.id)
        self.assertEquals(auth_token.session_id, ret.session_id)
        # relogin is a special case, since it changes the session_id (which is
        # used to generate the cache key). Thus, we need to confirm that the old
        # token under its old cache key gets purged from the cache.
        old_session_id = auth_token.session_id
        new_session_id = self.user_manager.relogin(auth_token)['auth_token']
        self.assertRaises(AuthToken.DoesNotExist, AuthToken.objects.get, session_id=old_session_id)

class TestBackendInfo(TestCase):
    def test_backend_info(self):
        tz = self.backend_info.get_time_zone()
        self.assertEquals(tz, settings.TIME_ZONE)
        ts = self.backend_info.get_current_timestamp()
        from pr_services.iso8601 import parse
        t1 = parse(ts)
        t2 = time.mktime(datetime.now().timetuple())
        self.assertTrue((t2 - t1) < 10.0)
        rev = self.backend_info.get_revision()
        self.assertTrue(rev)

class TestBlameManager(GeneralTestCase):
    def test_create(self):
        b = facade.managers.BlameManager().create(self.user1_auth_token)
        self.assertEquals(b.user, self.user1)

class TestCookiecache(GeneralTestCase):
    def setUp(self):
        super(TestCookiecache, self).setUp()

        self.user_manager.create('test_user', 'password', 'Mr.', 'Memcache', 'Test', '', 'memcache@tester.email', 'active')
        self.user1_auth_token = facade.subsystems.Utils.get_auth_token_object(self.user_manager.login('test_user', 'password')['auth_token'])

    def test_all(self):
        # Fire it up
        mc = CookieCache(self.user1_auth_token)

        # Make sure no paths are defined yet...
        self.assertEquals(mc.paths, [])

        # Set/save some paths
        mc.paths.append('/path1')
        # Add an extra path that should get stripped off in forced uniqueness
        mc.paths.append('/path2')
        mc.paths.append('/path2')
        mc.save()

        # Blow away our mc object, the recreate it to make sure the paths got stored properly
        del(mc)
        mc = CookieCache(self.user1_auth_token)
        # Check against a sorted list...the uniqueness check may change order
        self.assertEquals(sorted(mc.paths), ['/path1', '/path2'])

        # Remove our memcache entry
        mc.delete()

        # Resync, which should create a new entry, so check for empty paths list
        mc.update()
        self.assertEquals(mc.paths, [])

        # Clean up
        mc.delete()

    def test_cookiecache_view(self):
        CachedCookie.objects.create(key='foo', value='line 1\r\nline 2\r\n')
        response = self.client.get('/cookiecache/foo/')
        self.assertEquals(response.content, 'line 1\r\nline 2\r\n')
        self.assertEquals(response._headers['content-type'][1], 'text/plain')
        response = self.client.get('/cookiecache/bar/')
        self.assertEquals(response.content, '')

class TestTask(TestCase):
    def test_generate_name(self):
        # Test generating the name automatically from the title if present,
        # otherwise using the content type and primary key.  Verify that the
        # name isn't automatically generated if explicitly set.
        task = Task.objects.create(title='Foo Task')
        self.assertEqual(task.name, 'foo_task')
        task2 = Task.objects.create()
        self.assertEqual(task2.name, 'task_%d' % task2.pk)
        task3 = Task.objects.create(name='my_task')
        self.assertEqual(task3.name, 'my_task')
        exam = Exam.objects.create(title='Foo Exam')
        self.assertEqual(exam.name, 'foo_exam')
        exam2 = Exam.objects.create()
        self.assertEqual(exam2.name, 'exam_%d' % exam2.pk)
        exam3 = Exam.objects.create(name='my_exam')
        self.assertEqual(exam3.name, 'my_exam')


class TestAssignment(GeneralTestCase):
    def test_create_multiple_types(self):
        self.assertEquals(Assignment.objects.filter(user=self.user1).count(), 0)
        tasks = []
        # Append some Exams to our task list
        tasks.append(self.exam_manager.create('Exam 1', 'description'))
        tasks.append(self.exam_manager.create('Exam 2', 'description'))
        # We have to upload a scorm zip file to make a SCO.
        scorm_zip_file_name = os.path.join(os.path.dirname(__file__), '..',
            'test_services', 'ConstantCon1.zip')
        with open(scorm_zip_file_name, 'rb') as scorm_zip_file:
            self.sco_manager._process_scorm_file(self.admin_token, scorm_zip_file)
        sco_id = self.sco_manager.get_filtered({}, ['url'])[0]['id']
        # Append the SCO to our task list
        tasks.append(Sco.objects.get(pk=sco_id))

        for task in tasks:
            ret = self.assignment_manager.create(task.id, self.user1.id)
            self.assertTrue(ret)
            ret = self.assignment_attempt_manager._create(self.admin_token, ret)
            self.assertTrue(ret)

        self.assertEquals(Assignment.objects.filter(user=self.user1).count(), 3)
        self.assertEquals(AssignmentAttempt.objects.filter(assignment__user=self.user1).count(), 3)

    # make sure status changes from 'pending' to 'assigned' when minimum enrollment numbers are met
    def test_session_status_change(self):
        learner1, learner2, learner3 = self.user1, self.user2, self.user3
        self.e1 = self.event_manager.create('Event 1', 'Event 1', 'Event 1', self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), self.organization1.id, {'venue' : self.venue1.id})
        session1 = self.session_manager.create(self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), 'pending', True, 10000, self.e1.id, 'Short Name 1', 'Long Name 1')
        student_role = SessionUserRole.objects.get(name__exact='Student')
        role_req1 = self.session_user_role_requirement_manager.create(str(session1.id), str(student_role.id), 2, 3, None, {'prevent_duplicate_assignments' : True})

        session = self.session_manager.get_filtered({'exact': {'id': session1.id}}, ['status'])
        self.assertEquals(session[0]['status'], 'pending')
        self.assignment_manager.bulk_create(role_req1.id, [learner1.id])
        session = self.session_manager.get_filtered({'exact': {'id': session1.id}}, ['status'])
        self.assertEquals(session[0]['status'], 'pending')
        self.assignment_manager.bulk_create(role_req1.id, [learner2.id, learner3.id])
        session = self.session_manager.get_filtered({'exact': {'id': session1.id}}, ['status'])
        self.assertEquals(session[0]['status'], 'active')

    def test_assignment_related_dates(self):
        right_now = datetime.utcnow().replace(microsecond = 0, tzinfo = pr_time.UTC())
        learner1, l1_token = self.user1, self.user1_auth_token
        exam1 = self.exam_manager.create('Exam 1')
        exam2 = self.exam_manager.create('Exam 2')
        curriculum = self.curriculum_manager.create('Curriculum 1')
        self.curriculum_task_association_manager.create(curriculum.id, exam1.id, {'days_before_start' : 2, 'days_to_complete' : 3})
        self.curriculum_task_association_manager.create(curriculum.id, exam2.id, {'days_before_start' : 0, 'days_to_complete' : 3})
        self.curriculum_enrollment_manager.create(curriculum.id, right_now.isoformat(), (right_now + timedelta(days=10)).isoformat(), [learner1.id])
        assignment1 = self.assignment_manager.get_filtered(l1_token, {'exact' : {'user' : learner1.id, 'task' : exam1.id}}, ['id'])[0]['id']
        assignment2 = self.assignment_manager.get_filtered(l1_token, {'exact' : {'user' : learner1.id, 'task' : exam2.id}}, ['id'])[0]['id']
        # cannot attempt this Assignment yet because of the "days_before_start"
        # specification above
        self.assertRaises(exceptions.PermissionDeniedException, self.exam_session_manager.create, l1_token, assignment1)
        # but this one should work
        self.exam_session_manager.create(l1_token, assignment2)

    def test_assign_sessions(self):
        learner1, learner2 = self.user1, self.user2
        learner3, learner4 = self.user3, self.user4
        learner5 = self.user_manager.create('learner_5', 'password', '', '', '', '', '', 'active')
        learner6 = self.user_manager.create('learner_6', 'password', '', '', '', '', '', 'active')
        learner7 = self.user_manager.create('learner_7', 'password', '', '', '', '', '', 'active')
        learner8 = self.user_manager.create('learner_8', 'password', '', '', '', '', '', 'active')
        l1_token = self.user1_auth_token
        self.e1 = self.event_manager.create('Event 1', 'Event 1', 'Event 1', self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), self.organization1.id, {'venue' : self.venue1.id})
        session1 = self.session_manager.create(self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), 'active', True, 10000, self.e1.id, 'Short Name 1', 'Full Name 1')
        student_role = SessionUserRole.objects.get(name__exact='Student')
        role_req1 = self.session_user_role_requirement_manager.create(str(session1.id), str(student_role.id), 1, 3, None, {'prevent_duplicate_assignments' : True})
        # This overlaps intentionally to test room capacity limits below
        session2 = self.session_manager.create(self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), 'active', True, 10000, self.e1.id, 'Short Name 1', 'Full Name 1')
        role_req2 = self.session_user_role_requirement_manager.create(str(session2.id), str(student_role.id), 1, 3)
        tf1 = self.task_fee_manager.create('TF001', 'slick deal', 'a really great deal', 200, 0, role_req1.id, {'starting_quantity' : 10})
        assignments = self.assignment_manager.bulk_create(role_req1.id, [learner1.id, learner2.id, learner3.id])
        assignment_ids = [assignment['id'] for assignment in assignments.values()]
        self.assertEquals(len(assignments), 3)
        for key in assignments:
            self.assertEquals(assignments[key]['status'], 'unpaid')
        po1 = self.purchase_order_manager.create(l1_token)
        pc1 = self.product_claim_manager.create(l1_token, tf1.id, po1.id, 8)
        p = Payment(amount=4000, purchase_order=po1, sales_tax=0)
        p.save()
        self.assertRaises(exceptions.NotPaidException, self.product_claim_manager.choose_assignments, pc1.id, xrange(15))
        self.product_claim_manager.choose_assignments(pc1.id, assignment_ids)

        # now that they are paid up, make sure capacity checks work
        assignments = self.assignment_manager.bulk_create(role_req1.id, [learner4.id])
        self.assertEquals(len(assignments), 1)
        self.assertEquals(assignments[learner4.id]['status'], 'wait-listed')
        learner4_assignment = assignments[learner4.id]

        assignments = self.assignment_manager.get_filtered({'member' : {'id' : assignment_ids}}, ['status'])
        self.assertEquals(len(assignments), 3)
        for assignment in assignments:
            self.assertEquals(assignment['status'], 'assigned')

        # make sure we prevent duplicate assignments when the task is set to do so
        assignments = self.assignment_manager.bulk_create(role_req1.id, [learner4.id])
        self.assertEquals(len(assignments), 1)
        self.assertEquals(assignments[learner4.id]['status'], 'error')
        self.assertEquals(assignments[learner4.id]['error_code'], exceptions.DuplicateAssignmentException.error_code)
        self.assertEquals(Assignment.objects.filter(task__id=role_req1.id, user__id=learner4.id).count(), 1)

        # Now let's verify room capacity restrictions
        self.assignment_manager.update(learner4_assignment['id'], {'status' : 'assigned'})
        self.session_user_role_requirement_manager.update(role_req1.id, {'max' : 100})
        self.session_manager.update(session1.id, {'room' : self.room1.id})
        self.session_manager.update(session2.id, {'room' : self.room1.id})
        self.room_manager.update(self.room1.id, {'capacity' : 5})
        assignments = self.assignment_manager.bulk_create(role_req1.id, [learner5.id])
        self.assertEquals(len(assignments), 1)
        self.assertEquals(assignments[learner5.id]['status'], 'unpaid')
        self.product_claim_manager.choose_assignments(pc1.id, [assignments[learner5.id]['id']])
        assignments = self.assignment_manager.bulk_create(role_req1.id, [learner6.id])
        self.assertEquals(len(assignments), 1)
        self.assertEquals(assignments[learner6.id]['status'], 'wait-listed')


        self.room_manager.update(self.room1.id, {'capacity' : 6})
        # Now we have assignments for two SURRs in the same room at the same time- can we handle it?
        assignments = self.assignment_manager.bulk_create(role_req2.id, [learner7.id])
        self.assertEquals(len(assignments), 1)
        self.assertEquals(assignments[learner7.id]['status'], 'assigned')

        # Can we ignore room capacity?
        self.session_user_role_requirement_manager.update(role_req2.id, {'ignore_room_capacity' : True})
        assignments = self.assignment_manager.bulk_create(role_req2.id, [learner8.id])
        self.assertEquals(len(assignments), 1)
        self.assertEquals(assignments[learner8.id]['status'], 'assigned')


class TestAssignmentManagerViews(BasicTestCase):

    fixtures = BasicTestCase.fixtures + ['exams_and_achievements']

    def setUp(self):
        super(TestAssignmentManagerViews, self).setUp()

        self.user = User.objects.get(id=2)
        self.exams = Exam.objects.all()
        self.assignments = Assignment.objects.all()
        self.manager = self.assignment_manager

        # default auth token to regular user
        self.auth_token = self._get_auth_token('user1')

    def test_exam_view(self):
        view = partial(self.manager.exam_view, user_id=self.user.id)
        assignment = self.assignments[0]
        exam = self.exams[0]
        expected = {
            'id': assignment.id,
            'user': self.user.id,
            'status': assignment.status,
            'task': {
                'id': exam.id,
                'name': unicode(exam.name),
                'title': unicode(exam.title),
                'type': u'pr_services.exam',
                'description': unicode(exam.description),
            }
        }
        result = view()
        self.assertEquals(len(result), 5)
        self.assertDictEqual(result[0], expected)

    def test_detailed_exam_view(self):
        view = partial(self.manager.detailed_exam_view, user_id=self.user.id)
        assignment = self.assignments[0]
        exam = self.exams[0]
        expected = {
            'id': assignment.id,
            'user': {
                'id': self.user.id,
                'first_name': self.user.first_name,
                'last_name': self.user.last_name,
            },
            'status': u'assigned',
            'task': {
                'id': exam.id,
                'name': exam.name,
                'title': exam.title,
                'type': u'pr_services.exam',
                'description': exam.description,
                'passing_score': exam.passing_score,
            }
        }
        result = view()
        self.assertEquals(len(result), 5)
        self.assertDictEqual(result[0], expected)

        result = view(fields=['status', 'task'])
        self.assertEquals(len(result), 5)
        self.assertDictEqual(result[0], expected)

        result = view(filters={'exact': {'id': assignment.id}})
        self.assertEquals(len(result), 1)

    def test_transcript_view(self):
        view = partial(self.manager.transcript_view, user_id=self.user.id)
        def _datestring(d):
            return d.replace(tzinfo=pr_time.UTC()).isoformat()

        # start the first 8 assignments
        for a in self.assignments[:8]:
            a.date_started = (self.right_now - self.one_day)
            a.save()

        # mark the first five completed and build the expected transcript
        expected = []
        for exam, asn in zip(self.exams, self.assignments[:5]):
            asn.mark_completed()
            asn.save()
            awards = asn.achievement_awards.values_list('id', flat=True)
            expected.append({
                'id': asn.id,
                'user': self.user.id,
                'status': unicode(asn.status),
                'date_completed': _datestring(asn.date_completed),
                'date_started': _datestring(asn.date_started),
                'achievement_awards': sorted(awards),
                'task': {
                    'id': exam.id,
                    'description': unicode(exam.description),
                    'achievements': [{
                         'id': a.id,
                         'name': unicode(a.name),
                         'description': unicode(a.description)
                    } for a in exam.achievements.all()],
                    'title': unicode(exam.title),
                    'type': u'pr_services.exam',
                    'name': unicode(exam.name),
                    }
                })
        result = view()
        # check a few things first to make failing tests easier to read
        self.assertGreater(len(result), 0)
        self.assertIn('achievement_awards', result[0])
        # sort awards in the result so we don't need to rely on the order
        for row in result:
            row['achievement_awards'] = sorted(row['achievement_awards'])

        # sort both the test and expected transcript by id
        # since the assignment ordering does not matter
        _id = itemgetter('id')
        result = sorted(result, key=_id)
        expected = sorted(expected, key=_id)
        self.assertSequenceEqual(result, expected)



class TestAchievementAwardManager(GeneralTestCase):
    def test_CRUD(self):
        achievement = self.achievement_manager.create('Super Star', 'Award for people who are super stars')

        # create
        achievement_award = self.achievement_award_manager.create(achievement.id, self.user1.id)
        self.assertEqual(achievement_award.achievement, achievement)
        self.assertEqual(achievement_award.user, self.user1)

        # try to change the user
        self.achievement_award_manager.update(achievement_award.id, {'user' : self.user2.id})
        achievement_award = AchievementAward.objects.get(id=achievement_award.id)
        self.assertEqual(achievement_award.achievement, achievement)
        self.assertEqual(achievement_award.user, self.user2)

    @expectPermissionDenied
    def test_user_cannot_award_self(self):
        achievement = Achievement.objects.create(name='Super Star', description='Award for people who are super stars')

        self.achievement_award_manager.create(self.user1_auth_token, achievement.id, self.user1.id)

    def test_owner_can_read_achievement_award(self):
        achievement = Achievement.objects.create(name='Super Star', description='Award for people who are super stars')
        achievement_award = AchievementAward.objects.create(achievement=achievement, user=self.user1)

        # try to read the AchievementAward details
        achievement_award_fields = ['achievement', 'assignment','date', 'user']
        ret = self.achievement_award_manager.get_filtered(self.user1_auth_token, {'exact' : {'id' : achievement_award.id}}, achievement_award_fields)
        self.assertEqual(len(ret), 1)
        # add one for 'id'
        self.assertEqual(len(ret[0]), len(achievement_award_fields) + 1)
        self.assertEqual(ret[0]['user'], self.user1.id)
        self.assertEqual(ret[0]['achievement'], achievement.id)

        # try to read the Achievement details
        achievement_fields = ['description', 'name']
        ret = self.achievement_manager.get_filtered(self.user1_auth_token, {'exact' : {'id' : achievement.id}}, achievement_fields)
        self.assertEqual(len(ret), 1)
        # add one for 'id'
        self.assertEqual(len(ret[0]), len(achievement_fields) + 1)
        self.assertEqual(ret[0]['name'], achievement.name)
        self.assertEqual(ret[0]['description'], achievement.description)

    def test_nonowner_cannot_read_achievement_award(self):
        achievement = Achievement.objects.create(name='Super Star', description='Award for people who are super stars')
        achievement_award = AchievementAward.objects.create(achievement=achievement, user=self.user1)

        # try to read the AchievementAward details
        ret = self.achievement_award_manager.get_filtered(self.user2_auth_token, {'exact' : {'id' : achievement_award.id}}, [])
        self.assertEqual(len(ret), 0)

        # try to read the Achievement details
        ret = self.achievement_manager.get_filtered(self.user2_auth_token, {'exact' : {'id' : achievement.id}}, [])
        self.assertEqual(len(ret), 0)


class TestCredentialManager(GeneralTestCase):
    def test_create(self):
        uid = self.user_manager.create('rbarlow', 'topSecret', 'Mr.', 'Randy', 'Barlow',
                            '919-816-2352', 'rbarlow@americanri.com', 'active',
                            {'email2' : 'randy@electronsweatshop.com'})
        ctyp1 = self.credential_type_manager.create('B.S.', 'Electrical Engineering')
        ret = self.credential_manager.create(uid.id, ctyp1.id,
            {'serial_number' : '1234', 'authority' : 'North Carolina State Univerity',
             'date_granted' : '2008-06-23', 'date_expires' : '2008-06-27'})
        self.assertEquals(ret.credential_type.name, 'B.S.')
        self.assertEquals(ret.user.id, uid.id)
        self.assertEquals(ret.credential_type.description, 'Electrical Engineering')
        self.assertEquals(ret.authority, 'North Carolina State Univerity')
        self.assertEquals(ret.serial_number, '1234')

    def test_str(self):
        uid = self.user_manager.create('rbarlow', 'topSecret', 'Mr.', 'Randy', 'Barlow',
                            '919-816-2352', 'rbarlow@americanri.com', 'active',
                            {'email2' : 'randy@electronsweatshop.com'})
        ctyp1 = self.credential_type_manager.create('B.S.', 'Electrical Engineering')
        ret = self.credential_manager.create(uid.id, ctyp1.id,
            {'serial_number' : '1234', 'authority' : 'North Carolina State Univerity',
             'date_granted' : '2008-06-23', 'date_expires' : '2008-06-27'})
        self.assertEquals(ret.__str__(), 'Credential, id=%d'%(int(ret.id)))

    def test_update(self):
        uid = self.user_manager.create('rbarlow', 'topSecret', 'Mr.', 'Randy', 'Barlow',
                            '919-816-2352', 'rbarlow@americanri.com', 'active',
                            {'email2' : 'randy@electronsweatshop.com'})
        ctyp1 = self.credential_type_manager.create('B.S.', 'Electrical Engineering')
        ret = self.credential_manager.create(uid.id, ctyp1.id,
            {'serial_number' : '1234', 'authority' : 'North Carolina State Univerity'})
        self.credential_manager.update(ret.id, {'authority' : 'Stanford University'})
        ret = Credential.objects.get(id = ret.id)
        self.assertEquals(ret.authority, 'Stanford University')

    def test_delete(self):
        uid = self.user_manager.create('rbarlow', 'topSecret', 'Mr.', 'Randy', 'Barlow',
                            '919-816-2352', 'rbarlow@americanri.com', 'active',
                            {'email2' : 'randy@electronsweatshop.com'})
        ctyp1 = self.credential_type_manager.create('B.S.', 'Electrical Engineering')
        ret = self.credential_manager.create(uid.id, ctyp1.id,
            {'serial_number' : '1234', 'authority' : 'North Carolina State Univerity'})
        ret = Credential.objects.get(id = ret.id)
        self.credential_manager.delete(ret.id)
        self.assertRaises(exceptions.ObjectNotFoundException, self.credential_manager._find_by_id, ret.id)

    def test_grant_from_achievement(self):
        credential_type = self.credential_type_manager.create(
            'B.S.', 'Electrical Engineering')
        achievement = self.achievement_manager.create('Super Star', 'Award for people who are super stars')
        self.credential_type_manager.update(credential_type.id,
            {'required_achievements': [achievement.id]})
        exam = self.exam_manager.create('EE Exam', '', {'achievements' : [achievement.id]})

        # Create a student
        student, student_at = self.user1, self.user1_auth_token

        # Create an assignment, and mark it as completed
        assignment = self.assignment_manager.create(exam.id,
            student.id)
        ret = self.assignment_manager.get_filtered(
            {'exact': {'id': assignment.id}}, ['status'])
        self.assertEqual(ret[0]['status'], 'assigned')
        self.assignment_manager.update(assignment.id,
            {'status': 'completed'})
        ret = self.assignment_manager.get_filtered(
            {'exact': {'id': assignment.id}}, ['status'])
        self.assertEqual(ret[0]['status'], 'completed')
        ret = self.credential_manager.get_filtered(
            {'exact': {'user': student.id}}, ['status'])
        self.assertTrue(len(ret) > 0)
        self.assertEqual(ret[0]['status'], 'granted')

    def test_grant_from_pending_credential(self):
        credential_type = self.credential_type_manager.create(
            'B.S.', 'Electrical Engineering')
        achievement = self.achievement_manager.create('Super Star', 'Award for people who are super stars')
        self.credential_type_manager.update(credential_type.id,
            {'required_achievements': [achievement.id]})
        exam = self.exam_manager.create('EE Exam', '', {'achievements' : [achievement.id]})

        # Create a student with a pending credential.
        student, student_at = self.user1, self.user1_auth_token
        credential = self.credential_manager.create(student.id,
            credential_type.id, {'serial_number': '1234', 'authority': 'NCSU'})
        ret = self.credential_manager.get_filtered(
            {'exact': {'id': credential.id}}, ['status'])
        self.assertEqual(ret[0]['status'], 'pending')

        # Create an assignment, and mark it as completed
        assignment = self.assignment_manager.create(exam.id,
            student.id)
        ret = self.assignment_manager.get_filtered(
            {'exact': {'id': assignment.id}}, ['status'])
        self.assertEqual(ret[0]['status'], 'assigned')
        self.assignment_manager.update(assignment.id,
            {'status': 'completed'})
        ret = self.assignment_manager.get_filtered(
            {'exact': {'id': assignment.id}}, ['status'])
        self.assertEqual(ret[0]['status'], 'completed')
        ret = self.credential_manager.get_filtered(
            {'exact': {'user': student.id}}, ['status'])
        self.assertTrue(len(ret) > 0)
        self.assertEqual(ret[0]['status'], 'granted')
        self.assertEqual(ret[0]['id'], credential.id)

    def test_grant_from_two_assignments(self):
        # Create another new credential that may be earned on the completion of
        # both exams.
        credential_type = self.credential_type_manager.create(
            'B.S.', 'Computer Engineering')
        achievement1 = self.achievement_manager.create('Super Star', 'Award for people who are super stars')
        achievement2 = self.achievement_manager.create('Super Duper Star', 'Award for people who are super duper stars')
        exam1 = self.exam_manager.create('EE Exam', '', {'achievements' : [achievement1.id]})
        exam2 = self.exam_manager.create('CS Exam', '', {'achievements' : [achievement2.id]})
        self.credential_type_manager.update(credential_type.id,
            {'required_achievements': [achievement1.id, achievement2.id]})

        # Create a student with a pending credential.
        student = self.user1
        credential = self.credential_manager.create(student.id,
            credential_type.id, {'serial_number': '2345', 'authority': 'NCSU'})
        ret = self.credential_manager.get_filtered(
            {'exact': {'id': credential.id}}, ['status'])
        self.assertEqual(ret[0]['status'], 'pending')

        # Now create an assignment, and then mark is as completed.
        assignment1 = self.assignment_manager.create(exam1.id,
            student.id)
        assignment2 = self.assignment_manager.create(exam2.id,
            student.id)
        ret = self.assignment_manager.get_filtered(
            {'exact': {'id': assignment1.id}}, ['status'])
        self.assertEqual(ret[0]['status'], 'assigned')
        ret = self.credential_manager.get_filtered(
            {'exact': {'id': credential.id}}, ['status'])
        self.assertEqual(ret[0]['status'], 'pending')
        self.assignment_manager.update(assignment1.id,
            {'status': 'completed'})
        ret = self.assignment_manager.get_filtered(
            {'exact': {'id': assignment1.id}}, ['status'])
        self.assertEqual(ret[0]['status'], 'completed')
        ret = self.credential_manager.get_filtered(
            {'exact': {'id': credential.id}}, ['status'])
        self.assertEqual(ret[0]['status'], 'pending')
        self.assignment_manager.update(assignment2.id,
            {'status': 'completed'})
        ret = self.assignment_manager.get_filtered(
            {'exact': {'id': assignment2.id}}, ['status'])
        self.assertEqual(ret[0]['status'], 'completed')
        ret = self.credential_manager.get_filtered(
            {'exact': {'id': credential.id}}, ['status'])
        self.assertEqual(ret[0]['status'], 'granted')


class TestCredentialTypeManager(GeneralTestCase):
    def test_create(self):
        ret = self.credential_type_manager.create('some name', 'A degree from an accredited university.')
        self.assertEquals(ret.name, 'some name')
        self.assertEquals(ret.description, 'A degree from an accredited university.')

    def test_update(self):
        ct_1 = self.credential_type_manager.create('some name', 'A cisco certification')
        self.assertRaises(exceptions.PermissionDeniedException, self.credential_type_manager.update, self.user1_auth_token, ct_1.id,
            {'name' : 'a longer name'})
        self.credential_type_manager.update(ct_1.id, {'name' : 'a longer name'})
        self.credential_type_manager.update(ct_1.id, {'description' : 'different description'})
        credential_type = CredentialType.objects.get(id=ct_1.id)
        self.assertEquals(credential_type.description, 'different description')
        self.assertEquals(credential_type.name, 'a longer name')

    def test_get_filtered(self):
        ct_1 = self.credential_type_manager.create('a name', 'a description')
        ct_2 = self.credential_type_manager.create('another', 'another description')
        ret = self.credential_type_manager.get_filtered({}, ['id', 'name', 'description'])
        self.assertEquals(type(ret), list)
        self.assertEquals(len(ret), 2)
        self.assertEquals(type(ret[0]), dict)
        self.assertEquals(type(ret[1]), dict)
        self.failUnless(type(ret[1]['id']) in [int, long])
        for credential_type in ret:
            if credential_type['id'] == ct_1.id:
                self.assertEquals(credential_type['name'], 'a name')
            elif credential_type['id'] == ct_2.id:
                self.assertEquals(credential_type['name'], 'another')
                self.assertEquals(credential_type['description'], 'another description')
            else:
                self.fail('unexpected credential type primary key [%d] in result set.  the expected ones were [%d, %d]' %\
                    (credential_type['id'], ct_1.id, ct_2.id))
        ret = self.credential_type_manager.get_filtered({}, ['id'])
        self.assertEquals('name' not in ret[0], True)

    def test_delete(self):
        self.credential_type_manager.create('name', 'description')
        self.credential_type_manager.create('another', 'another description')
        ret = self.credential_type_manager.get_filtered({}, ['id'])
        self.assertEquals(type(ret), list)
        self.assertEquals(len(ret), 2)
        self.credential_type_manager.delete(ret[0]['id'])
        ret = self.credential_type_manager.get_filtered({}, ['id'])
        self.assertEquals(len(ret), 1)

class TestCsvExport(TestCase):
    """ Tests the export_csv view. """

    def test_not_post_request(self):
        c = django.test.client.Client()
        response = c.get('/export_csv/')
        self.assertEquals(response.status_code, 400) # bad request

    def test_data_not_in_post(self):
        c = django.test.client.Client()
        response = c.post('/export_csv/',
            data={'foodata': json.dumps([['a', 'b'], ['c', 'd']])})
        self.assertEquals(response.status_code, 400) # bad request

    def test_data_in_wrong_format(self):
        c = django.test.client.Client()
        response = c.post('/export_csv/',
            data={'data': json.dumps(['a', 'b'])})
        self.assertEquals(response.status_code, 400) # bad request
        response = c.post('/export_csv/',
            data={'data': json.dumps({'a': 'b'})})
        self.assertEquals(response.status_code, 400) # bad request
        response = c.post('/export_csv/',
            data={'data': json.dumps([{'a': 'b'}])})
        self.assertEquals(response.status_code, 400) # bad request

    def test_json_unicode(self):
        """ make sure we can handle UTF-8 encoded Unicode with our json tools """
        unicode_string = u"東西"
        encoded_and_decoded_string = json.loads(json.dumps(unicode_string))
        self.assertEquals(encoded_and_decoded_string, unicode_string)
        self.failUnless(isinstance(encoded_and_decoded_string, unicode))

    def test_valid_data(self):
        c = django.test.client.Client()
        the_data = [
            [u"first name", u"last name", u"favorite book"],
            [u"Jules", u"Verne", u"A Journey to the Center of the Earth"],
            [u"Лeв", u"Толсто́й", u"Война и мир"],
            [u"耳", u"李", u"道德经"]
        ]
        csv_output = cStringIO.StringIO()
        writer = UnicodeCsvWriter(csv_output)
        for row in the_data:
            writer.writerow(row)
        response = c.post('/export_csv/', data={'data': json.dumps(the_data)})
        self.assertEquals(csv_output.getvalue(), response.content)

        # Also, check that we're using the custom "sanecsv" dialect that quotes
        # EVERYTHING, which makes importing less error-prone. This is a little
        # crappy, but I'm not sure how to do it better.
        # Get what the first line of the CSV file "should be"
        first_line_should_be = '"first name","last name","favorite book"'
        # Get what the first line actually is
        first_line_actually_is = csv_output.getvalue().splitlines()[0]
        # They should be the same, and would not be if we were using another
        # dialect (i.e. dialect=csv.excel) in the UnicodeCsvWriter
        self.assertEquals(first_line_should_be, first_line_actually_is)

class TestDelete(BasicTestCase):
    def test_delete_blame(self):
        dont_taze_me_bro = self.user_manager.create('dont_taze_me_bro', 'password', 'Mr.', 'Don\'t', 'Taze Me Bro', '123-456-7890',
            'dont@tazemebro.com', 'active')
        res = self.user_manager.get_filtered({'exact' : {'id' : dont_taze_me_bro.id}}, ['last_name'])
        self.assertEquals(len(res), 1)
        self.assertEquals(res[0]['last_name'], 'Taze Me Bro')
        the_blame_to_delete = dont_taze_me_bro.blame
        the_blame_to_delete.delete()
        res = self.user_manager.get_filtered({'exact' : {'id' : dont_taze_me_bro.id}}, ['last_name'])
        # We want to assert that dont_taze_me_bro still exists (i.e., that he wasn't tazed)
        self.assertEquals(len(res), 1)
        self.assertEquals(res[0]['last_name'], 'Taze Me Bro')

    def test_delete_related_notnull(self):
        # Test to reproduce #757
        my_region = self.region_manager.create('My Region')
        res = self.region_manager.get_filtered({'exact' : {'id' : my_region.id}}, ['name'])
        self.assertEquals(len(res), 1)
        self.assertEquals(res[0]['name'], 'My Region')
        my_venue = self.venue_manager.create('My Venue', '919-555-1234', my_region.id)
        res = self.venue_manager.get_filtered({'exact' : {'id' : my_venue.id}}, ['name'])
        self.assertEquals(len(res), 1)
        self.assertEquals(res[0]['name'], 'My Venue')
        # Attempt to delete the Region, which should fail because the Venue refers to it.
        self.assertRaises(exceptions.CascadingDeleteException, my_region.delete)
        res = self.region_manager.get_filtered({'exact' : {'id' : my_region.id}}, ['name'])
        self.assertEquals(len(res), 1)
        self.assertEquals(res[0]['name'], 'My Region')

class TestErrorTemplates(TestCase):
    def test_404(self):
        response = self.client.get('/this/path/should/not/exist')
        self.assertEquals(response.status_code, 404)
        self.assertTrue('TemplateDoesNotExist' not in response.content)
        self.assertTemplateUsed(response, '404.html')

    def test_500(self):
        from django.core.urlresolvers import get_resolver
        from django.conf.urls.defaults import url
        from django.http import HttpResponseServerError
        from django.template import Context, loader
        url_patterns = get_resolver(None).url_patterns
        def server_error_view(request):
            return HttpResponseServerError(loader.get_template('500.html').render(Context()))
        path = 'this/path/should/cause/a/server/error'
        url_patterns.append(url('^%s$' % path, server_error_view))
        response = self.client.get('/%s' % path)
        self.assertEquals(response.status_code, 500)
        self.assertTrue('TemplateDoesNotExist' not in response.content)
        self.assertTemplateUsed(response, '500.html')

class TestGetters(BasicTestCase):
    def test_get_content_type(self):
        some_exam = self.exam_manager.create('some exam')
        ret = self.exam_manager.get_filtered({'exact': {'id': some_exam.id}},
            ['content_type'])
        self.assertEquals(len(ret), 1)
        self.assertEquals(ret[0]['content_type'], 'pr_services.exam')

        ret = self.task_manager.get_filtered({'exact': {'id': some_exam.id}},
            ['content_type'])
        self.assertEquals(len(ret), 1)
        self.assertEquals(ret[0]['content_type'], 'pr_services.exam')

class TestGroupManager(GeneralTestCase):
    def test_add_user(self):
        cool_group = self.group_manager.create('cool_group')
        sweep_it_up = self.user_manager.create('sweep_it_up', 'iSweepEveryDay', '', '', '', '', '', 'active')
        self.assertRaises(exceptions.PermissionDeniedException, self.group_manager.update, self.user1_auth_token, cool_group.id,
            {'users' : {'add' : [sweep_it_up.id]}})
        self.group_manager.update(cool_group.id, {'users' : {'add' : [sweep_it_up.id]}})
        # re #2360 - Test that set_many doesn't raise an exception when we try to add the
        # same key again, especially when it's represented as unicode instead of an int.
        self.group_manager.update(cool_group.id, {'users' : {'add' : [sweep_it_up.id]}})
        self.group_manager.update(cool_group.id, {'users' : {'add' : [unicode(sweep_it_up.id)]}})
        group = self.group_manager.get_filtered({'exact' : {'id' : cool_group.id}}, ['id', 'users'])[0]
        self.assertTrue(sweep_it_up.id in group['users'])
        self.assertEquals(len(group['users']), 1)

    def test_add_users(self):
        cool_group = self.group_manager.create('cool_group')
        sweep_it_up = self.user_manager.create('sweep_it_up', 'iSweepEveryDay', '', '', '', '', '', 'active')
        lay_it_down = self.user_manager.create('lay_it_down', 'iLayItDown', '', '', '', '', '', 'active')
        self.assertRaises(exceptions.PermissionDeniedException, self.group_manager.update, self.user1_auth_token, cool_group.id,
            {'users' : {'add' : [sweep_it_up.id, lay_it_down.id]}})
        self.group_manager.update(cool_group.id, {'users' : {'add' : [sweep_it_up.id, lay_it_down.id]}})
        groups = self.group_manager.get_filtered({'exact' : {'id' : cool_group.id}}, ['id', 'users'])
        self.assertTrue(lay_it_down.id in groups[0]['users'])
        self.assertTrue(sweep_it_up.id in groups[0]['users'])
        self.assertEquals(len(groups[0]['users']), 2)

    def test_create(self):
        ret = self.group_manager.create('some name')
        self.assertEquals(ret.name, 'some name')

    def test_create_perm_denied(self):
        """
        test_create tests creating a group with the cru_groups
        permission set
        this tests trying to make one without permission
        """

        self.assertRaises(exceptions.PermissionDeniedException, self.group_manager.create,
            self.user1_auth_token, 'new group name')

    def test_update(self):
        new_group = self.group_manager.create('some name')
        self.assertRaises(exceptions.PermissionDeniedException, self.group_manager.update, self.user1_auth_token, new_group.id, {'name' : 'a longer name'})
        self.group_manager.update(new_group.id, {'name' : 'a longer name'})
        q_group = Group.objects.get(id = new_group.id)
        self.assertEquals(q_group.name, 'a longer name')

    def test_get_filtered(self):
        self.group_manager.create('a name')
        self.group_manager.create('another')
        ret = self.group_manager.get_filtered({}, ['id', 'name'])
        self.assertEquals(type(ret), list)
        # we have two additional groups from the setUp() method
        self.assertTrue(len(ret) >= 5)
        self.assertEquals(type(ret[0]), dict)
        self.assertEquals(type(ret[1]), dict)
        self.failUnless(type(ret[1]['id']) in [int, long])
        ret = self.group_manager.get_filtered({}, ['id'])
        self.failUnless('id' in ret[0])
        # we didn't ask for the 'name' value, make sure it's not present
        self.failUnless('name' not in ret[1])

    def test_delete(self):
        g1 = self.group_manager.create('name')
        self.group_manager.create('another')
        ret = self.group_manager.get_filtered({}, ['id'])
        self.assertEquals(type(ret), list)
        # we have an additional group from the setUp() method
        group_count = len(ret)
        self.assertTrue(group_count >= 5)
        self.group_manager.delete(g1.id)
        ret = self.group_manager.get_filtered({}, ['id'])
        # we have an additional group from the setUp() method
        self.assertEquals(len(ret), group_count - 1)

    def test_remove_users(self):
        cool_group = self.group_manager.create('cool_group')
        sweep_it_up = self.user_manager.create('sweep_it_up', 'iSweepEveryDay', '', '', '', '', '', 'active')
        lay_it_down = self.user_manager.create('lay_it_down', 'iLayItDown', '', '', '', '', '', 'active')
        self.group_manager.update(cool_group.id, {'users' : {'add' : [sweep_it_up.id, lay_it_down.id]}})
        self.assertRaises(exceptions.PermissionDeniedException, self.group_manager.update, self.user1_auth_token, cool_group.id,
            {'users' : {'remove' : [sweep_it_up.id, lay_it_down.id]}})
        self.group_manager.update(cool_group.id, {'users' : {'remove' : [lay_it_down.id]}})
        cool_group_dict = self.group_manager.get_filtered({'exact' : {'id' : cool_group.id}}, ['users'])[0]
        self.assertEquals(len(cool_group_dict['users']), 1)
        self.assertEquals(cool_group_dict['users'][0], sweep_it_up.id)

class TestLogging(BasicTestCase):
    def test_log(self):
        lm = self.log_manager
        lm.critical(self.admin_token, 'this is a critical test')
        lm.error(self.admin_token, 'this is an error test')
        lm.warning(self.admin_token, 'this is a warning test')
        lm.info(self.admin_token, 'this is an info test')
        lm.debug(self.admin_token, 'this is a debug test')

        # Test guest without logging permission
        guest_acl = ACL.objects.filter(role__name='Guest')[0]
        arb_perm_list = cPickle.loads(str(guest_acl.arbitrary_perm_list))
        if 'logging' in arb_perm_list:
            arb_perm_list.remove('logging')
            guest_acl.arbitrary_perm_list = cPickle.dumps(arb_perm_list)
            guest_acl.save()
            facade.subsystems.Authorizer._load_acls() # must reload from DB for it to take effect
        self.assertRaises(exceptions.NotLoggedInException,
            self.log_manager.error, 'this is not a valid auth token',
            'this is an invalid auth token test')
        self.assertRaises(exceptions.PermissionDeniedException,
            self.log_manager.error, '', 'this is a guest auth token test')
        self.assertRaises(exceptions.PermissionDeniedException,
            self.log_manager.error, None, 'this is a guest auth token test')

        # Add logging permission for guest
        guest_acl = ACL.objects.filter(role__name='Guest')[0]
        arb_perm_list = cPickle.loads(str(guest_acl.arbitrary_perm_list))
        if 'logging' not in arb_perm_list:
            arb_perm_list.append('logging')
            guest_acl.arbitrary_perm_list = cPickle.dumps(arb_perm_list)
            guest_acl.save()
            facade.subsystems.Authorizer._load_acls() # must reload from DB for it to take effect
        self.log_manager.error('', 'this is a guest auth token test')
        self.log_manager.error(None, 'this is a guest auth token test')

class TestModels(GeneralTestCase):
    def test_room_get_surrs_by_time(self):
        self.e1 = self.event_manager.create('Event 1', 'Event 1', 'Event 1', self.right_now.isoformat(),
            (self.right_now+self.one_day*3).isoformat(), self.organization1.id, {'venue' : self.venue1.id})
        session1 = self.session_manager.create(self.right_now.isoformat(),
            (self.right_now + self.one_day).isoformat(), 'active', True, 10000, self.e1.id, 'Short Name 1', 'Full Name 1')
        student_role = SessionUserRole.objects.get(name__exact='Student')
        role_req1 = self.session_user_role_requirement_manager.create(str(session1.id), str(student_role.id), 1, 3, False)
        session2 = self.session_manager.create((self.right_now+self.one_day*2).isoformat(),
            (self.right_now+self.one_day*3).isoformat(), 'active', True, 10000, self.e1.id, 'Short Name 1', 'Full Name 1')
        role_req2 = self.session_user_role_requirement_manager.create(str(session2.id), str(student_role.id), 1, 3, False)
        session1.room = self.room1
        session2.room = self.room1
        session1.save()
        session2.save()

        ret = self.room1.get_surrs_by_time(self.right_now.replace(tzinfo=None), (self.right_now+3*self.one_day).replace(tzinfo=None))
        self.assertEquals(ret.count(), 2)
        self.assertTrue(role_req1 in ret)
        self.assertTrue(role_req2 in ret)

        ret = self.room1.get_surrs_by_time((self.right_now-self.one_day).replace(tzinfo=None), (self.right_now+3*self.one_day).replace(tzinfo=None))
        self.assertEquals(ret.count(), 2)
        self.assertTrue(role_req1 in ret)
        self.assertTrue(role_req2 in ret)

        ret = self.room1.get_surrs_by_time((self.right_now+self.one_day).replace(tzinfo=None), (self.right_now+3*self.one_day).replace(tzinfo=None))
        self.assertEquals(ret.count(), 1)
        self.assertTrue(role_req2 in ret)

        ret = self.room1.get_surrs_by_time((self.right_now-self.one_day).replace(tzinfo=None), (self.right_now).replace(tzinfo=None))
        self.assertEquals(ret.count(), 0)

    def test_user_full_name_derived_field(self):
        homer_simpson = self.user_manager.create('homer.simpson', 'password',
            'Mr.', 'Homer', 'Simpson', '', '', 'active')
        self.assertEquals(homer_simpson.full_name, u'Mr. Homer Simpson')
        maggie_simpson = self.user_manager.create('maggie.simpson', 'password',
            '', 'Maggie', 'Simpson', '', '', 'active')
        self.assertEquals(maggie_simpson.full_name, u'Maggie Simpson')
        mlk = self.user_manager.create('mlk', 'password',
            'Dr.', 'Martin', 'King', '', '', 'active', {'name_suffix': 'Jr.',
                'middle_name': 'Luther'})
        self.assertEquals(mlk.full_name, 'Dr. Martin Luther King, Jr.')

if 'ecommerce' in settings.INSTALLED_APPS:
    class TestPaymentManager(GeneralTestCase):
        def setUp(self):
            super(TestPaymentManager, self).setUp()
            self.po1 = self.purchase_order_manager.create({'user' : self.user1.id, 'training_units_purchased' : 100, 'training_units_price' : 5000})
            # This is info for an American Express gift card which has no remaining value.
            self.p = self.payment_manager.create(self.po1.id, 'Amex', '379014099768149', '1010', '5000',
                    str(time.time()), 'Gift Card', 'Recipient', '170 Southport Dr. Suite 400',
                    'Morrisville', 'NC', '27650', 'US', '4434')
            self.assertTrue(self.po1.is_paid)

        def test_cant_pay_again(self):
            # Try to pay another dollar on an already paid PO - this should raise an exception
            self.assertRaises(exceptions.PurchaseOrderAlreadyPaidException, self.payment_manager.create, self.admin_token, self.po1.id, 'Amex', '379014099768149',
                '1010', '1', str(time.time()), 'Gift Card', 'Recipient', '170 Southport Dr. Suite 400', 'Morrisville', 'NC', '27650', 'US', '4434')

        def test_create(self):
            p1 = Payment.objects.get(id = self.p.id)
            self.assertEquals(p1.amount, 5000)
            self.assertTrue(p1.result_message in ['Success', 'SuccessWithWarning', 'APPROVED', 'Approved'])
            self.assertEquals(p1.purchase_order, self.po1)
            # Make sure we are only storing the last 4 digits of the card number.
            self.assertEquals(p1.card_number, '8149')

        def test_refund(self):
            r1 = self.payment_manager.refund(self.p.id, 20, '379014099768149')
            r2 = self.payment_manager.refund(self.p.id, 30, '379014099768149')
            ga = self.payment_manager.get_filtered({}, ['id', 'amount', 'refunds', 'date'])
            self.assertEquals(len(ga), 1)
            p = ga[0]
            self.assertEquals(p['amount'], 5000)
            self.assertEquals(len(p['refunds']), 2)
            refunds = p['refunds']
            for r in refunds:
                self.assertEquals(r['amount'] in [20, 30], True)
                self.assertEquals('date' in r, True)
                self.assertEquals(len(r['date']) > 0, True)
            self.assertEquals(r1, 20)
            self.assertEquals(r2, 30)
            # Total refunds for a payment cannot exceed the payment's value
            self.assertRaises(exceptions.PermissionDeniedException, self.payment_manager.refund, self.admin_token, self.p.id, 6000)
            # A normal user cannot issue a refund
            self.assertRaises(exceptions.PermissionDeniedException, self.payment_manager.refund, self.user1_auth_token, self.p.id, 50)

class TestProductManager(BasicTestCase):
    def setUp(self):
        super(TestProductManager, self).setUp()
        self.p1 = self.product_manager.create('ABC123', 'Bread Slicer', 'Slices bread', 4995, 2995, {'display_order' : 90})
        self.pd1 = self.product_discount_manager.create('Slick Deal', 85, 0, 0, False, [self.p1.id], [], 'cheap')
        self.group1 = self.group_manager.create('Group 1', {'users' : {'add' : [self.admin_token.user.id]}})
        self.group2 = self.group_manager.create('Group 2')

    def test_create_products(self):
        products = self.product_manager.get_filtered({}, ['display_order', 'id', 'sku', 'price', 'cost'])
        self.assertEquals(products[0]['sku'], 'ABC123')
        self.assertEquals(products[0]['price'], 4995)
        self.assertEquals(products[0]['cost'], 2995)
        self.assertEquals(products[0]['display_order'], 90)

    def test_create_product_discounts(self):
        product_discounts = self.product_discount_manager.get_filtered({}, ['id', 'currency', 'promo_code'])
        self.assertEquals(len(product_discounts), 1)
        self.assertEquals(product_discounts[0]['currency'], 85)
        self.assertEquals(product_discounts[0]['promo_code'], 'cheap')

    def test_use_promo_code_discount(self):
        po1 = self.purchase_order_manager.create({'promo_code' : 'cheap'})
        self.product_claim_manager.create(self.p1.id, po1.id, 2)
        ret = self.purchase_order_manager.get_filtered({'exact' : {'id' : po1.id}}, ['id', 'total_price'])
        self.assertEquals(len(ret), 1)
        self.assertEquals(ret[0]['id'], po1.id)
        self.assertTrue('total_price' in ret[0])
        self.assertEquals(ret[0]['total_price'], (4995 - 85) * 2)

    def test_use_ctc_discount(self):
        # Try using a condition_test_collection
        ctc1 = self.condition_test_collection_manager.create('test CTC 1')
        ctc2 = self.condition_test_collection_manager.create('test CTC 2')
        self.condition_test_manager.create(10, ctc1.id, True, {'groups' : {'add':[self.group1.id]}})
        self.condition_test_manager.create(10, ctc2.id, True, {'groups' : {'add':[self.group2.id]}})

        product1 = self.product_manager.create('BCD', 'Product 1', 'Product 1', 500, 200)
        product2 = self.product_manager.create('CDE', 'Product 2', 'Product 2', 500, 200)
        self.product_discount_manager.create('Discount 1', None, None, 20, True, [product1.id], [], None, ctc1.id)
        self.product_discount_manager.create('Discount 2', None, None, 15, True, [], [], None, ctc2.id)

        po1 = self.purchase_order_manager.create(self.admin_token)
        self.product_claim_manager.create(product1.id, po1.id, 2)

        po2 = self.purchase_order_manager.create(self.admin_token)
        self.product_claim_manager.create(product2.id, po2.id, 2)

        ret1 = self.purchase_order_manager.get_filtered({'exact' : {'id' : po1.id}}, ['id', 'total_price'])
        ret2 = self.purchase_order_manager.get_filtered({'exact' : {'id' : po2.id}}, ['id', 'total_price'])

        self.assertEquals(len(ret1), 1)
        self.assertEquals(ret1[0]['id'], po1.id)
        self.assertTrue('total_price' in ret1[0])
        self.assertEquals(ret1[0]['total_price'], (500*2*.8))

        self.assertEquals(len(ret2), 1)
        self.assertEquals(ret2[0]['id'], po2.id)
        self.assertTrue('total_price' in ret2[0])
        self.assertEquals(ret2[0]['total_price'], (500 * 2))

    def test_inventory(self):
        self.p1.starting_quantity = 10
        self.p1.save()
        for x in range(6):
            blame = self.blame_manager.create(self.admin_token)
            ProductTransaction.objects.create(product = self.p1, blame = blame, change = x)
        result = self.product_manager.get_filtered({'exact' : {'id' : self.p1.id}}, ['id', 'inventory'])
        self.assertTrue('inventory' in result[0])
        self.assertEquals(int(result[0]['inventory']), 25)

class TestPrTime(TestCase):
    def test_iso_conversion(self):
        ret = pr_time.iso8601_to_datetime('1994-11-05T13:15:30Z')
        self.assertEquals(ret.year, 1994)
        self.assertEquals(ret.month, 11)
        self.assertEquals(ret.day, 05)
        self.assertEquals(ret.hour, 13)
        self.assertEquals(ret.minute, 15)
        self.assertEquals(ret.second, 30)
        self.assertRaises(exceptions.DatetimeConversionError, pr_time.iso8601_to_datetime, 'not a proper ISO8601 string')

class TestPurchaseOrderManager(GeneralTestCase):
    def setUp(self):
        super(TestPurchaseOrderManager, self).setUp()
        self.prod1 = self.product_manager.create('ACB123', 'Fly Paper', 'Sticky Paper that traps Flies', 995, 1095)
        self.prod2 = self.product_manager.create('XYZ456', 'Sand Paper', 'Sandy Paper that polishes Flies', 795, 895)
        self.prod_offer1 = self.product_offer_manager.create(self.prod1.id, self.user1.id, 1195,
            'This is an amazing set of fly-trapping paper!!!!!!')

    def test_retrieve_receipt(self):
        po1 = self.purchase_order_manager.create(self.user1_auth_token, {'user' : self.user1.id})
        self.product_claim_manager.create(self.user1_auth_token, self.prod1.id, po1.id, 7)

        ret = self.purchase_order_manager.retrieve_receipt(po1.id)
        self.failUnless(ret.has_key('subject') and ret['subject'])
        self.failUnless(ret.has_key('body') and ret['body'])

class TestRoleManager(GeneralTestCase):
    def test_create(self):
        ret = self.role_manager.create('some role name')
        self.assertEquals(ret.name, 'some role name')

    def test_create_perm_denied(self):
        """
        test_create tests creating a role with the cru_roles
        permission set
        this tests trying to make one without permission
        """

        self.assertRaises(exceptions.PermissionDeniedException, self.role_manager.create,
            self.user1_auth_token, 'new role name')

    def test_update(self):
        self.group_manager.create('group1')
        self.group_manager.create('group2')
        new_role = self.role_manager.create('mistaken name')
        self.role_manager.update(new_role.id, {'name' : 'an unmistakable name'})
        q_role = Role.objects.get(id = new_role.id)
        self.assertEquals(q_role.name, 'an unmistakable name')

    def test_get_filtered(self):
        role1 = self.role_manager.create('role1')
        role2 = self.role_manager.create('role2')
        ret = self.role_manager.get_filtered({'member' : {'id' : [role1.id, role2.id]}}, ['id', 'name'])
        self.assertEquals(type(ret), list)
        self.assertEquals(len(ret), 2)
        self.assertEquals(type(ret[0]), dict)
        self.assertEquals(type(ret[1]), dict)
        self.failUnless(type(ret[1]['id']) in [int, long])
        self.failUnless(ret[1]['name'] == 'role2' or ret[0]['name'] == 'role2')
        ret = self.role_manager.get_filtered({'member' : {'id' : [role1.id, role2.id]}}, ['id'])
        # we asked for the 'id' value, make sure it's correct
        self.failUnless(ret[0]['id'] in (role1.id, role2.id))
        self.failUnless(ret[0]['id'] in (role1.id, role2.id))
        self.assertNotEqual(ret[0]['id'], ret[1]['id'])
        # we didn't ask for the 'name' value, make sure it's not present
        self.assertEquals('name' not in ret[1], True)

    def test_delete(self):
        role1 = self.role_manager.create('role1')
        role2 = self.role_manager.create('role2')
        ret = self.role_manager.get_filtered({'member' : {'id' : [role1.id, role2.id]}}, ['id'])
        self.assertEquals(type(ret), list)
        self.assertEquals(len(ret), 2)
        self.role_manager.delete(role1.id)
        ret = self.role_manager.get_filtered({'member' : {'id' : [role1.id, role2.id]}}, ['id'])
        self.assertEquals(len(ret), 1)

class TestRoomManager(GeneralTestCase):
    def test_name_uniqueness(self):
        self.room_manager.create('Hemingway',
            self.venue1.id, 100)
        # same name, same venue, should fail
        try:
            self.room_manager.create('Hemingway',
                self.venue1.id, 120)
        except ModelDataValidationError, e:
            self.failUnless(e.validation_errors.has_key('name'))
            self.failUnless(e.validation_errors['name'][0].find('conflicts') != -1)
        except Exception, e:
            self.fail(u'The wrong type of exception was raised: %s' %\
                unicode(e))
        else:
            self.fail('A models.ModelDataValidationError should have been raised.')
        # same name but different venue, should succeed
        venue2 = self.venue_manager.create('Venue 2', '1253462',
            self.region1.id)
        self.room_manager.create('Hemingway', venue2.id, 150)

class TestRpcService(TestCase):
    def _compare_object_to_service(self, obj_class, svc_class):
        obj_doc = inspect.getdoc(obj_class)
        svc_doc = inspect.getdoc(svc_class)
        self.assertEquals(obj_doc, svc_doc)
        for name in svc_class._get_service_methods():
            if not hasattr(obj_class, name):
                continue
            obj_m = getattr(obj_class, name)
            svc_m = getattr(svc_class, name)
            obj_m_doc = inspect.getdoc(obj_m)
            svc_m_doc = inspect.getdoc(svc_m)
            self.assertEquals(obj_m_doc, svc_m_doc)
            obj_m_argspec = inspect.getargspec(obj_m)
            svc_m_argspec = inspect.getargspec(svc_m)
            self.assertEquals(obj_m_argspec, svc_m_argspec)
            self.assertTrue(hasattr(obj_m, '_service_method'))
            self.assertTrue(hasattr(svc_m, '_service_method'))

    def test_rpc_service(self):
        # Define example manager classes.
        class MyObject(object):
            """MyObject"""

            @service_method
            def create(self, name):
                """Create something with a name"""
                return id(name)

            @service_method
            def delete(self, pk):
                """Delete the thing with primary key pk."""

            def do_secret(self, secret_code):
                """Method that should not be exposed as a service."""
                return secret_code

        class MySubObject(MyObject):
            """MySubObject"""

            @service_method
            def create(self, name, description):
                """Create something else with a name and description"""
                return id(name)

            @service_method
            def do_stuff(self, pk):
                """Do stuff to the something with primary key pk."""

        class MyObjectSvc(RpcService):
            action_class = MyObject

        self._compare_object_to_service(MyObject, MyObjectSvc)
        self.assertFalse(hasattr(MyObjectSvc, 'do_secret'))

        class MySubObjectSvc(MyObjectSvc):
            action_class = MySubObject

        self._compare_object_to_service(MySubObject, MySubObjectSvc)
        self.assertFalse(hasattr(MySubObjectSvc, 'do_secret'))

        class MySubObjectSvc2(RpcService):
            action_class = MySubObject

            def non_service_method(self):
                """This extra method is not exposed."""

            @wrap_service_method
            def exposed_service_method(self):
                """This extra method is exposed."""

        self._compare_object_to_service(MySubObject, MySubObjectSvc2)
        self.assertFalse(hasattr(MySubObjectSvc2, 'do_secret'))
        self.assertTrue(hasattr(MySubObjectSvc2, 'non_service_method'))
        self.assertTrue('non_service_method' not in MySubObjectSvc2._get_service_methods())
        self.assertTrue(hasattr(MySubObjectSvc2, 'exposed_service_method'))
        self.assertTrue('exposed_service_method' in MySubObjectSvc2._get_service_methods())

        MyObjectSvc2 = create_rpc_service(MyObject)
        self._compare_object_to_service(MyObject, MyObjectSvc2)
        self.assertFalse(hasattr(MyObjectSvc2, 'do_secret'))

        MySubObjectSvc3 = create_rpc_service(MySubObject)
        self._compare_object_to_service(MySubObject, MySubObjectSvc3)
        self.assertFalse(hasattr(MySubObjectSvc3, 'do_secret'))

class TestEventTemplateManager(GeneralTestCase):
    def test_all(self):
        event_template = self.event_template_manager.create(
            'EVT', 'Templated Event', 'A super-boring event')
        session_template = self.session_template_manager.create('name', 'longer name', '2.0', 'This is a description', 1595,
            600000, True, 'Self-Paced E-Learning', {'event_template' : event_template.id})
        event = self.event_manager.create(event_template.name_prefix,
            event_template.title, event_template.description, self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(),
            self.organization1.id, {'venue' : self.venue1.id, 'event_template' : event_template.id})

        et = self.event_template_manager.get_filtered({'exact' : {'id' : event_template.id}}, ['id', 'name_prefix', 'session_templates', 'events', 'title'])
        e = self.event_manager.get_filtered({'exact' : {'id' : event.id}}, ['id', 'event_template', 'title', 'name'])
        st = self.session_template_manager.get_filtered({'exact' : {'id' : session_template.id}}, ['id', 'event_template'])

        self.assertEquals(len(et), 1)
        self.assertEquals(len(e), 1)
        self.assertEquals(len(st), 1)
        self.assertEquals(et[0]['title'], e[0]['title'])
        self.assertEquals(et[0]['id'], e[0]['event_template'])
        self.assertTrue(st[0]['id'] in et[0]['session_templates'])
        self.assertTrue(e[0]['id'] in et[0]['events'])
        self.assertEquals(e[0]['name'], '%s%d' % (event_template.name_prefix, event.id))


class TestEventManager(GeneralTestCase):
    def setUp(self):
        super(TestEventManager, self).setUp()
        self.test_utils = TestUtils()

    def test_create_with_sessions(self):
        sessions = [
            {
                'start' : self.right_now.isoformat(),
                'end' : (self.right_now + self.one_day).isoformat(),
                'status' : 'pending',
                'confirmed' : False,
                'default_price' : 0,
                'shortname' : 'Session 1',
                'fullname' : 'The very first Session!',
                'optional_attributes' : {'lead_time' : 60*60*24*3, 'url' : 'http://openassign.org'},
            },
            {
                'start' : self.right_now.isoformat(),
                'end' : (self.right_now + self.one_day).isoformat(),
                'status' : 'pending',
                'confirmed' : False,
                'default_price' : 0,
                'shortname' : 'Session 2',
                'fullname' : 'The second Session!',
                'optional_attributes' : {'lead_time' : 60*60*24*3, 'url' : 'http://openassign.org'},
            }
        ]

        e1 = self.event_manager.create('Event 1',
            'First Event of My Unit Test', 'Event 1', self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(),
            self.organization1.id, {'venue' : self.venue1.id, 'sessions' : sessions})

        # verify results
        event = Event.objects.get(id=e1.pk)
        sessions = event.sessions.all()
        self.assertEquals(len(sessions), 2)
        self.assertEquals(event.title, 'First Event of My Unit Test')
        self.assertEquals(event.description, 'Event 1')

        for session in sessions:
            self.assertEquals(session.status, 'pending')
            self.assertTrue(session.shortname.startswith('Session'))
            self.assertEquals(session.url, 'http://openassign.org')
            self.assertEquals(session.lead_time, 60*60*24*3)


class TestSessionManager(GeneralTestCase):
    def setUp(self):
        super(TestSessionManager, self).setUp()
        self.test_utils = TestUtils()

    def test_view(self):
        e1 = self.event_manager.create('Event 1',
            'First Event of My Unit Test', 'Event 1', self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(),
            self.organization1.id, {'venue' : self.venue1.id})
        self.session_manager.create(
            self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), 'active', False, 10000, e1.id, 'Short Name 1', 'Full Name 1', {'room':self.room1.id})
        ret = self.session_manager.detailed_surr_view()
        self.assertEquals(len(ret), 1)
        fetched_session = ret[0]
        self.assertTrue('room' in fetched_session)

        room = fetched_session['room']
        self.assertTrue('name' in room)
        self.assertEquals(room['name'], self.room1.name)
        self.assertTrue('id' in room)
        self.assertTrue('venue_name' in room)
        self.assertEquals(room['venue_name'], self.venue1.name)
        self.assertTrue('venue_address' in room)

        address = room['venue_address']
        self.assertTrue('label' in address)
        self.assertEquals(address['label'], self.venue1.address.label)
        self.assertTrue('locality' in address)
        self.assertEquals(address['locality'], self.venue1.address.locality)
        self.assertTrue('region' in address)
        self.assertEquals(address['region'], self.venue1.address.region)
        self.assertTrue('postal_code' in address)
        self.assertEquals(address['postal_code'], self.venue1.address.postal_code)
        self.assertTrue('country' in address)
        self.assertEquals(address['country'], self.venue1.address.country)

        # test without a room defined, which tests the merging logic
        e2 = self.event_manager.create('Event 2',
            'Second Event of My Unit Test', 'Event 2', self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(),
            self.organization1.id, {'venue' : self.venue1.id})
        self.session_manager.create(
            self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), 'active', False, 10000, e2.id, 'short name 1', 'long name 1')
        ret = self.session_manager.detailed_surr_view()

    def test_view_without_room(self):
        # test without a room defined, which tests the merging logic
        e2 = self.event_manager.create('Event 2',
            'Second Event of My Unit Test', 'Event 2', self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(),
            self.organization1.id, {'venue' : self.venue1.id})
        self.session_manager.create(
            self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), 'active', False, 10000, e2.id, 'short name 1', 'long name 1')
        self.session_manager.detailed_surr_view()

    def test_create(self):
        e1 = self.event_manager.create('Event 1',
            'First Event of My Unit Test', 'Event 1', self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(),
            self.organization1.id, {'venue' : self.venue1.id})
        session1 = self.session_manager.create(
            self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), 'active', False, 10000, e1.id, 'short name 1', 'long name 1')
        self.assertEquals(session1.status, 'active')

        # Make sure we get a valid paypal url
        self.user_manager.update(self.admin_token.user.id,
            {'paypal_address' : 'mhrivnak@triad.rr.com', 'enable_paypal' : True})
        ret = self.session_manager.get_filtered(
            {'exact' : {'id' : session1.id}}, ['id', 'paypal_url'])
        self.assertEquals(urllib2.urlopen(ret[0]['paypal_url']).code, 200)

    def test_validate(self):
        # event start not <= end
        self.assertRaises(ModelDataValidationError, self.event_manager.create,
            self.admin_token, 'Event 1', 'First Event of My Unit Test', 'Event 1',
            '1994-11-06', '1994-11-05', self.organization1.id, {'venue' : self.venue1.id})
        e1 = self.event_manager.create('Event 1',
            'First Event of My Unit Test', 'Event 1',
            self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(), self.organization1.id,
            {'venue' : self.venue1.id})
        # session start not <= session end
        self.assertRaises(ModelDataValidationError,
            self.session_manager.create, self.admin_token,
            '1994-11-05T18:15:30+00:00', '1994-11-05T16:15:30Z', 'active',
            False, 10000, e1.id, 'short name 1', 'long name 1')
        # session start not >= event start
        self.assertRaises(ModelDataValidationError,
            self.session_manager.create, self.admin_token,
            '1994-11-04T13:15:30+00:00', '1994-11-05T16:15:30Z', 'active',
            False, 10000, e1.id, 'short name 1', 'long name 1')
        # session end not <= event end
        self.assertRaises(ModelDataValidationError,
            self.session_manager.create, self.admin_token,
            '1994-11-05T13:15:30+00:00', '1994-11-06T16:15:30Z', 'active',
            False, 10000, e1.id, 'short name 1', 'long name 1')

    def test_create_perm_denied(self):
        e1 = self.event_manager.create('Event 1', 'Event 1', 'Event 1',
            self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(), self.organization1.id, {'venue' : self.venue1.id})
        self.assertRaises(exceptions.PermissionDeniedException, self.session_manager.create,
            self.user1_auth_token, self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), 'active', False, 100, e1.id, 'short name 1', 'long name 1')

    def test_create_by_pl(self):
        prod = self.product_line_manager.create('Earn your MBA overnight!')
        pl_user = self.user_manager.create('pl_user', 'pw', '', '', '', '', '',
            'active')
        self.product_line_manager.update(prod.id,
            {'managers' : [pl_user.id]})
        pu_token = facade.subsystems.Utils.get_auth_token_object(self.user_manager.login('pl_user', 'pw')['auth_token'])
        # session_template in a product line in which the user is allowed to create sessions
        crs = self.session_template_manager.create('name',
            'longer name', '2.0', 'This is a description', 1595, 600000, True, 'Generic',
            {'product_line' : prod.id})
        # session associated with that session_template, should succeed
        e1 = self.event_manager.create('Event 1', 'Event 1',
            'Event 1', self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(), self.organization1.id,
            {'venue' : self.venue1.id})
        self.session_manager.create(pu_token, self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), 'active', False, 100, e1.id, 'short name 1', 'long name 1',
            {'session_template' : str(crs.id)})
        # session associated with a session_template in a different product line, should fail
        prod_2 = self.product_line_manager.create('pottery')
        crs_2 = self.session_template_manager.create('PA2',
            'intermediate pottery', '2.0', 'This is a description', 1595, 600000, True,
            'ILT', {'product_line' : prod_2.id})
        self.assertRaises(exceptions.PermissionDeniedException, self.session_manager.create,
            pu_token, self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(),
            'active', False, 100, e1.id, 'short name 1', 'long name 1', {'session_template' : str(crs_2.id)})
        # session not associated with a session_template, should fail
        self.assertRaises(exceptions.PermissionDeniedException, self.session_manager.create,
            pu_token, self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(),
            'active', False, 100, e1.id, 'short name 1', 'long name 1')

    def test_update(self):
        e1 = self.event_manager.create('Event 1', 'Event 1',
            'Event 1', self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(), self.organization1.id,
            {'venue' : self.venue1.id})
        session_1 = self.session_manager.create(self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), 'active', False, 100, e1.id, 'short name 1', 'long name 1')
        self.session_manager.update(session_1.id, {'fullname' : 'an even longer name',
            'start' : self.right_now.isoformat(), 'confirmed' : True})
        session = Session.objects.get(id=session_1.id)
        self.assertEquals(session.fullname, 'an even longer name')
        self.assertEquals(session.confirmed, True)

    def test_update_denied(self):
        e1 = self.event_manager.create('Event 1', 'Event 1',
            'Event 1', self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(), self.organization1.id,
            {'venue' : self.venue1.id})
        session_1 = self.session_manager.create(self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), 'active', False, 100, e1.id, 'short name 1', 'long name 1')
        # fails because start date is in the past.
        self.assertRaises(exceptions.PermissionDeniedException,
            self.session_manager.update, self.user1_auth_token, session_1.id,
            {'fullname' : 'an even longer name',
            'start':'1994-11-04T13:15:30+00:00'})

    def test_update_by_pl(self):
        prod = self.product_line_manager.create('Earn your MBA overnight!')
        pl_user = self.user_manager.create('pl_user', 'pw', '', '', '', '', '',
            'active')
        self.product_line_manager.update(prod.id,
            {'managers' : [pl_user.id]})
        pu_token = facade.subsystems.Utils.get_auth_token_object(self.user_manager.login('pl_user', 'pw')['auth_token'])
        # session_template in a product line in which the user is allowed to create sessions
        crs = self.session_template_manager.create('name',
            'longer name', '2.0', 'This is a description', 1595,
            600000, True, 'Generic', {'product_line' : prod.id})
        # session associated with that session_template, should succeed
        e1 = self.event_manager.create('Event 1', 'Event 1',
            'Event 1', self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(),
            self.organization1.id, {'venue' : self.venue1.id})
        pl_evt = self.session_manager.create(self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(),
            'active', False, 100, e1.id, 'short name 1', 'long name 1', {'modality' : 'ILT', 'session_template' : str(crs.id)})
        self.session_manager.update(pu_token, str(pl_evt.id), {'default_price':250})
        # refresh the persistent object manually, since it doesn't get
        # invalidated or refreshed automatically (see ticket #160 in trac)
        pl_evt = Session.objects.get(id=pl_evt.id)
        self.assertEquals(pl_evt.default_price, 250)
        # session associated with a session_template in a different product line, should fail
        prod_2 = self.product_line_manager.create('pottery')
        crs_2 = self.session_template_manager.create('PA2',
            'intermediate pottery', '2.0', 'This is a description',
            1595, 600000, True, 'ILT', {'product_line' : prod_2.id})
        e2 = self.event_manager.create('Event 2', 'Event 2', 'Event 2',
            self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(),
            self.organization1.id, {'venue' : self.venue1.id})
        evt_2 = self.session_manager.create(
            self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(), 'active', False,
            100, e2.id, 'short name 1', 'long name 1', {'session_template' : str(crs_2.id)})
        self.assertRaises(exceptions.PermissionDeniedException, self.session_manager.update,
            pu_token, str(evt_2.id), {'default_price':250})
        # session not associated with a session_template, should fail
        e3 = self.event_manager.create('Event 3', 'Event 3', 'Event 3',
            self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(), self.organization1.id,
            {'venue' : self.venue1.id})
        evt_3 = self.session_manager.create(
            self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(), 'active', False, 100,
            e3.id, 'short name 1', 'long name 1')
        self.assertRaises(exceptions.PermissionDeniedException, self.session_manager.update, pu_token,
            str(evt_3.id), {'default_price':500})

    def test_get_filtered(self):
        e1 = self.event_manager.create('Event 1', 'Event 1',
            'Event 1', self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(), self.organization1.id,
            {'venue' : self.venue1.id})
        self.session_manager.create(
            self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(), 'active', False, 100,
            e1.id, 'short name 1', 'long name 1')
        e2 = self.event_manager.create('Event 2', 'Event 2', 'Event 2',
            (self.right_now+self.one_day*2).isoformat(), (self.right_now+self.one_day*3).isoformat(), self.organization1.id,
            {'venue' : self.venue1.id})
        s2 = self.session_manager.create((self.right_now+self.one_day*2).isoformat(),
            (self.right_now+self.one_day*3).isoformat(), 'active', False, 100, e2.id, 'short name 1', 'long name 1')
        ret = self.session_manager.get_filtered(
            {'range' : {'start' : ((self.right_now+self.one_day).isoformat(), (self.right_now+self.one_day*2).isoformat())}},
            ['id', 'shortname'])
        self.assertEquals(len(ret), 1)
        self.assertEquals(str(ret[0]['id']), str(s2.id))
        self.assertEquals(ret[0]['shortname'], s2.shortname)

    def test_get_filtered_case_insensitive(self):
        # Create events
        e1 = self.event_manager.create('EVT', 'Event 1 Title',
            'Event 1 description', self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(),
            self.organization1.id, {'venue' : self.venue1.id})
        e2 = self.event_manager.create('EVT', 'Event 2 Title', 'Event 2 description',
            (self.right_now+self.one_day*2).isoformat(), (self.right_now+self.one_day*3).isoformat(),
            self.organization1.id, {'venue' : self.venue1.id})
        # Create a dummy event in an attemp
        self.event_manager.create('EVT', 'Foo 3 Title', 'Event 3 description',
            (self.right_now+self.one_day*3).isoformat(), (self.right_now+self.one_day*4).isoformat(),
            self.organization1.id, {'venue' : self.venue1.id})
        events = self.event_manager.get_filtered({'iexact': {'title': 'event 1 tiTLe'}},
            ['id', 'title'])
        self.assertEquals(len(events), 1)
        self.assertEquals(events[0]['id'], e1.id)
        events = self.event_manager.get_filtered({'icontains': {'title': 'vENt'}},
            ['id', 'title'])
        self.assertEquals(len(events), 2)
        self.failUnless(events[0]['id'] != events[1]['id'])
        self.failUnless(events[0]['id'] == e1.id or events[1]['id'] == e1.id)
        self.failUnless(events[0]['id'] == e2.id or events[1]['id'] == e2.id)
        events = self.event_manager.get_filtered({'ibegins': {'title': 'eVeNt 1'}},
            ['id', 'name'])
        self.assertEquals(len(events), 1)
        self.assertEquals(events[0]['id'], e1.id)
        events = self.event_manager.get_filtered({'iends': {'title': '2 TItle'}},
            ['id', 'name'])
        self.assertEquals(len(events), 1)
        self.assertEquals(events[0]['id'], e2.id)

    def test_delete(self):
        self.e1 = self.event_manager.create('Event 1', 'Event 1', 'Event 1', self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), self.organization1.id, {'venue' : self.venue1.id})
        session_1 = self.session_manager.create(self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(), 'active', False, 100,
            self.e1.id, 'short name 1', 'long name 1')
        self.e2 = self.event_manager.create('Event 2', 'Event 2', 'Event 2', self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), self.organization1.id, {'venue' : self.venue1.id})
        self.session_manager.create(self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(),
                      'active', False, 100, self.e2.id, 'short name 1', 'long name 1')
        ret = self.session_manager.get_filtered({}, ['id'])
        self.assertEquals(type(ret), list)
        self.assertEquals(len(ret), 2)
        self.session_manager.delete(session_1.id)
        ret = self.session_manager.get_filtered({}, ['id'])
        self.assertEquals(len(ret), 1)

    def test_get_events_needing_reminders(self):
        tu = TestUtils()
        tu.setup_test_sessions()
        sessions = self.session_manager._get_sessions_needing_reminders()
        self.assertEquals(len(sessions), 2)
        session2 = Session.objects.get(pk=tu.s2.id)
        session3 = Session.objects.get(pk=tu.s3.id)
        self.failUnless(session2 in sessions)
        self.failUnless(session3 in sessions)

    def test_enrollment_auth_by_venue(self):
        # Create a proctor role with a user
        proctor_group = self.group_manager.create('Proctors')
        acl = {
            'Assignment' : {
                'c' : False,
                'r' : ['id', 'status'],
                'u' : ['status'],
                'd' : False,
            },
        }
        proctor_role = Role.objects.create(name='Proctor')
        proctor_acl = ACL.objects.create(acl = cPickle.dumps(acl), role=proctor_role)
        group_test_method = ACCheckMethod.objects.get(name = 'actor_member_of_group')
        ACMethodCall.objects.create(acl=proctor_acl, ac_check_method = group_test_method,
            ac_check_parameters = cPickle.dumps({'group_id' : proctor_group.id}))

        assignment_venue_matches_actor_preferred_venue = ACCheckMethod.objects.get(
            name = 'assignment_venue_matches_actor_preferred_venue')
        ACMethodCall.objects.create(acl=proctor_acl, ac_check_method=assignment_venue_matches_actor_preferred_venue)
        proctor = self.user_manager.create('proctor1', 'password', 'Dr', 'P', 'Roctor', '123-456-7890', 'p@roctor.org', 'active',
            {'groups' : {'add' : [proctor_group.id]}})
        proctor_token = facade.subsystems.Utils.get_auth_token_object(self.user_manager.login('proctor1', 'password')['auth_token'])
        facade.subsystems.Authorizer._load_acls()

        # Create some users and enroll them in something
        learner1 = self.user_manager.create('learner_1', 'password', '', '', '', '', '', 'active')
        self.user_manager.update(proctor.id, {'preferred_venues' : {'add' : [self.venue1.id]}})

        self.e1 = self.event_manager.create('Event 1', 'Event 1', 'Event 1', self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), self.organization1.id, {'venue' : self.venue1.id})
        evt1 = self.session_manager.create(self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), 'active', True, 10000, self.e1.id, 'short name 1', 'long name 1')
        student_role = SessionUserRole.objects.get(name__exact='Student')
        role_req = self.session_user_role_requirement_manager.create(str(evt1.id), str(student_role.id), 1, 3, False)
        self.assignment_manager.bulk_create(str(role_req.id), [learner1.id])
        assignment_ret = self.assignment_manager.bulk_create(role_req.id, [learner1.id])

        # Try defining the venue by way of the session's room, and make sure this still works
        self.e1.venue = None
        self.e1.save()
        evt1.room = self.room1
        evt1.save()

        # Try to change status
        self.assignment_manager.update(proctor_token, assignment_ret[learner1.id]['id'], {'status' : 'completed'})

        # Remove the venue from the proctor's preferred_venues, and make sure the update fails
        self.user_manager.update(proctor.id, {'preferred_venues' : {'remove' : [self.venue1.id]}})
        self.user_manager.get_filtered({'exact' : {'id' : learner1.id}}, ['id', 'session_user_role_requirements'])
        self.assertRaises(exceptions.PermissionDeniedException, self.assignment_manager.update, proctor_token, assignment_ret[learner1.id]['id'], {'status' : 'canceled'})


class TestSessionTemplateManager(GeneralTestCase):
    def test_create(self):
        prod = self.product_line_manager.create('Earn your MBA overnight!')
        ret = self.session_template_manager.create('name', 'longer name', '2.0', 'This is a description', 1595,
            600000, True, 'Self-Paced E-Learning', {'product_line' : prod.id})
        self.assertEquals(ret.shortname, 'name')
        self.assertEquals(ret.fullname, 'longer name')
        self.assertEquals(ret.version, '2.0')
        self.assertEquals(ret.active, True)
        self.assertEquals(ret.price, 1595)
        self.assertEquals(ret.product_line_id, prod.id)
        self.assertEquals(ret.modality, 'Self-Paced E-Learning')

    def test_update(self):
        session_template = self.session_template_manager.create('name', 'longer name', '2.0', 'This is a description', 1595,
            600000, True)
        self.session_template_manager.update(session_template.id, {'shortname' : 'a short name', 'fullname' : 'an even longer name',
            'version' : '2.1', 'description' : 'new description', 'price' : 2014, 'lead_time' : 2340322})
        self.session_template = SessionTemplate.objects.get(id=session_template.id)
        self.assertEquals(self.session_template.fullname, 'an even longer name')

    def test_update_by_pl(self):
        prod = self.product_line_manager.create('Earn your MBA overnight!')
        self.product_line_manager.create('Medical Basket Weaving')
        self.pl_user = self.user_manager.create('pl_session_template_creator', 'password',
            '', 'pl', 'session_template creator', '', '', 'active')
        self.product_line_manager.update(prod.id, {'managers' : [self.pl_user.id]})
        pl_token = facade.subsystems.Utils.get_auth_token_object(self.user_manager.login('pl_session_template_creator', 'password')['auth_token'])
        crs_1 = self.session_template_manager.create(pl_token, 'MBA2', 'macroeconomics and basket weaving', '2.0', 'This is a description', 1595, 600000, True,
            'Generic', {'product_line': str(prod.id)})
        self.session_template_manager.update(pl_token, str(crs_1.id), {'shortname':'MBA5'})
        crs_1 = SessionTemplate.objects.get(id=crs_1.id)
        self.assertEquals(crs_1.shortname, 'MBA5')
        self.session_template_manager.create('MBA2', 'fair trade and coffee', '0.8',
            'economics of fair trade applied to coffee beans', 1595, 600000, True)

    def test_get_filtered(self):
        session_template_1 = self.session_template_manager.create('name', 'longer name', '2.0',
            'This is a description', 1595, 600000, True)
        session_template_2 = self.session_template_manager.create('another name', 'another longer name',
            '2.1', 'This is a description', 1595, 600000, False)
        ret = self.session_template_manager.get_filtered({},
            ['id', 'fullname', 'active', 'price', 'version'])
        self.assertEquals(type(ret), list)
        self.assertEquals(len(ret), 2)
        self.assertEquals(type(ret[0]), dict)
        self.assertEquals(type(ret[1]), dict)
        self.failUnless(type(ret[1]['id']) in [int, long])

        for session_template in ret:
            if session_template['id'] == session_template_1.id:
                self.assertEquals(session_template['fullname'], 'longer name')
                self.assertEquals(session_template['active'], True)
                self.assertEquals(session_template['price'], 1595)
            elif session_template['id'] == session_template_2.id:
                self.assertEquals(session_template['fullname'], 'another longer name')
                self.assertEquals(session_template['active'], False)
            else:
                raise Exception('unexexpected primary key [' + session_template['id'] + ']')

    def test_delete(self):
        c1 = self.session_template_manager.create('name', 'longer name', '2.0', 'This is a description', 1595, 600000, True)
        self.session_template_manager.create('another name', 'another longer name', '2.1', 'This is a description', 1595, 600000, True)
        ret = self.session_template_manager.get_filtered({}, ['id'])
        self.assertEquals(type(ret), list)
        self.assertEquals(len(ret), 2)
        self.assertRaises(exceptions.PermissionDeniedException, self.session_template_manager.delete, self.user1_auth_token, c1.id)
        self.session_template_manager.delete(c1.id)
        ret = self.session_template_manager.get_filtered({'exact' : {'active' : True}}, ['id'])
        self.assertEquals(len(ret), 1)

    @expectPermissionDenied
    def test_create_permission_denied(self):
        self.session_template_manager.create('short_name', 'longer name', '1.1',
                'description', 1595, 600000, True, auth_token=None)

    def test_create_by_pl(self):
        prod = self.product_line_manager.create('Earn your MBA overnight!')
        prod_2 = self.product_line_manager.create('Medical Basket Weaving')
        self.pl_user = self.user_manager.create('pl_session_template_creator', 'password',
            '', 'pl', 'session_template creator', '', '', 'active')
        self.product_line_manager.update(prod.id, {'managers' : [self.pl_user.id]})
        pl_token = facade.subsystems.Utils.get_auth_token_object(self.user_manager.login('pl_session_template_creator', 'password')['auth_token'])
        self.session_template_manager.create(pl_token, 'MBA2', 'macroeconomics and basket weaving', '2.0', 'This is a description', 1595, 600000, True, 'ILT',
            {'product_line': str(prod.id)})
        self.assertRaises(exceptions.PermissionDeniedException, self.session_template_manager.create, pl_token,
            'MBA3', 'beansprouts and accountants: hidden truths and diets', '1.1',
            "see why CPA's like beansprouts but hate asparagus in this innovative seminar",
            10050, 240000, True)
        self.assertRaises(exceptions.PermissionDeniedException, self.session_template_manager.create, pl_token,
            'MBW0', 'basket weaving therapy for schizophrenia', '1.0',
            'seminar on an exciting new approach to therapy for schizophrenia',
            150034, 240000, True, 'Generic', {'product_line':str(prod_2.id)})

class TestSessionTemplateUserRoleRequirementManager(BasicTestCase):
    def setUp(self):
        super(TestSessionTemplateUserRoleRequirementManager, self).setUp()
        self.pl = self.product_line_manager.create('Earn your MBA overnight!')
        self.new_session_template = self.session_template_manager.create('name', 'longer name', '2.0',
            'This is a description', 1595, 600000, True, 'ILT', {'product_line' : self.pl.id})
        self.instructor_role = SessionUserRole.objects.get(name__exact='Instructor')
        self.student_role = SessionUserRole.objects.get(name__exact='Student')

    def test_creation(self):
        curr = self.session_template_user_role_requirement_manager.create(self.new_session_template.id,
            self.instructor_role.id, 1, 2, [])
        ret = self.session_template_user_role_requirement_manager.get_filtered({'exact':{'id':curr.id}},
            ['id', 'max'])
        self.assertEquals(type(ret), list)
        self.assertEquals(ret[0]['id'], curr.id)
        self.assertEquals(ret[0]['max'], 2)

class TestSessionUserRoleManager(GeneralTestCase):
    def test_update(self):
        session_user_role = self.session_user_role_manager.create('Sweep Upper')
        self.assertRaises(exceptions.PermissionDeniedException, self.session_user_role_manager.update, self.user1_auth_token, session_user_role.id,
            {'name' : 'Sweep It Upper'})
        self.session_user_role_manager.update(session_user_role.id, {'name' : 'Sweep It Upper'})
        session_user_roles = self.session_user_role_manager.get_filtered({'exact' : {'id' : session_user_role.id}}, ['id', 'name'])
        self.assertEquals(session_user_roles[0]['name'], 'Sweep It Upper')

class TestSessionUserRoleRequirementManager(GeneralTestCase):
    def setUp(self):
        super(TestSessionUserRoleRequirementManager, self).setUp()
        self.instructor_role = SessionUserRole.objects.get(name__exact='Instructor')
        self.student_role = SessionUserRole.objects.get(name__exact='Student')
        self.e1 = self.event_manager.create('Event 1', 'Event 1', 'Event 1', self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), self.organization1.id, {'venue' : self.venue1.id})
        self.session = self.session_manager.create(self.right_now.isoformat(),
            (self.right_now + self.one_day).isoformat(), 'active', False, 100, self.e1.id, 'short name 1', 'long name 1')

    def test_creation(self):
        surr = self.session_user_role_requirement_manager.create(self.session.id, self.instructor_role.id, 1,
            2, [])
        ret = self.session_user_role_requirement_manager.get_filtered({'exact':{'id':surr.id}}, ['id', 'max'])
        self.assertEquals(type(ret), list)
        self.assertEquals(ret[0]['id'], surr.id)
        self.assertEquals(ret[0]['max'], 2)

    def test_view(self):
        surr1 = self.session_user_role_requirement_manager.create(self.session.id, self.instructor_role.id, 1,
            2, [])
        self.session_user_role_requirement_manager.create(self.session.id, self.student_role.id, 1,
            2, [])
        ret = self.session_user_role_requirement_manager.surr_view(self.admin_token)
        self.assertEquals(type(ret), list)
        self.assertEquals(len(ret), 2)

        ret = self.session_user_role_requirement_manager.surr_view({'exact' : {'id' : surr1.id}})
        self.assertEquals(type(ret), list)
        self.assertEquals(len(ret), 1)
        self.assertEquals(ret[0]['id'], surr1.id)

class TestDomainManagement(GeneralTestCase):
    def test_affiliate_with_new_domain(self):
        student1, student1_at = self.user1, self.user1_auth_token
        student2, student2_at = self.user2, self.user2_auth_token

        testing_domain = self.domain_manager.create('Testing Domain')

        # user can associate self with another domain
        self.domain_affiliation_manager.create(student1_at, student1.id,
            testing_domain.id, 'student1')

        # user cannot associate someone else with another domain
        self.assertRaises(exceptions.PermissionDeniedException, self.domain_affiliation_manager.create, student1_at, student2.id,
            testing_domain.id, 'student2')


class TestTrainingUnitAccountManager(GeneralTestCase):
    def setUp(self):
        super(TestTrainingUnitAccountManager, self).setUp()
        self.c1 = self.organization_manager.create('ACME')
        self.po1 = self.purchase_order_manager.create(
            {'user' : self.user1.id, 'training_units_purchased' : 100, 'training_units_price' : 5000})
        self.tua1 = self.training_unit_account_manager.create(self.user1.id)
        self.tua1.starting_value = 200
        self.tua1.save()
        self.tuauth1 = self.training_unit_authorization_manager.create(self.tua1.id, self.user1.id,
            (self.right_now - self.one_day).isoformat(), (self.right_now + self.one_day).isoformat(), 10000)
        self.tuauth2 = self.training_unit_authorization_manager.create(self.tua1.id, self.user1.id,
            (self.right_now - self.one_day).isoformat(), (self.right_now + self.one_day).isoformat(), 2000)
        self.tut1 = self.training_unit_transaction_manager.create(self.tua1.id, 3500, self.po1.id)
        self.tut2 = self.training_unit_transaction_manager.create(self.tua1.id, -1800, self.po1.id,
            {'training_unit_authorizations' : {'add' : [self.tuauth1.id]}})
        self.tut3 = self.training_unit_transaction_manager.create(self.tua1.id, 5000, self.po1.id)
        self.tut4 = self.training_unit_transaction_manager.create(self.tua1.id, -2500, self.po1.id,
            {'training_unit_authorizations' : {'add' : [self.tuauth1.id]}})

    def test_create_accounts(self):
        tua2 = self.training_unit_account_manager.create(None, self.c1.id)
        self.assertEquals(self.tua1.blame.user_id, self.admin_token.user.id)
        self.assertEquals(tua2.organization.name, self.c1.name)

    def test_create_transactions(self):
        self.assertEquals(self.tut1.blame.user_id, self.admin_token.user.id)
        self.assertEquals(self.tut2.value, -1800)
        self.assertEquals(self.tut2.purchase_order, self.po1)
        res = self.training_unit_account_manager.get_filtered({'exact' : {'id' : self.tua1.id}}, ['id', 'balance'])
        self.assertEquals(res[0]['balance'], 4400)

    def test_training_unit_authorization(self):
        tuauths = self.training_unit_authorization_manager.get_filtered({},
            ['id', 'training_unit_account', 'user', 'used_value', 'max_value'])
        self.assertEquals(len(tuauths), 2)
        if tuauths[0]['id'] == self.tuauth1.id:
            one = 0
            two = 1
        else:
            one = 1
            two = 0
        self.assertEquals(tuauths[one]['id'], self.tuauth1.id)
        self.assertEquals(tuauths[one]['training_unit_account'], self.tua1.id)
        self.assertEquals(tuauths[one]['user'], self.user1.id)
        self.assertEquals(tuauths[one]['used_value'], 4300)
        self.assertEquals(tuauths[one]['max_value'], 10000)
        self.assertEquals(tuauths[two]['id'], self.tuauth2.id)
        self.assertEquals(tuauths[two]['used_value'], 0)
        self.assertEquals(tuauths[two]['max_value'], 2000)

        self.tuauth3 = self.training_unit_authorization_manager.create(self.tua1.id, self.admin_token.user.id,
            (self.right_now - self.one_day).isoformat(), (self.right_now + self.one_day).isoformat(), 2000)
        self.tuauth4 = self.training_unit_authorization_manager.create(self.tua1.id, self.user1.id,
            (self.right_now + self.one_day).isoformat(), (self.right_now + 2 * self.one_day).isoformat(), 2000)

        user_auths = self.training_unit_authorization_manager.get_filtered(self.user1_auth_token, {}, ['id', 'used_value', 'user'])
        self.assertEquals(len(user_auths), 3)
        ua1 = user_auths[0]
        self.assertEquals('used_value' in ua1, True)
        self.assertEquals(ua1['used_value'] == 4300 or ua1['used_value'] == 0, True)
        self.assertEquals('id' in ua1, True)

class TestTrainingVoucherManager(GeneralTestCase):
    def setUp(self):
        super(TestTrainingVoucherManager, self).setUp()
        self.e1 = self.event_manager.create('Event 1', 'Event 1', 'Event 1', self.right_now.isoformat(),
            (self.right_now+self.one_day).isoformat(), self.organization1.id, {'venue' : self.venue1.id})
        self.s1 = self.session_manager.create(self.right_now.isoformat(), (self.right_now + self.one_day).isoformat(), 'active',
            True, 100, self.e1.id, 'short name 1', 'long name 1')
        self.eur1 = self.session_user_role_manager.create('Fancy Job')
        self.eurr1 = self.session_user_role_requirement_manager.create(self.s1.id, self.eur1.id, 10, 20)
        self.po1 = self.purchase_order_manager.create(self.admin_token)

    def test_create(self):
        tv1 = self.training_voucher_manager.create(self.eurr1.id)
        voucher = self.training_voucher_manager.get_filtered({'exact' : {'id' : tv1.id}}, ['price', 'session_user_role_requirement',
            'code', 'id'])[0]
        self.assertEquals(voucher['price'], self.s1.default_price)
        self.assertEquals(voucher['session_user_role_requirement'], self.eurr1.id)
        code = voucher['code']
        self.assertEquals(len(code), 10)
        self.assertEquals(code.isalnum(), True)

        voucher = self.training_voucher_manager.get_voucher_by_code(code)
        self.assertEquals(voucher['id'], tv1.id)
        self.assertEquals(voucher['session_user_role_requirement'], tv1.session_user_role_requirement_id)

class TestOrganizationManager(BasicTestCase):
    def setUp(self):
        super(TestOrganizationManager, self).setUp()
        self.FILE_UPLOAD_MAX_MEMORY_SIZE = settings.FILE_UPLOAD_MAX_MEMORY_SIZE

    def tearDown(self):
        super(TestOrganizationManager, self).tearDown()
        settings.FILE_UPLOAD_MAX_MEMORY_SIZE = self.FILE_UPLOAD_MAX_MEMORY_SIZE

    def test_naming_restrictions(self):
        """
        Make sure we are correctly enforcing that 'name' and 'parent' are unique together.
        """
        org1 = self.organization_manager.create('Org 1')
        self.assertRaises(ModelDataValidationError, self.organization_manager.create, self.admin_token, 'Org 1')

        org2 = self.organization_manager.create('Org 2', {'parent' : org1.id})
        self.organization_manager.create('Sales Department', {'parent' : org1.id})
        self.assertRaises(ModelDataValidationError, self.organization_manager.create, self.admin_token, 'Sales Department', {'parent' : org1.id})
        self.organization_manager.create('Sales Department', {'parent' : org2.id})

    def test_admin_org_views(self):
        org1 = self.organization_manager.create('Org 1')
        org2 = self.organization_manager.create('Org 2', {'parent' : org1.id})
        org3 = self.organization_manager.create('Sales Department', {'parent' : org1.id})
        self.organization_manager.create('Sales Department', {'parent' : org2.id})

        orgrole1 = self.org_role_manager.create('Org Role 1')

        jerk = self.user_manager.create('george', 'initial_password', 'Mr.', 'first_name',
                           'last_name', '555.555.5555', 'foo@bar.org',
                           'active', {'organizations' : {'add' : [{'id' : org1.id, 'role' : orgrole1.id}]}})

        ret = self.organization_manager.admin_org_view(self.admin_token)

        for org in ret:
            if org['id'] == org1.id:
                self.assertEquals(len(org['user_org_roles']), 1)
                user_org_role = org['user_org_roles'][0]
                self.assertEquals(user_org_role['role'], orgrole1.id)
                self.assertEquals(user_org_role['role_name'], orgrole1.name)
            elif org['id'] == org3.id:
                self.assertEquals(org['parent'], org1.id)

        # make sure we can read the users
        ret = self.user_org_role_manager.user_org_role_detail_view({'exact' : {'organization' : org1.id}})

        self.assertEquals(len(ret), 1)
        user = ret[0]
        self.assertEquals(user['owner']['first_name'], jerk.first_name)
        self.assertEquals(user['owner']['last_name'], jerk.last_name)
        self.assertEquals(user['owner']['email'], jerk.email)
        self.assertEquals(user['role']['name'], orgrole1.name)

    def test_recursive_organizations(self):
        org1 = self.organization_manager.create('Org 1')
        org2 = self.organization_manager.create('Org 2', {'parent' : org1.id})
        org3 = self.organization_manager.create('Org 3', {'parent' : org1.id})
        org4 = self.organization_manager.create('Org 4', {'parent' : org2.id})
        org5 = self.organization_manager.create('Org 5', {'parent' : org2.id})
        org6 = self.organization_manager.create('Org 6', {'parent' : org4.id})

        orgs = self.organization_manager.get_filtered({'member' : {'id' : [org1.id, org2.id, org3.id, org4.id, org5.id, org6.id]}}, ['id', 'parent', 'children', 'ancestors', 'descendants'])

        self.assertTrue(len(orgs) == 6)
        for org in orgs:
            self.assertTrue('parent' in org)
            self.assertTrue('children' in org)
            self.assertTrue('ancestors' in org)
            self.assertTrue('descendants' in org)
            if org['id'] == org1.id:
                self.assertEquals(org['parent'], None)
                self.assertEquals(org['ancestors'], [])
                self.assertEquals(set(org['children']), set([org2.id, org3.id]))
                self.assertEquals(set(org['descendants']), set([org2.id, org3.id, org4.id, org5.id, org6.id]))
            elif org['id'] == org2.id:
                self.assertEquals(org['parent'], org1.id)
                self.assertEquals(org['ancestors'], [org1.id])
                self.assertEquals(set(org['children']), set([org4.id, org5.id]))
                self.assertEquals(set(org['descendants']), set([org4.id, org5.id, org6.id]))
            elif org['id'] == org3.id:
                self.assertEquals(org['parent'], org1.id)
                self.assertEquals(set(org['ancestors']), set([org1.id]))
                self.assertEquals(org['children'], [])
                self.assertEquals(org['descendants'], [])
            elif org['id'] == org4.id:
                self.assertEquals(org['parent'], org2.id)
                self.assertEquals(set(org['ancestors']), set([org1.id, org2.id]))
                self.assertEquals(org['children'], [org6.id])
                self.assertEquals(org['descendants'], [org6.id])
            elif org['id'] == org5.id:
                self.assertEquals(org['parent'], org2.id)
                self.assertEquals(set(org['ancestors']), set([org1.id, org2.id]))
                self.assertEquals(org['children'], [])
                self.assertEquals(org['descendants'], [])
            elif org['id'] == org6.id:
                self.assertEquals(org['parent'], org4.id)
                self.assertEquals(set(org['ancestors']), set([org1.id, org2.id, org4.id]))
                self.assertEquals(org['children'], [])
                self.assertEquals(org['descendants'], [])

    def test_create_organization(self):
        org_dict = {
            'phone' : '919-459-2491',
            'email' : 'info@testing.org',
            'description' : 'We rock',
            'primary_contact_first_name' : 'Paul',
            'primary_contact_last_name' : 'Krugman',
            'primary_contact_office_phone' : '919-123-4567',
            'primary_contact_cell_phone' : '919-234-5678',
            'primary_contact_other_phone' : '919-345-6789',
            'primary_contact_email' : 'pkrugman@testing.org',
            'url' : 'http://organization.testing.org',
        }

        org = self.organization_manager.create('Testing Organization', org_dict)

        photo_file_name = os.path.join(os.path.dirname(__file__), 'test_data/testimage.png')
        settings.FILE_UPLOAD_MAX_MEMORY_SIZE = os.path.getsize(photo_file_name) * 2

        the_org = self.organization_manager.get_filtered({'exact' : {'id' : org.id}}, ['photo_url'])[0]
        self.assertEquals(the_org['photo_url'], None)
        with open(photo_file_name, 'r') as photo_file:
            response = self.client.post('/upload/organization/photo', {'auth_token' : self.admin_token.session_id, 'organization_id' : the_org['id'],
                'photo' : photo_file})
            self.assertEquals(response.status_code, 200)

        requested_attributes = org_dict.keys()
        requested_attributes.extend(['photo_url'])

        the_org = self.organization_manager.get_filtered({'exact' : {'id' : org.id}}, requested_attributes)[0]
        self.assertEquals(the_org['photo_url'][-4:], '.png')
        self.assertEquals(the_org['phone'], org_dict['phone'])
        self.assertEquals(the_org['email'], org_dict['email'])
        self.assertEquals(the_org['description'], org_dict['description'])
        self.assertEquals(the_org['primary_contact_last_name'], org_dict['primary_contact_last_name'])
        self.assertEquals(the_org['primary_contact_cell_phone'], org_dict['primary_contact_cell_phone'])
        self.assertEquals(the_org['url'], org_dict['url'])


class TestOrgEmailDomainManager(GeneralTestCase):
    fixtures = ['precor_orgs', 'precor_org_roles'] + GeneralTestCase.fixtures

    def test_crud(self):
        email_domain = 'poweru.net'
        organization = Organization.objects.all()[0]
        default_org_role = OrgRole.objects.get(default=True)
        org_email_domain = self.org_email_domain_manager.create(email_domain, organization.id)
        self.assertEqual(org_email_domain.email_domain, email_domain)
        self.assertEqual(org_email_domain.organization, organization)
        self.assertEqual(org_email_domain.role, None)
        self.assertEqual(org_email_domain.effective_role, default_org_role)
        org_email_domain = self.org_email_domain_manager.get_filtered(
            {'exact': {'id': org_email_domain.id}},
            ['email_domain', 'organization', 'role', 'effective_role'])[0]
        self.assertEqual(org_email_domain['email_domain'], email_domain)
        self.assertEqual(org_email_domain['organization'], organization.id)
        self.assertEqual(org_email_domain.get('role'), None)
        self.assertEqual(org_email_domain['effective_role'], default_org_role.id)
        email_domain = 'americanri.com'
        org_role = OrgRole.objects.get(name='Administrator')
        org_email_domain = self.org_email_domain_manager.create(email_domain, organization.id, org_role.id)
        self.assertEqual(org_email_domain.role, org_role)
        self.assertEqual(org_email_domain.effective_role, org_role)
        org_email_domain = self.org_email_domain_manager.get_filtered(
            {'exact': {'id': org_email_domain.id}}, ['role', 'effective_role'])[0]
        self.assertEqual(org_email_domain['role'], org_role.id)
        self.assertEqual(org_email_domain['effective_role'], org_role.id)
        email_domain = 'americanri.com.ofc'
        self.org_email_domain_manager.update(org_email_domain['id'],
            {'email_domain': email_domain})
        org_email_domain = self.org_email_domain_manager.get_filtered(
            {'exact': {'id': org_email_domain['id']}}, ['email_domain'])[0]
        self.assertEqual(org_email_domain['email_domain'], email_domain)
        self.org_email_domain_manager.delete(org_email_domain['id'])
        self.assertEqual(self.org_email_domain_manager.get_filtered(
            {'exact': {'id': org_email_domain['id']}}, ['email_domain']), [])


class TestUploadManager(GeneralTestCase):
    def setUp(self):
        super(TestUploadManager, self).setUp()
        self.FILE_UPLOAD_MAX_MEMORY_SIZE = settings.FILE_UPLOAD_MAX_MEMORY_SIZE

    def tearDown(self):
        super(TestUploadManager, self).tearDown()
        settings.FILE_UPLOAD_MAX_MEMORY_SIZE = self.FILE_UPLOAD_MAX_MEMORY_SIZE


    def _upload_user_photo(self, photo_file_name):
        the_user = self.admin_token.user
        the_user = self.user_manager.get_filtered({'exact' : {'id' : the_user.id}}, ['photo_url'])[0]
        self.assertEquals(the_user['photo_url'], None)
        with open(photo_file_name, 'r') as photo_file:
            response = self.client.post('/upload/user/photo', {'auth_token' : self.admin_token.session_id, 'user_id' : the_user['id'],
                'photo' : photo_file})
            self.assertEquals(response.status_code, 200)
        the_user = self.user_manager.get_filtered({'exact' : {'id' : the_user['id']}}, ['photo_url'])[0]
        self.assertEquals(the_user['photo_url'][-4:], '.png')

    def test_upload_user_photo(self):
        photo_file_name = os.path.join(os.path.dirname(__file__), 'test_data/testimage.png')
        settings.FILE_UPLOAD_MAX_MEMORY_SIZE = os.path.getsize(photo_file_name) * 2
        self._upload_user_photo(photo_file_name)

    def test_upload_large_user_photo(self):
        # Test with a photo larger than the max memory size for file uploads
        photo_file_name = os.path.join(os.path.dirname(__file__), 'test_data/testimage.png')
        settings.FILE_UPLOAD_MAX_MEMORY_SIZE = os.path.getsize(photo_file_name) / 2
        self._upload_user_photo(photo_file_name)

    def test_upload_corrupt_image(self):
        image_file = os.path.join(os.path.dirname(__file__), 'test_data/corrupt.jpg')
        settings.FILE_UPLOAD_MAX_MEMORY_SIZE = os.path.getsize(image_file) * 2
        self.assertRaises(ModelDataValidationError, self._upload_user_photo, image_file)

class TestUserManager(GeneralTestCase):

    fixtures = ['precor_orgs', 'precor_org_roles'] + GeneralTestCase.fixtures

    def test_addresses(self):
        self.auth_token = self.user1_auth_token
        um = self.user_manager
        um.update(self.user1.id,
                {'shipping_address':
                    {'country': 'US',
                     'label': '4379 Mind If I Do A J Dr.',
                     'region': 'CA',
                     'locality': 'Los Angeles',
                     'postal_code': '63485'
                    }})
        ret = um.get_filtered({'exact': {'id': self.user1.id}},
                ['shipping_address', 'id'])[0]
        self.assertEquals(ret['shipping_address']['label'], '4379 Mind If I Do A J Dr.')

    def test_authenticate_bad_password(self):
        self.assertRaises(exceptions.AuthenticationFailureException,
                          self.user_manager.login, 'user1', 'bad_password')

    def test_authenticate_invalid_username(self):
        # we don't let the client know that the username2 was invalid
        # to mitigate risk of brute-force attacks that guess usernames
        self.assertRaises(exceptions.AuthenticationFailureException,
                          self.user_manager.login, 'some_other_user', 'password')

    def test_authenticate_successful_authentication(self):
        auth_token_str = self.user_manager.login('user2', 'password')['auth_token']
        # make sure that a new auth_token structure exists in the db
        auth_token_entry = facade.subsystems.Utils.get_auth_token_object(auth_token_str)
        self.assertEquals(str(auth_token_entry), auth_token_str)
        self.assertEquals(unicode(auth_token_entry), u'%s' % (auth_token_str))
        # now make sure that the user is correctly associated with the auth token
        da = DomainAffiliation.objects.get(username='user2', domain__name='local')
        self.assertEquals(auth_token_entry.user, da.user)

    def test_batch_create(self):
        res = self.user_manager.batch_create(
            [{'username' : 'hoot', 'initial_password' : 'rock', 'title' : 'Ma\'am', 'first_name' : 'Ma\'am', 'last_name' : 'Ma\'am',
            'phone' : '123-455-6789', 'email' : 'hoot@boot.com', 'status' : 'active'}])
        user_made = User.objects.filter(id = res.keys()[0])[0]
        self.assertEquals(user_made.blame.user, self.admin_token.user)

    def test_change_password(self):
        change_pwd = self.user_manager.change_password

        self.assertRaises(exceptions.AuthenticationFailureException, change_pwd,
                self.user1.id, 'password2', 'password3')

        change_pwd(self.user1_auth_token, self.user1.id, 'password2', 'password')
        da = DomainAffiliation.objects.get(username='user1', domain__name='local')
        self.assertEquals(facade.subsystems.Utils._hash('password2' + da.password_salt, 'SHA-512'), da.password_hash)

        change_pwd(self.user1.id, 'password3', 'password2', auth_token=None)
        da = DomainAffiliation.objects.get(id=da.id)
        self.assertEquals(facade.subsystems.Utils._hash('password3' + da.password_salt, 'SHA-512'), da.password_hash)

        # Make sure we raise an exception if the user is set for foreign authentication
        da.domain = Domain.objects.get(name='LDAP')
        da.save()
        self.assertRaises(exceptions.CannotChangeForeignPasswordException,
                change_pwd, self.user1.id, 'password4', 'password2', 'LDAP')

    def test_create(self):
        ret = self.user_manager.create('username2', 'initial_password', 'Mr.',
            'first_name', 'last_name', '555.555.5555', 'foo@bar.org', 'pending',
            {'name_suffix' : 'Jr.', 'url' : 'http://somejunkyandfakeurlthatshouldnotbreakpowerreg.net/',
            'alleged_organization': 'Moustache Club of America'},
            auth_token=None)
        new_user = User.objects.get(id=ret.id)
        da = DomainAffiliation.objects.get(user__id=ret.id, domain__name='local')
        new_user = da.user
        self.assertEquals(da.username, 'username2')
        self.assertEquals(new_user.title, 'Mr.')
        self.assertEquals(new_user.first_name, 'first_name')
        self.assertEquals(new_user.last_name, 'last_name')
        self.assertEquals(new_user.name_suffix, 'Jr.')
        self.assertEquals(new_user.phone, '555.555.5555')
        self.assertEquals(new_user.email, 'foo@bar.org')
        self.assertEquals(new_user.status, 'pending')
        self.assertEquals(da.password_hash_type, 'SHA-512')
        self.assertEquals(new_user.blame.user, new_user)
        self.assertEquals(new_user.url, 'http://somejunkyandfakeurlthatshouldnotbreakpowerreg.net/')
        self.assertEquals(new_user.alleged_organization, 'Moustache Club of America')
        s = hashlib.sha512()
        s.update('initial_password'+da.password_salt)
        self.assertEquals(da.password_hash, s.hexdigest())
        optionalEmailUser = self.user_manager.create('ringo', 'myBrain', 'Mr.', 'Ringo', 'Starr',
                           '123.456.7890', 'ringo@starr.com', 'active',
                           {'email2' : 'ringo2@starr.com'})
        self.assertEquals(optionalEmailUser.email2, 'ringo2@starr.com')
        optionalPhoneUser = self.user_manager.create('ringop', 'myBrainp', 'Mr.', 'Ringo', 'Starr',
                            '123.456.7890', 'ringo@starr.com', 'active',
                            {'email2' : 'ringo2@starr.com', 'phone2' : '124.642.3476',
                            'phone3' : '919-123-4567'})
        self.assertEquals(optionalPhoneUser.email2, 'ringo2@starr.com')
        self.assertEquals(optionalPhoneUser.phone2, '124.642.3476')
        self.assertEquals(optionalPhoneUser.phone3, '919-123-4567')

    def test_create_duplicate(self):
        self.assertRaises(Exception, self.user_manager.create,
                          'user1', 'initial_password', 'Mr.', 'first_name',
                          'last_name', '555.555.5555', 'foo@bar.org', 'active',
                          auth_token=None)

    def test_create_with_organization_from_email(self):
        # Test user creation with the organization and role assigned based on
        # the email domain.
        organization = Organization.objects.all()[0]
        default_org_role = OrgRole.objects.get(default=True)
        self.org_email_domain_manager.create('poweru.net', organization.id)
        org_role = OrgRole.objects.get(name='Administrator')
        self.org_email_domain_manager.create('americanri.com', organization.id, org_role.id)
        settings.USER_EMAIL_CONFIRMATION = True
        settings.USER_CONFIRMATION_AUTO_LOGIN = True
        settings.ASSIGN_ORG_ROLES_FROM_EMAIL = True
        user = self.user_manager.create('george', 'initial_password', 'Mr.', 'first_name', 'last_name',
                      '555.555.5555', 'george@poweru.net', 'pending',
                      auth_token=None)
        at = self.user_manager.confirm_email(user.confirmation_code)
        ret = self.user_manager.get_filtered(at, {'exact' : {'id' : user.id}}, ['organizations'])
        self.assertEquals(len(ret[0]['organizations']), 1)
        user_org_role = UserOrgRole.objects.get(owner__id=user.id)
        self.assertEqual(user_org_role.organization, organization)
        self.assertEqual(user_org_role.role, default_org_role)
        user = self.user_manager.create('arigeorge', 'initial_password', 'Mr.', 'first_name', 'last_name',
                      '555.555.5555', 'george@americanri.com', 'pending',
                      auth_token=None)
        at = self.user_manager.confirm_email(user.confirmation_code)
        ret = self.user_manager.get_filtered(at, {'exact' : {'id' : user.id}}, ['organizations'])
        self.assertEquals(len(ret[0]['organizations']), 1)
        user_org_role = UserOrgRole.objects.get(owner__id=user.id)
        self.assertEqual(user_org_role.organization, organization)
        self.assertEqual(user_org_role.role, org_role)
        settings.ASSIGN_ORG_ROLES_FROM_EMAIL = False
        user = self.user_manager.create('georgia', 'initial_password', 'Mrs.', 'first_name', 'last_name',
                      '555.555.5555', 'georgia@poweru.net', 'pending',
                      auth_token=None)
        at = self.user_manager.confirm_email(user.confirmation_code)
        ret = self.user_manager.get_filtered(at, {'exact' : {'id' : user.id}}, ['organizations'])
        self.assertEquals(ret[0]['organizations'], [])
        self.assertEqual(UserOrgRole.objects.filter(owner__id=user.id).count(), 0)
        user = self.user_manager.create('arigeorgia', 'initial_password', 'Mrs.', 'first_name', 'last_name',
                      '555.555.5555', 'georgia@americanri.com', 'pending',
                      auth_token=None)
        at = self.user_manager.confirm_email(user.confirmation_code)
        ret = self.user_manager.get_filtered(at, {'exact' : {'id' : user.id}}, ['organizations'])
        self.assertEquals(ret[0]['organizations'], [])
        self.assertEqual(UserOrgRole.objects.filter(owner__id=user.id).count(), 0)

    def test_user_email_confirmation(self):
        # Test normal user creation, confirmation and login.
        settings.USER_EMAIL_CONFIRMATION = True
        settings.USER_CONFIRMATION_AUTO_LOGIN = True
        settings.USER_CONFIRMATION_DAYS = 7
        org = self.organization_manager.create(
            'Bar Corporation')
        self.org_email_domain_manager.create(
            self.admin_token, 'bar.org', org.id)
        u = self.user_manager.create('user1234', 'initial_password', 'Mr.',
                                     'first_name', 'last_name', '555.555.5555',
                                     'foo@bar.org', 'pending', auth_token=None)
        self.assertTrue(u.confirmation_code)
        self.assertEqual(len(mail.outbox), 1)
        mess = mail.outbox[0]
        self.assertEqual(mess.subject,
            u'Congratulations and welcome to Precor Experience')
        self.assertTrue(
            django.utils.dateformat.format(date.today(), settings.DATE_FORMAT)
            in mess.body)
        self.assertTrue('Mr. first_name last_name' in mess.body)
        self.assertTrue('Bar Corporation' in mess.body)
        self.assertTrue(u.confirmation_code in mess.body)
        self.assertRaises(exceptions.UserConfirmationException,
                          self.user_manager.login, 'user1234', 'initial_password')
        auth_token = self.user_manager.confirm_email(u.confirmation_code)
        self.assertTrue(auth_token)
        self.assertRaises(exceptions.UserConfirmationException,
                          self.user_manager.confirm_email, u.confirmation_code)
        self.user_manager.relogin(auth_token)
        self.user_manager.logout(auth_token)
        self.user_manager.login('user1234', 'initial_password')
        # Test confirm_email view with normal creation and login.
        u = self.user_manager.create('user0123', 'initial_password', 'Mr.',
                                     'first_name', 'last_name', '555.555.5555',
                                     'foo0@bar.org', 'pending', auth_token=None)
        self.assertFalse('authToken' in self.client.cookies)
        url = reverse('confirm_email', args=[u.confirmation_code])
        response = self.client.get(url, follow=False)
        self.assertEquals(response.status_code, 302)
        self.assertEquals(response['Location'], settings.FRONTEND_URL)
        self.assertTrue('authToken' in self.client.cookies)
        auth_token = self.utils.get_auth_token_object(self.client.cookies['authToken'].value)
        self.user_manager.relogin(auth_token)
        self.user_manager.logout(auth_token)
        self.user_manager.login('user0123', 'initial_password')
        del self.client.cookies['authToken']
        url = reverse('confirm_email', args=[u.confirmation_code])
        response = self.client.get(url, follow=True)
        self.assertEquals(response.status_code, 400) # bad request
        # Test without the auto-login after confirmation.
        settings.USER_CONFIRMATION_AUTO_LOGIN = False
        u = self.user_manager.create('user2345', 'initial_password', 'Mr.',
                                     'first_name', 'last_name', '555.555.5555',
                                     'foo2@bar.org', 'pending', auth_token=None)
        auth_token = self.user_manager.confirm_email(u.confirmation_code)
        self.assertFalse(auth_token)
        self.user_manager.login('user2345', 'initial_password')
        # Test the view without the auto-login.
        u = self.user_manager.create('user2354', 'initial_password', 'Mr.',
                                     'first_name', 'last_name', '555.555.5555',
                                     'foo2a@bar.org', 'pending', auth_token=None)
        self.assertFalse('authToken' in self.client.cookies)
        url = reverse('confirm_email', args=[u.confirmation_code])
        response = self.client.get(url, follow=False)
        self.assertEquals(response.status_code, 302)
        self.assertEquals(response['Location'], settings.FRONTEND_URL)
        self.assertFalse('authToken' in self.client.cookies)
        self.user_manager.login('user2354', 'initial_password')
        # Test the confirmation code expiration period.
        settings.USER_CONFIRMATION_DAYS = 0
        u = self.user_manager.create('user3456', 'initial_password', 'Mr.',
                                     'first_name', 'last_name', '555.555.5555',
                                     'foo3@bar.org', 'pending', auth_token=None)
        self.assertRaises(exceptions.UserConfirmationException,
                          self.user_manager.confirm_email, u.confirmation_code)
        self.assertRaises(exceptions.UserConfirmationException,
                          self.user_manager.login, 'user3456', 'initial_password')
        url = reverse('confirm_email', args=[u.confirmation_code])
        response = self.client.get(url, follow=True)
        self.assertEquals(response.status_code, 400) # bad request
        # Test with user email confirmation turned off.
        settings.USER_EMAIL_CONFIRMATION = False
        u = self.user_manager.create('user4567', 'initial_password', 'Mr.',
                                     'first_name', 'last_name', '555.555.5555',
                                     'foo4@bar.org', 'pending', auth_token=None)
        self.assertFalse(u.confirmation_code)
        self.user_manager.login('user4567', 'initial_password')

    def test_find_by_id(self):
        self.assertEquals(self.user_manager._find_by_id(self.user1.id),
                self.user1)

    def test_find_da_by_username(self):
        da = self.user_manager._find_da_by_username('user2', 'local')
        self.assertEquals(da.user, self.user2)

    def test_get_filtered(self):
        ret = self.user_manager.get_filtered({}, ['id', 'first_name'])
        self.assertEquals(type(ret), list)
        # The setup fixture creates five users
        self.assertEquals(len(ret), 5)
        self.assertEquals(type(ret[2]), dict)
        self.assertEquals(type(ret[3]), dict)
        self.assertIn(type(ret[3]['id']), [int, long])
        # we didn't ask for the 'last_name' value, make sure it's not present
        self.assertNotIn('last_name', ret[3])

    def test_hash_migration_from_sha1_to_sha512(self):
        da = DomainAffiliation.objects.get(user__id=self.user1.id, domain__name='local')
        # We used to use the sha library.  Now we use hashlib.  This unit test is an attempt to test what happens when a user migrates
        # from one environment to the other.  The password hash below was generated using the following commented code, which is being kept as an example:
        #
        # import sha
        # s = sha.new()
        # s.update('initial_password')
        # new_user.password_hash = s.hexdigest()
        da.password_hash = '949856ddb388cffe39fad226906d390ee1928c94'
        da.password_hash_type = 'SHA-1'
        da.password_salt = None
        da.save()
        # Let's make sure that failing authentication doesn't set the password or update the user
        self.assertRaises(exceptions.AuthenticationFailureException, self.user_manager.login, 'user1', 'wrong_password')
        da = DomainAffiliation.objects.get(user__id=self.user1.id, domain__name='local')
        self.assertEquals(da.password_hash, '949856ddb388cffe39fad226906d390ee1928c94')
        self.assertEquals(da.password_hash_type, 'SHA-1')
        self.assertTrue(da.password_salt in [None, ''])
        # The user user should be able to get an AuthToken by logging in
        auth_token = AuthToken.objects.get(session_id=self.user_manager.login('user1', 'initial_password')['auth_token'])
        # Let's have them log out and re-login to see if everything still works
        self.user_manager.logout(auth_token)
        self.user_manager.login('user1', 'initial_password')
        self.assertRaises(exceptions.AuthenticationFailureException, self.user_manager.login, 'user1', 'wrong_password')
        da = DomainAffiliation.objects.get(user__id=self.user1.id, domain__name='local')
        new_hash = hashlib.sha512()
        self.assertEquals(len(da.password_salt), 8) # Make sure the user now has a password salt
        new_hash.update('initial_password' + da.password_salt)
        self.assertEquals(da.password_hash_type, 'SHA-512') # Make sure the new user's hash type is now SHA-512
        self.assertEquals(da.password_hash, new_hash.hexdigest())

    def test_instructor_can_read_student(self):
        """
        Ensure that instructors can read some information about students.
        Also, ensure that students cannot read instructors, or other students.
        """
        create_surr = self.session_user_role_requirement_manager.create
        get_sur = self.session_user_role_manager.get_filtered
        get_users = self.user_manager.get_filtered
        get_groups = self.group_manager.get_filtered

        student1, student1_at = self.user1, self.user1_auth_token
        student2, student2_at = self.user2, self.user2_auth_token
        instructor, instructor_at = self.user3, self.user3_auth_token

        instructor_gid = get_groups({'exact': {'name': 'Instructors'}})[0]['id']
        self.user_manager.update(instructor.id, {'groups': {'add': [instructor_gid]}})

        boring_session_template = self.session_template_manager.create(
            'boringAsItGets', 'Boring As It Gets!', '1',
            'The purpose of this session_template is for the instructor to gain ' +\
            'experience in the important task of boring the snott out of students',
            5555555, 9, True)
        e1 = self.event_manager.create('Event 1', 'Event 1', 'Event 1',
            self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(),
            self.organization1.id, {'venue' : self.venue1.id})

        boring_session = self.session_manager.create(
            self.right_now.isoformat(), (self.right_now+self.one_day).isoformat(),
            'active', True, 23456, e1.id, 'short name 1', 'long name 1',
            {'session_template' : boring_session_template.id})


        instructor_role = get_sur({'exact' : {'name' :'Instructor'}}, ['id'])[0]
        self.assertIn('id', instructor_role)

        student_role = get_sur({'exact' : {'name' :'Student'}}, ['id'])[0]
        self.assertIn('id', student_role)

        instructor_surr =  create_surr(boring_session.id, instructor_role['id'], 1, 1)
        student_surr = create_surr(boring_session.id, student_role['id'], 1, 2)

        self.assignment_manager.bulk_create(instructor_surr.id, [instructor.id])
        self.assignment_manager.bulk_create(student_surr.id, [student1.id, student2.id])
        # Now the instructor should be able to see some things about the user, like their email address
        student_query = get_users(instructor_at, {'exact' : {'id' : student1.id}}, ['id', 'email'])
        self.assertIn('email', student_query[0])
        self.assertEquals(student_query[0]['email'], self.user1.email)
        # Students should not be able to see each other's information, like email address
        student_query = get_users(student2_at, {'exact' : {'id' : student1.id}}, ['id', 'email'])
        self.assertNotIn('email', student_query[0])
        # Students should not be able to see the instructors information,
        # like email address (actually, we may want this, but this is to test the method
        # that checks to see if an instructor is an instructor of a student.  It seems
        # to work properly, so we may need to remove this test if we want
        # users to be able to see more information about their instructors, like email addresses)
        instructor_query = get_users(student2_at, {'exact' : {'id' : instructor.id}}, ['id', 'email'])
        self.assertTrue('email' not in instructor_query)

    def test_invalid_field(self):
        self.assertRaises(exceptions.FieldNameNotFoundException,
                self.user_manager.update, self.user1.id,
                {'foo' : 'You can\'t set foo, foo!'})
        self.assertRaises(exceptions.FieldNameNotFoundException,
                self.user_manager.get_filtered, {'exact': {'id': self.user1.id}},
                ['foo'])

    def test_renew_authentication(self):
        admin_group = Group.objects.get(name='Super Administrators')
        admin_group.users.add(self.user1)
        ret1 = self.user_manager.login('user1', 'password')
        for key in ['auth_token', 'username', 'expiration', 'id', 'groups']:
            self.assertIn(key, ret1)
        self.assertEquals(ret1['id'], self.user1.id)
        self.assertEquals(ret1['domain'], 'local')
        self.assertEquals(ret1['groups'], [{'id':admin_group.id, 'name':admin_group.name},])
        self.assertEquals(ret1['title'], 'Mr.')
        self.assertEquals(ret1['first_name'], 'Primo')
        self.assertEquals(ret1['last_name'], 'Uomo')
        self.assertEquals(ret1['email'], self.user1.email)
        self.assertEquals(ret1['phone'], self.user1.phone)
        self.assertEquals(ret1['username'], self.user1.domain_affiliations.all()[0].username)
        auth_token1 = facade.subsystems.Utils.get_auth_token_object(ret1['auth_token'])
        auth_token2 = facade.subsystems.Utils.get_auth_token_object(self.user_manager.relogin(auth_token1)['auth_token'])
        self.assertEquals(auth_token1.number_of_renewals, auth_token2.number_of_renewals)
        self.assertEquals(auth_token1.number_of_renewals, 1)
        self.assertRaises(exceptions.AuthenticationFailureException,
            self.user_manager.relogin, 'this_is_not_a_valid_auth_token')

        auth_token2.time_of_expiration = datetime.utcnow() - timedelta(hours=1)
        auth_token2.save()
        self.assertRaises(exceptions.AuthenticationFailureException,
            self.user_manager.relogin, auth_token2)

    def test_unauthenticate(self):
        auth_token_str = self.user_manager.login('user1', 'password')['auth_token']
        # make sure that a new auth_token structure exists in the db
        get_auth_token_object = facade.subsystems.Utils.get_auth_token_object
        auth_token_entry = get_auth_token_object(auth_token_str)
        self.assertEquals(str(auth_token_entry.session_id), auth_token_str)
        self.assertEquals(unicode(auth_token_entry), u'%s' % (auth_token_str))
        # now make sure that the user is correctly associated with the auth token
        self.assertEquals(auth_token_entry.user, self.user1)
        self.user_manager.logout(auth_token_entry)
        self.assertRaises(exceptions.NotLoggedInException,
                get_auth_token_object, auth_token_str)

    def test_modify_self(self):
        change_password = self.user_manager.change_password
        change_password(self.user1_auth_token, self.user1.id, 'you', 'password')
        self.assertRaises(exceptions.PermissionDeniedException, change_password,
                self.user1_auth_token, self.user2.id, 'woman')
        change_password(self.user2.id, 'woman')

    def test_modify_someone_else_without_permission(self):
        self.assertRaises(exceptions.PermissionDeniedException,
                self.user_manager.update, self.user1_auth_token, self.user3.id,
                {'first_name': 'Secret Agent'})
        res = self.user_manager.get_filtered(self.user2_auth_token,
                {'exact' : {'id' : self.user2.id}},
                ['id', 'first_name'])
        self.assertEquals(res[0]['first_name'], 'Secundo')

    def test_read_someone_else_without_permission(self):
        self.auth_token = self.user1_auth_token
        get_filtered = self.user_manager.get_filtered
        res = get_filtered({}, ['last_name', 'id'])
        self.assertEquals(len(res), 5)
        last_names = []
        for user in res:
            if user.has_key('last_name'):
                last_names.append(user['last_name'])
        self.assertIn('Uomo', last_names)
        res = get_filtered({'exact' : {'id' : self.user2.id}}, ['id', 'first_name'])
        self.assertEquals(len(res), 1)
        self.assertEquals(res[0]['id'], self.user2.id)
        self.assertTrue('first_name' not in res[0])

    def test_delete(self):
        self.assertRaises(exceptions.OperationNotPermittedException,
                self.user_manager.delete, self.user1_auth_token, self.user1.id)

    def test_deactivate(self):
        self.user_manager._deactivate(self.admin_token, self.user1.id)
        george = DomainAffiliation.objects.get(username='user1', domain__name='local').user
        self.assertEquals(george.status, 'inactive')
        # test deactivation of a non-existent user
        self.assertRaises(exceptions.ObjectNotFoundException, self.user_manager._deactivate,
                          self.admin_token, 57)
        # test deactivation of a user who's already deactivated
        self.user_manager._deactivate(self.admin_token, self.user1.id)

    def test_update(self):
        self.user_manager.get_filtered({'exact' : {'id' : self.user1.id}}, ['first_name'])[0]['first_name']
        self.user_manager.update(self.user1.id, {'first_name' : 'thisisaterriblefirst_name'})
        new_first_name = self.user_manager.get_filtered({'exact' : {'id' : self.user1.id}}, ['first_name'])[0]['first_name']
        self.assertEquals(new_first_name, 'thisisaterriblefirst_name')

    def test_user_org_roles(self):
        role = self.org_role_manager.create('arole')
        role2 = self.org_role_manager.create('anotherrole')
        org = self.organization_manager.create('anorg')
        org2 = self.organization_manager.create('anotherorg')
        user, user_at = self.user1, self.user1_auth_token
        user2, user2_at = self.user2, self.user2_auth_token
        self.user_manager.update(user.id,
            {'roles' : {'add' : [{'id' : role.id, 'organization' : org}]}})
        result = self.org_role_manager.get_filtered(
            {'exact' : {'id': role.id}},
            ['users', 'organizations', 'user_org_roles'])[0]
        self.assertEqual(len(result['organizations']), 1)
        self.assertEqual(result['organizations'][0], org.id)
        self.assertEqual(len(result['users']), 1)
        self.assertEqual(result['users'][0], user.id)
        self.assertEqual(len(result['user_org_roles']), 1)
        result = self.organization_manager.get_filtered(
            {'exact' : {'id': org.id}},
            ['users', 'roles', 'user_org_roles'])[0]
        self.assertEqual(len(result['roles']), 1)
        self.assertEqual(result['roles'][0], role.id)
        self.assertEqual(len(result['users']), 1)
        self.assertEqual(result['users'][0], user.id)
        self.assertEqual(len(result['user_org_roles']), 1)
        result = self.user_manager.get_filtered(
            {'exact' : {'id': user.id}},
            ['organizations', 'roles', 'owned_userorgroles'])[0]
        self.assertEqual(len(result['roles']), 1)
        self.assertEqual(result['roles'][0], role.id)
        self.assertEqual(len(result['organizations']), 1)
        self.assertEqual(result['organizations'][0], org.id)
        self.assertEqual(len(result['owned_userorgroles']), 1)
        result = self.user_org_role_manager.get_filtered({})
        self.assertEqual(len(result), 1)
        # now let's see what the user himself can see
        result = self.user_manager.get_filtered(user_at,
            {'exact' : {'id': user.id}},
            ['organizations', 'roles', 'owned_userorgroles'])[0]
        self.assertEqual(len(result['roles']), 1)
        self.assertEqual(result['roles'][0], role.id)
        self.assertEqual(len(result['organizations']), 1)
        self.assertEqual(result['organizations'][0], org.id)
        self.assertEqual(len(result['owned_userorgroles']), 1)
        result = self.organization_manager.get_filtered(user_at,
            {'exact' : {'id': org.id}},
            ['name', 'parent', 'children', 'ancestors', 'descendants'])[0]
        self.assertEqual(result['name'], org.name)
        for k in ['parent', 'children', 'ancestors', 'descendants']:
            self.assertTrue(k in result)
        result = self.organization_manager.get_filtered(user_at,
            {'exact' : {'id': org2.id}},
            ['name', 'parent', 'children', 'ancestors', 'descendants'])[0]
        self.assertEqual(result['name'], org2.name)
        for k in ['parent', 'children', 'ancestors', 'descendants']:
            self.assertTrue(k in result)
        result = self.org_role_manager.get_filtered(user_at, {}, ['name'])
        result = [x['name'] for x in result]
        self.assertTrue(role.name in result)
        self.assertTrue(role2.name in result)
        result = self.user_org_role_manager.get_filtered(user_at, {})
        self.assertEqual(len(result), 1)
        # now let's see what an unrelated user can see
        result = self.user_manager.get_filtered(user2_at,
            {'exact' : {'id': user.id}},
            ['organizations', 'roles', 'owned_userorgroles'])[0]
        self.assertEqual(result.keys(), ['id'])
        result = self.user_org_role_manager.get_filtered(user2_at, {})
        self.assertEqual(len(result), 0)
        # now let's delete the UserOrgRole
        todel = self.user_org_role_manager.get_filtered({})
        self.user_org_role_manager.delete(todel[0]['id'])
        # and try all the other ways of creating and deleting them
        result = self.user_manager.update(user.id,
            {'organizations' : {'add' : [{'id' : org.id, 'role' : role}]}})
        self.user_org_role_manager.delete(result.owned_userorgroles.all()[0].id)
        result = self.organization_manager.update(org.id,
            {'users' : {'add' : [{'id' : user.id, 'role' : role}]}})
        self.user_org_role_manager.delete(result.user_org_roles.all()[0].id)
        result = self.organization_manager.update(org.id,
            {'roles' : {'add' : [{'id' : role.id, 'owner' : user}]}})
        self.user_org_role_manager.delete(result.user_org_roles.all()[0].id)
        result = self.org_role_manager.update(role.id,
            {'users' : {'add' : [{'id' : user.id, 'organization' : org}]}})
        self.user_org_role_manager.delete(result.user_org_roles.all()[0].id)
        result = self.org_role_manager.update(role.id,
            {'organizations' : {'add' : [{'id' : org.id, 'owner' : user}]}})
        self.user_org_role_manager.delete(result.user_org_roles.all()[0].id)
        # now let's try to add a user to an org with the default role
        self.user_manager.update(user.id,
            {'organizations' : {'add' : [org.id]}})
        result = self.user_org_role_manager.get_filtered(
            {}, ['role', 'owner', 'organization'])[0]
        self.assertEqual(result['owner'], user.id)
        self.assertEqual(result['organization'], org.id)
        uorid = result['id']
        result = self.org_role_manager.get_filtered(
            {'exact' : {'id' : result['role']}}, ['name'])[0]
        self.assertEqual(result['name'], 'User')
        self.user_org_role_manager.delete(uorid)
        # now let's try to link 2 UserOrgRoles through the parent relation
        result = self.user_manager.update(user.id,
            {'roles' : {'add' : [{'id' : role.id, 'organization' : org}]}})
        uor = result.owned_userorgroles.all()[0]
        result = self.user_manager.update(user2.id,
            {'roles' : {'add' : [{'id' : role.id, 'organization' : org}]}})
        uor2 = result.owned_userorgroles.all()[0]
        self.user_org_role_manager.update(
            uor2.id, {'parent' : uor.id})
        result = self.user_org_role_manager.get_filtered(
            {'exact' : {'id' : uor.id}}, ['parent', 'children'])[0]
        self.assertEqual(result['parent'], None)
        self.assertEqual(len(result['children']), 1)
        self.assertTrue(uor2.id in result['children'])
        result = self.user_org_role_manager.get_filtered(
            {'exact' : {'id' : uor2.id}}, ['parent', 'children'])[0]
        self.assertEqual(result['parent'], uor.id)
        self.assertEqual(len(result['children']), 0)

    def test_password_policy(self):
        self.user_manager.check_password_against_policy('a')
        self.assertRaises(exceptions.PasswordPolicyViolation,
            self.user_manager.check_password_against_policy, '')

    def test_get_users_by_group_name(self):
        group1 = Group.objects.create(name='Jerks')
        jerk = self.user_manager.create('george', 'initial_password', 'Mr.', 'first_name',
                           'last_name', '555.555.5555', 'foo@bar.org',
                           'active', {'groups':[group1.id]})

        ret = self.user_manager.get_users_by_group_name(group1.name, ['first_name', 'last_name', 'email'])
        self.assertEquals(len(ret), 1)
        self.assertTrue('id' in ret[0])
        self.assertTrue('first_name' in ret[0])
        self.assertTrue('last_name' in ret[0])
        self.assertTrue('email' in ret[0])
        self.assertEquals(ret[0]['id'], jerk.id)
        self.assertEquals(ret[0]['first_name'], jerk.first_name)
        self.assertEquals(ret[0]['last_name'], jerk.last_name)
        self.assertEquals(ret[0]['email'], jerk.email)

    def test_admin_users_view(self):
        org1 = self.organization_manager.create('Org 1')
        orgrole1 = self.org_role_manager.create('Org Role 1')
        group1 = Group.objects.create(name='Jerks')
        jerk = self.user_manager.create('george', 'initial_password', 'Mr.', 'first_name',
                           'last_name', '555.555.5555', 'foo@bar.org',
                           'active', {'groups':[group1.id], 'organizations' : {'add' : [{'id' : org1.id, 'role' : orgrole1.id}]}})

        ret = self.user_manager.admin_users_view(self.admin_token)
        for user in ret:
            if user['id'] == jerk.id:
                self.assertTrue('groups' in user)
                self.assertEqual(len(user['groups']), 1)
                self.assertTrue('name' in user['groups'][0])
                self.assertEqual(user['groups'][0]['name'], 'Jerks')
                self.assertTrue('owned_userorgroles' in user)
                self.assertEqual(len(user['owned_userorgroles']), 1)
                self.assertTrue('organization_name' in user['owned_userorgroles'][0])
                self.assertEqual(user['owned_userorgroles'][0]['organization_name'], org1.name)

        ret = self.user_manager.admin_users_view({'exact': {'id' :jerk.id}})
        self.assertEquals(len(ret), 1)
        self.assertTrue('groups' in ret[0])

    @skipUnless(settings.LDAP_AUTHENTICATION, "ldap authentication disabled")
    def test_ldap_login(self):
        self.group_manager.create('library').id
        self.group_manager.create('student').id
        self.group_manager.create('press').id
        self.group_manager.create('continuinged').id
        self.group_manager.create('publicsafety').id
        self.group_manager.create('training').id
        self.group_manager.create('instructional').id
        self.group_manager.create('enrollment').id

        library_group_id = self.group_manager.get_filtered(
            {'exact' : {'name' : 'library'}})[0]['id']

        exception_raised = False
        try:
            self.user_manager.login('rpbarlow', 'rpbarlow', 'LDAP')
        except exceptions.AuthenticationFailureException:
            exception_raised = True
        except:
            raise
        if not exception_raised:
            self.fail('AuthenticationFailureException not raised!')

        # Wrong password
        exception_raised = False
        try:
            self.user_manager.login('UVOD_LIBRARY_G', 'wrongPasswordYo', 'LDAP')
        except exceptions.AuthenticationFailureException:
            exception_raised = True
        except Exception:
            raise
        if not exception_raised:
            self.fail('AuthenticationFailureException not raised!')

        ret = self.user_manager.login('UVOD_LIBRARY_G', 'test', 'LDAP')
        AuthToken.objects.get(session_id=ret['auth_token'])
        # Log in again, to simulate a user who is returning to our system after being created from the first login call
        AuthToken.objects.get(
            session_id=self.user_manager.login('UVOD_LIBRARY_G', 'test', 'LDAP')['auth_token'])


        # Wrong password
        exception_raised = False
        try:
            self.user_manager.login('UVOD_LIBRARY_G', 'wrongPasswordYo', 'LDAP')
        except exceptions.AuthenticationFailureException:
            exception_raised = True
        except Exception:
            raise
        self.assertTrue(exception_raised)

        # Log in again, to simulate a user who is returning to our system after a failed login
        ret = self.user_manager.login('UVOD_LIBRARY_G', 'test', 'LDAP')
        uvod_library_g_id = ret['id']
        uvod_library_g_at = AuthToken.objects.get(session_id=ret['auth_token'])

        ret = self.user_manager.get_filtered(uvod_library_g_at, {'exact' : {'id' : uvod_library_g_id}},
            ['first_name', 'last_name', 'groups', 'email'])
        self.assertEquals(ret[0]['first_name'], 'user')
        self.assertEquals(ret[0]['last_name'], 'VOD_LIBRARY_G')
        self.assertEquals(ret[0]['email'], 'uvod_library_g@mcg.edu')
        self.assertEquals(len(ret[0]['groups']), 1)
        self.assertTrue(library_group_id in ret[0]['groups'])

        # What happens when a person logs in and doesn't have any groups specified?
        ret = self.user_manager.login('unogroups', 'test', 'LDAP')
        unogroups_id = ret['id']
        ldap_at = AuthToken.objects.get(session_id=ret['auth_token'])

        ret = self.user_manager.get_filtered(ldap_at, {'exact' : {'id' : unogroups_id}},
            ['first_name', 'last_name', 'groups', 'email'])[0]
        self.assertEquals(ret['first_name'], 'user')
        self.assertEquals(ret['last_name'], 'nogroups')
        self.assertEquals(ret['email'], 'unogroups@mcg.edu')
        self.assertEquals(len(ret['groups']), 0)

        # What happens if the user logs in and has groups that aren't in powerreg?
        ret = self.user_manager.login('ufakegroup', 'test', 'LDAP')
        ufakegroup_id = ret['id']
        ldap_at = AuthToken.objects.get(session_id=ret['auth_token'])
        ret = self.user_manager.get_filtered(ldap_at, {'exact' : {'id' : ufakegroup_id}},
            ['first_name', 'last_name', 'groups', 'email'])[0]
        self.assertEquals(ret['first_name'], 'user')
        self.assertEquals(ret['last_name'], 'fakegroup')
        self.assertEquals(ret['email'], 'ufakegroup@mcg.edu')
        self.assertEquals(len(ret['groups']), 0)

    def test_self_registered_users_must_be_pending(self):
        # we need to use unique user names because we don't benefit
        # from the RPC layer rolling back transactions in these unit tests
        for status in ['', 'active', 'inactive', 'qualified', 'suspended', 'training']:
            self.assertRaises(exceptions.PermissionDeniedException,
                self.user_manager.create, 'randomuser'+status,
                'initial_password', 'Mr.', 'First', 'Last', '555.555.1212',
                'random@example.net', status, auth_token=None)
        self.user_manager.create('randomuserpending', 'initial_password',
            'Mr.', 'First', 'Last', '555.555.1212', 'random@example.net',
            'pending', auth_token=None)

    def test_reset_password(self):
        self.user_manager.update(self.user1.id, {
            'email2' : 'another@valid.email.com',
            'organizations' : [self.organization1.id],
        })
        self.assertRaises(exceptions.ObjectNotFoundException,
            self.user_manager.reset_password, 'user1', 'wrong@email.com')
        self.user_manager.reset_password('user1', self.user1.email)
        self.user_manager.reset_password('user1', 'another@valid.email.com')
        self.assertEqual(len(mail.outbox), 2)
        for em in mail.outbox:
            self.assertEqual(em.subject, 'password reset for Precor Experience')
            self.assertTrue(
                django.utils.dateformat.format(date.today(), settings.DATE_FORMAT)
                in em.body)
            self.assertTrue('Mr. Primo Uomo, Sr.' in em.body)
            self.assertTrue('Organization 1' in em.body)
            self.assertTrue('Your new password is' in em.body)

    def test_send_password(self):
        org = self.organization_manager.create(
            'Example Corporation')
        self.org_email_domain_manager.create(
            self.admin_token, 'example.com', org.id)
        self.user_manager.create('mailme', 'mypasswd',
            'Mr.', 'Mailme', 'Mypassword', '555.555.5555', 'fake@example.com',
            'active', {'send_password' : True})
        self.assertEqual(len(mail.outbox), 1)
        mess = mail.outbox[0]
        self.assertEqual(mess.subject, u'Welcome to Precor Experience')
        self.assertTrue(
            django.utils.dateformat.format(date.today(), settings.DATE_FORMAT)
            in mess.body)
        self.assertTrue('Mr. Mailme Mypassword' in mess.body)
        self.assertTrue('Example Corporation' in mess.body)
        self.assertTrue('mypasswd' in mess.body)


class TestUserManagerGetters(BasicTestCase):

    fixtures = BasicTestCase.fixtures + ['exams_and_achievements']

    def setUp(self):
        super(TestUserManagerGetters, self).setUp()
        self.user = User.objects.get(id=2)
        self.user_token = self._get_auth_token('user1', 'password')
        self.exams = Exam.objects.all()
        self.assignments = Assignment.objects.all()
        self.get_filtered = partial(self.user_manager.get_filtered,
                filters={'exact': {'id': self.user.id}})

        for a in self.assignments:
            a.mark_completed()
            a.save()

    def test_get_achievements(self):
        _id = attrgetter('id')
        expected = sorted(map(_id, self.user.achievements.all()))
        # test getting achievement with the default token
        result = self.get_filtered(field_names=('achievements',))
        self.assertEquals(len(result), 1)
        self.assertIn('achievements', result[0])
        self.assertSequenceEqual(sorted(result[0]['achievements']), expected)

        # test getting achievements with the users token
        result = self.get_filtered(auth_token=self.user_token,
                field_names=('achievements',))
        self.assertEquals(len(result), 1)
        self.assertIn('achievements', result[0])
        self.assertSequenceEqual(sorted(result[0]['achievements']), expected)

    def test_get_achievement_awards(self):
        _id = attrgetter('id')
        awards = sorted(map(_id, self.user.achievement_awards.all()))
        # test getting achievement awards with default token
        result = self.get_filtered(field_names=('achievement_awards',))
        self.assertEquals(len(result), 1)
        self.assertIn('achievement_awards', result[0])
        self.assertSequenceEqual(sorted(result[0]['achievement_awards']), awards)

        # test getting achievement awards with user's token
        result = self.get_filtered(auth_token=self.user_token,
                field_names=('achievement_awards',))
        self.assertEquals(len(result), 1)
        self.assertIn('achievement_awards', result[0])
        self.assertSequenceEqual(sorted(result[0]['achievement_awards']), awards)


class TestUserModel(BasicTestCase):
    def test_delete(self):
        number_of_initial_users = User.objects.all().count()
        number_of_initial_blames = Blame.objects.all().count()
        soon_to_be_deleted_user = self.user_manager.create('soon_to_be_deleted', 'password', 'Mr',
            'Soon to be', 'Deleted', '919-191-9191', 'soontobe@deleted.org', 'active')
        self.assertEquals(User.objects.all().count(), number_of_initial_users+1)
        self.assertEquals(Blame.objects.all().count(), number_of_initial_blames+1)
        soon_to_be_deleted_user.delete()
        self.assertEquals(User.objects.all().count(), number_of_initial_users)
        self.assertEquals(Blame.objects.all().count(), number_of_initial_blames)

    def test_default_username_and_domain(self):
        ret = self.user_manager.get_filtered({'exact': {'id': self.admin_user.id}},
            ['default_username_and_domain'])
        self.assertEquals(len(ret), 1)
        self.assertEquals(ret[0]['default_username_and_domain'],
            {'username': 'admin', 'domain': 'local'})

class TestVenueManager(GeneralTestCase):
    def test_creation(self):
        region = self.region_manager.create('Southwest')
        venue = self.venue_manager.create('a new venue',
            '555.555.5555', region.id, {'contact' : 'Jenny Lewis is hott!', 'hours_of_operation' : 'NEVER!'})
        address_dict = {'country' : 'US', 'region' : 'NC', 'locality' : 'Raleigh', 'postal_code' : '27613',
            'label' : '100 S. Main St'}

        venue = Venue.objects.get(id=venue.id) # refresh from database
        self.assertEquals(venue.phone, '555.555.5555')
        self.assertEquals(venue.owner.first_name, 'admin')

        self.venue_manager.update(venue.id, {'address' : address_dict, 'phone' : '444.444.4444'})

        venue = Venue.objects.get(id = venue.id) # refresh from database
        self.assertEquals(venue.phone, '444.444.4444')

        venue = self.venue_manager.get_filtered({'exact' : {'id' : venue.id}},
            ['region', 'address', 'contact', 'phone', 'name', 'hours_of_operation'])[0]
        self.assertEquals(venue['region'], region.id)
        self.assertEquals(venue['phone'], '444.444.4444')
        self.assertEquals(venue['name'], 'a new venue')
        self.assertEquals(venue['contact'], 'Jenny Lewis is hott!')
        self.assertEquals(venue['hours_of_operation'], 'NEVER!')
        a = venue['address']
        for attribute in address_dict.keys():
            self.assertTrue(attribute in a)
            self.assertEquals(a[attribute], address_dict[attribute])

    def test_get_filtered(self):
        region = self.region_manager.create('The Danger Zone')
        venue = self.venue_manager.create('Highway to the',
                '911', region.id, {'owner' : self.user1.id})
        room1 = self.room_manager.create('Emergency Room', venue.id, 25)
        room2 = self.room_manager.create('Safety Room', venue.id, 52)
        res = self.venue_manager.get_filtered({'exact' : {'id' : venue.id}}, ['rooms'])
        self.assertEquals(len(res[0]['rooms']), 2)
        self.assertTrue(room1.id in res[0]['rooms'])
        self.assertTrue(room2.id in res[0]['rooms'])
        self.assertEquals(res[0]['id'], venue.id)

class TestCharFieldTruncation(TestCase):
    """
    re #2194 make sure that CharFields are silently truncated
    """

    def test_charfield_truncation(self):
        r = Region.objects.create(name='1'*255 + '2')
        self.assertEquals(r.name, '1'*255)


class CommonObjectManagerTests:
    """
    Reusable tests which depend on a valid auth_token for ObjectManager operations

    Every subclass will run the same test cases which means in order to run
    tests with a different token, the `auth_token` instance member must be
    defined in each subclass (or the default is the admin auth token).
    """

    def test_check_exists(self):
        """checking field value exists (value is unique)"""
        check_exists = self.user_manager.check_exists
        self.assertTrue(check_exists('email', 'admin@admin.org'))
        self.assertFalse(check_exists('email', 'nonexistent@email.com'))


class TestObjectManager(GeneralTestCase, CommonObjectManagerTests):
    def setUp(self):
        super(TestObjectManager, self).setUp()
        self.tu = TestUtils()

    def test_query_on_related_objects(self):
        self.failUnless(ProductLine.objects.count() > 0)
        self.failUnless(Organization.objects.count() > 0)
        organization = Organization.objects.all()[0]

        suitable_venues = Venue.objects.filter(address__isnull=False).exclude(address__postal_code__isnull=True).exclude(address__postal_code='')
        self.failUnless(len(suitable_venues) > 0)
        venue = suitable_venues[0]

        now = datetime.utcnow()
        event_start = now.replace(microsecond=0, second=0, minute=0, hour=0)
        event_end = (now + timedelta(days=5)).replace(microsecond=0, second=0, minute=0, hour=0)

        e1 = self.event_manager.create('Evt', 'Event Title', 'an event',
            event_start.isoformat() + 'Z', event_end.isoformat()  + 'Z',
            organization.id, {'venue': venue.id})
        s1_start = event_start
        s1_end = event_start + timedelta(hours=1)
        self.session_manager.create(s1_start.isoformat() + 'Z',
            s1_end.isoformat() + 'Z', 'active', True, 0, e1.id, 'short name 1', 'long name 1')
        s2_start = s1_end + timedelta(hours=1)
        s2_end = s2_start + timedelta(hours=1)
        self.session_manager.create(s2_start.isoformat() + 'Z',
            s2_end.isoformat() + 'Z', 'active', True, 0, e1.id, 'short name 1', 'long name 1')

        direct_query = Event.objects.filter(
            venue__address__postal_code__exact=venue.address.postal_code)

        ret = self.event_manager.get_filtered(
            {'exact': {'venue__address__postal_code': venue.address.postal_code}}, ['id'])

        self.failUnless(len(ret) == len(direct_query))
        found_e1_in_ret = False
        for result in ret:
            if result['id'] == e1.id:
                found_e1_in_ret = True
        self.failUnless(found_e1_in_ret)

        e2 = self.event_manager.create('Evt', 'Event Title 2', 'another event',
            event_start.isoformat() + 'Z', event_end.isoformat()  + 'Z',
            organization.id, {'venue': venue.id})
        s3_start = event_end - timedelta(hours=10)
        s3_end = s3_start + timedelta(hours=1)

        self.session_manager.create(s3_start.isoformat() + 'Z',
            s3_end.isoformat() + 'Z', 'active', True, 0, e2.id, 'short name 1', 'full name 1')

        direct_query = Event.objects.filter(sessions__start__exact=s3_start)
        self.assertEquals(len(direct_query), 1)
        self.assertEquals(direct_query[0].id, e2.id)

        ret = self.event_manager.get_filtered({'exact':
            {'sessions__start': s3_start.isoformat(' ')}}, ['id'])
        self.assertEquals(len(ret), 1)
        self.assertEquals(ret[0]['id'], e2.id)


class TestObjectManagerPermissions(RoleTestCase, CommonObjectManagerTests):
    """
    Tests for ObjectManager Permissions
    """

    CHECK_PERMISSION_DENIED = ('test_check_exists',)

    def setUp(self):
        super(TestObjectManagerPermissions, self).setUp()
        # run common tests with no auth token, expect permission denied
        self.auth_token = None

    # supplement common tests with a few specific additional checks
    def test_check_exists_with_create_perm_only(self):
        "checking if value exists with create permission only"
        self.create_quick_user_role("Foo Role", {'User': {'c': True}})
        check_exists = self.user_manager.check_exists
        self.assertTrue(check_exists('email', 'admin@admin.org'))
        self.assertFalse(check_exists('email', 'nonexistent@email.com'))

    def test_check_exists_with_update_perm_only(self):
        "checking if value exists with update permission only"
        self.create_quick_user_role("Foo Role", {'User': {'u': set(('email', ))}})
        check_exists = self.user_manager.check_exists
        self.assertTrue(check_exists('email', 'admin@admin.org'))
        self.assertFalse(check_exists('email', 'nonexistent@email.com'))


class TestTaskBundles(BasicTestCase):

    def setUp(self):
        super(TestTaskBundles, self).setUp()
        # create some tasks so that we can bundle them together
        self.exam_1 = self.exam_manager.create('Exam 1')
        self.exam_2 = self.exam_manager.create('Exam 2')
        self.exam_3 = self.exam_manager.create('Exam 3')

    def test_create_and_update(self):
        # create a task bundle with no tasks
        task_bundle = self.task_bundle_manager.create(
            'example task bundle', 'this is an example task bundle', [])
        ret = self.task_bundle_manager.get_filtered(
            {'exact': {'id': task_bundle.id}},
            ['name', 'description', 'tasks_depr'])
        self.failUnless(isinstance(ret, list))
        self.failUnless(len(ret) == 1)
        self.assertEquals(ret[0]['name'], 'example task bundle')
        self.assertEquals(ret[0]['description'], 'this is an example task bundle')
        self.assertEquals(ret[0]['tasks_depr'], [])
        # add some associated tasks
        self.task_bundle_manager.update(task_bundle.id,
            {'tasks_depr': [{'id': self.exam_1.id, 'presentation_order': 2},
                       {'id': self.exam_2.id, 'presentation_order': 1, 'continue_automatically': True},
                      ]})
        ret = self.task_bundle_manager.get_filtered(
            {'exact': {'id': task_bundle.id}}, ['name', 'description', 'tasks_depr'])
        self.failUnless(isinstance(ret, list))
        self.failUnless(len(ret) == 1)
        self.assertEquals(ret[0]['tasks_depr'],
            [{'id': self.exam_2.id, 'presentation_order': 1, 'content_type': 'pr_services.exam',
              'continue_automatically': True},
             {'id': self.exam_1.id, 'presentation_order': 2, 'content_type': 'pr_services.exam',
              'continue_automatically': False}])
        # now swap the order of the tasks
        self.task_bundle_manager.update(task_bundle.id,
            {'tasks_depr': [{'id': self.exam_1.id, 'presentation_order': 1, 'continue_automatically': True},
                       {'id': self.exam_2.id, 'presentation_order': 2, 'continue_automatically': False},
                      ]})
        ret = self.task_bundle_manager.get_filtered(
            {'exact': {'id': task_bundle.id}}, ['name', 'description', 'tasks_depr'])
        self.failUnless(isinstance(ret, list))
        self.failUnless(len(ret) == 1)
        self.assertEquals(ret[0]['tasks_depr'],
            [{'id': self.exam_1.id, 'presentation_order': 1, 'content_type': 'pr_services.exam',
                'continue_automatically': True},
             {'id': self.exam_2.id, 'presentation_order': 2, 'content_type': 'pr_services.exam',
                'continue_automatically': False}])
        # now update to a different list of tasks
        self.task_bundle_manager.update(task_bundle.id,
            {'tasks_depr': [{'id': self.exam_1.id, 'presentation_order': 1, 'continue_automatically': False},
                       {'id': self.exam_2.id, 'presentation_order': 2, 'continue_automatically': True},
                       {'id': self.exam_3.id, 'presentation_order': 3, 'continue_automatically': False},
                      ]})
        ret = self.task_bundle_manager.get_filtered(
            {'exact': {'id': task_bundle.id}}, ['name', 'description', 'tasks_depr'])
        self.failUnless(isinstance(ret, list))
        self.failUnless(len(ret) == 1)
        self.assertEquals(ret[0]['tasks_depr'],
            [{'id': self.exam_1.id, 'presentation_order': 1, 'content_type': 'pr_services.exam',
              'continue_automatically': False},
             {'id': self.exam_2.id, 'presentation_order': 2, 'content_type': 'pr_services.exam',
              'continue_automatically': True},
             {'id': self.exam_3.id, 'presentation_order': 3, 'content_type': 'pr_services.exam',
              'continue_automatically': False}])


class TestScormServer(BasicTestCase):
    def test_mark_completed(self):
        # Upload a SCORM file for testing.
        scorm_zip_file_name = os.path.join(os.path.dirname(__file__), '..',
            'test_services', 'ConstantCon1.zip')
        with open(scorm_zip_file_name, 'rb') as scorm_zip_file:
            self.sco_manager._process_scorm_file(self.admin_token, scorm_zip_file)
        self.assertEqual(len(self.sco_manager.get_filtered({})), 1)
        sco = self.sco_manager.get_filtered({}, ['url'])[0]
        self.sco_manager.update(sco['id'],
            {'completion_requirement': 'cmi_core_lesson_status__completed'})

        # Create an Assignment for the uploaded Sco.
        assignment = self.assignment_manager.create(sco['id'])
        ret = self.assignment_manager.get_filtered(
            {'exact': {'id': assignment.id}}, ['status', 'date_completed'])
        self.assertNotEqual(ret[0]['status'], 'completed')
        self.assertEqual(ret[0]['date_completed'], None)

        # Retrieve the Sco URL view and get its db_form_url context variable.
        response = self.client.get(sco['url'])
        self.assertEqual(response.status_code, 200)
        db_form_url = response.context['db_form_url']

        # Retrive the db form and get its context variables.
        response = self.client.get(db_form_url)
        self.assertEqual(response.status_code, 200)
        auth_token = response.context['auth_token']
        sco_session_id = response.context['sco_session_id']
        shared_object = 'cmi_core_lesson_status=completed'

        # Check that the ScoSession and Assignment do not indicate they have
        # been completed.
        sco_session = self.sco_session_manager.get_filtered(
            {'exact': {'id': sco_session_id}}, ['cmi_core_lesson_status'])[0]
        self.assertNotEqual(sco_session['cmi_core_lesson_status'], 'completed')
        ret = self.assignment_manager.get_filtered(
            {'exact': {'id': assignment.id}}, ['status', 'date_completed'])
        self.assertNotEqual(ret[0]['status'], 'completed')
        self.assertEqual(ret[0]['date_completed'], None)

        # Now post to the lms_commit view to mark the Sco as completed.
        lms_commit_url = reverse('lms_commit')
        data = dict(auth_token=auth_token, sco_session_id=sco_session_id,
            flashSO=shared_object)
        response = self.client.post(lms_commit_url, data)
        self.assertEqual(response.status_code, 200)

        # Check that both the ScoSession and Assignment now indicate they have
        # been completed.
        sco_session = self.sco_session_manager.get_filtered(
            {'exact': {'id': sco_session_id}}, ['cmi_core_lesson_status'])[0]
        self.assertEqual(sco_session['cmi_core_lesson_status'], 'completed')
        ret = self.assignment_manager.get_filtered(
            {'exact': {'id': assignment.id}}, ['status', 'date_completed'])
        self.assertEqual(ret[0]['status'], 'completed')
        self.assertNotEqual(ret[0]['date_completed'], None)

class TestPrUtils(BasicTestCase):
    """
    Test the pr_services.utils.Utils class.
    """

    def test_get_auth_token_object(self):
        at = self.utils.get_auth_token_object(self.admin_token.session_id)
        self.assertEquals(at.session_id, self.admin_token.session_id)
        admin_session_id = at.session_id
        self.user_manager.logout(self.admin_token)
        self.assertRaises(exceptions.NotLoggedInException, self.utils.get_auth_token_object,
            admin_session_id)


class TestCurriculumManagement(BasicTestCase):

    def setUp(self):
        super(TestCurriculumManagement, self).setUp()
        # create some tasks so that we can bundle them together
        self.exam_1 = self.exam_manager.create('Exam 1')
        self.exam_2 = self.exam_manager.create('Exam 2')
        self.exam_3 = self.exam_manager.create('Exam 3')

    def test_admin_curriculum_view(self):
        curriculum = self.curriculum_manager.create('Curriculum 1')

        ret = self.curriculum_manager.admin_curriculums_view(self.admin_token)
        self.assertEquals(len(ret), 1)
        self.assertTrue('name' in ret[0])
        self.assertEquals(ret[0]['name'], curriculum.name)

    def test_create_from_task_bundle(self):
        task_bundle = self.task_bundle_manager.create(
            'example task bundle', 'this is an example task bundle', [
                {'id' : self.exam_1.id, 'presentation_order' : 10},
                {'id' : self.exam_2.id, 'presentation_order' : 20},
                ])
        tbs = self.task_bundle_manager.get_filtered({}, ['id', 'tasks_depr', 'name'])
        self.assertEquals(len(tbs), 1)
        self.assertEquals(tbs[0]['id'], task_bundle.id)
        self.assertTrue('tasks_depr' in tbs[0])
        self.assertEquals(len(tbs[0]['tasks_depr']), 2)
        self.assertTrue('presentation_order' in tbs[0]['tasks_depr'][0])
        self.assertTrue('continue_automatically' in tbs[0]['tasks_depr'][0])

        curriculum = self.curriculum_manager.create('Curriculum 1')
        cta_dicts = []
        for task in tbs[0]['tasks_depr']:
            cta_dicts.append({'curriculum' : curriculum.id, 'task' : task['id'],
                'optional_attributes' : {
                    'presentation_order' : task['presentation_order'],
                    'task_bundle' : tbs[0]['id'],
                    'continue_automatically' : task['continue_automatically']}})
        ret = self.curriculum_task_association_manager.bulk_create(cta_dicts)
        self.assertEquals(len(ret), len(tbs[0]['tasks_depr']))

    def test_enroll_users(self):
        # create users, create curriculum, enroll users
        learner1 = self.user_manager.create('learner_1', 'password', '', '', '', '', '', 'active')
        learner2 = self.user_manager.create('learner_2', 'password', '', '', '', '', '', 'active')
        learner3 = self.user_manager.create('learner_3', 'password', '', '', '', '', '', 'active')
        curriculum = self.curriculum_manager.create('Curriculum 1')
        self.curriculum_task_association_manager.create(curriculum.id, self.exam_1.id)
        self.curriculum_task_association_manager.create(curriculum.id, self.exam_2.id)
        start = self.right_now.isoformat()
        end = (self.right_now+self.one_day).isoformat()
        enrollment = self.curriculum_enrollment_manager.create(curriculum.id, start, end, [learner1.id, learner2.id, learner3.id])

        # verify enrollment
        ret = self.curriculum_enrollment_manager.get_filtered({'exact' : {'id' : enrollment.id}}, ['id', 'users', 'assignments', 'user_completion_statuses'])
        self.assertEquals(len(ret), 1)
        self.assertTrue('users' in ret[0])
        self.assertEquals(len(ret[0]['users']), 3)
        self.assertEquals(len(ret[0]['assignments']), 6)
        self.assertTrue('user_completion_statuses' in ret[0])
        self.assertEquals(len(ret[0]['user_completion_statuses']), 3)
        for user in ret[0]['user_completion_statuses']:
            self.assertEquals(ret[0]['user_completion_statuses'][user], False)

        # verify enrollment status on user object
        users = self.user_manager.get_filtered({'member' : {'id' : [learner1.id, learner2.id, learner3.id]}}, ['completed_curriculum_enrollments', 'incomplete_curriculum_enrollments'])
        self.assertEquals(len(users), 3)
        for user in users:
            self.assertEquals(len(user['completed_curriculum_enrollments']), 0)
            self.assertEquals(len(user['incomplete_curriculum_enrollments']), 1)

        # mark assignments as completed, and verify that the curriculum_enrollment agrees
        for assignment in ret[0]['assignments']:
            self.assignment_manager.update(assignment, {'status' : 'completed'})
        ret = self.curriculum_enrollment_manager.get_filtered({'exact' : {'id' : enrollment.id}}, ['id', 'user_completion_statuses'])
        self.assertTrue('user_completion_statuses' in ret[0])
        self.assertEquals(len(ret[0]['user_completion_statuses']), 3)
        for user in ret[0]['user_completion_statuses']:
            self.assertEquals(ret[0]['user_completion_statuses'][user], True)

        # verify new enrollment status on user object
        users = self.user_manager.get_filtered({'member' : {'id' : [learner1.id, learner2.id, learner3.id]}}, ['completed_curriculum_enrollments', 'incomplete_curriculum_enrollments'])
        self.assertEquals(len(users), 3)
        for user in users:
            self.assertEquals(len(user['completed_curriculum_enrollments']), 1)
            self.assertEquals(len(user['incomplete_curriculum_enrollments']), 0)


class TestUtilsManager(TestCase):
    def test_get_choices(self):
        get_choices = self.utils_manager.get_choices

        # check the invalid model name case
        self.assertRaises(exceptions.FieldNameNotFoundException,
            get_choices, 'not_a_model', 'aspect_ratio')

        self.assertRaises(exceptions.FieldNameNotFoundException,
            get_choices, 'Assignment', 'not_a_field')

        # check that we gen an empty list for a field that has no choices
        choices = get_choices('Assignment', 'date_started')
        self.assertEquals(len(choices), 0)

        # check a couple of fields with choices
        def django_choices(s):
            choice = operator.itemgetter(0)
            return map(choice, s)

        expected = django_choices(Assignment.STATUS_CHOICES)
        test = get_choices('Assignment', 'status')
        self.assertEqual(test, expected)

        expected = django_choices(Domain.PASSWORD_HASH_TYPE_CHOICES)
        test = get_choices('Domain', 'password_hash_type')
        self.assertEquals(test, expected)


##############################################################################
#
# Below this comment block is found utility code that is used to facilitate some of the above unit tests.
#
# XXX: all of which should eventually be moved into testlib
##############################################################################
class TestUtils(object):
    def __init__(self):
        self.session_manager = facade.managers.SessionManager()
        self.assignment_manager = facade.managers.AssignmentManager()
        self.event_manager = facade.managers.EventManager()
        self.organization_manager = facade.managers.OrganizationManager()
        self.session_user_role_requirement_manager = facade.managers.SessionUserRoleRequirementManager()
        self.session_user_role_manager = facade.managers.SessionUserRoleManager()
        self.user_manager = facade.managers.UserManager()
        self.admin_token = facade.subsystems.Utils.get_auth_token_object(self.user_manager.login('admin', 'admin')['auth_token'])
        if not facade.models.Region.objects.all().count():
            self.region2 = facade.managers.RegionManager().create(self.admin_token, 'Region 2')
        else:
            self.region2 = facade.models.Region.objects.all()[0]
        self.venue2 = facade.managers.VenueManager().create(self.admin_token, 'Venue 2', '1253462', self.region2.id,
            {'address': {'label': '1 Test Case Way',
                'locality': 'Morrisville',
                'region': 'NC',
                'country': 'US',
                'postal_code': '27560'}})
        if facade.models.Organization.objects.all().count() == 0:
            self.organization2 = self.organization_manager.create(self.admin_token, 'Organization 2')
        else:
            self.organization2 = facade.models.Organization.objects.all()[0]

        # We just need a product line to use. It doesn't matter which one
        pls = facade.models.ProductLine.objects.all()
        if pls.count():
            self.product_line2 = pls[0]
        else:
            self.product_line2 = facade.managers.ProductLineManager().create(self.admin_token, 'Product Line 2')

    def setup_test_sessions(self):
        """
        set up several test sessions, for use within unit tests
        (this method isn't treated as a unit test because its name doesn't begin with 'test')
        """

        now = datetime.utcnow()
        now = now.replace(microsecond=0, tzinfo=pr_time.UTC()) # we don't want microseconds in our ISO time strings
        # and we need a timezone specified to make valid ISO 8601 format timestamps

        # notifications have not been sent for any of these sessions

        # session 1 happened 5 hours ago and has a lead time of 1 day
        s1_begin = now + timedelta(days=5)
        s1_end = s1_begin + timedelta(hours=2)
        s1_status = 'active'
        s1_confirmed = True
        s1_price = 10000
        s1_modality = 'ILT'
        e1 = self.event_manager.create(self.admin_token, 'Event 1', 'Event 1', 'Event 1', s1_begin.isoformat(), s1_end.isoformat(),
            self.organization2.id, {'venue' : self.venue2.id, 'lead_time' : 86400})
        s1 = self.session_manager.create(self.admin_token, s1_begin.isoformat(), s1_end.isoformat(), s1_status,
            s1_confirmed, s1_price, e1.id, 'short name 1', 'long name 1', {'modality' : s1_modality})

        # session 2 will occur in 1 day and has a lead time of 2 days
        s2_begin = now + timedelta(days=1)
        s2_end = s2_begin + timedelta(hours=3)
        s2_status = 'active'
        s2_confirmed = True
        s2_price = 20000
        s2_modality = 'Generic'
        e2 = self.event_manager.create(self.admin_token, 'Event 2', 'Event 2', 'Event 2', s2_begin.isoformat(), s2_end.isoformat(),
            self.organization2.id, {'venue' : self.venue2.id, 'lead_time' : 172800})
        self.s2 = self.session_manager.create(self.admin_token, s2_begin.isoformat(), s2_end.isoformat(), s2_status,
            s2_confirmed, s2_price, e2.id, 'short name 1', 'long name 1', {'modality' : s2_modality})

        # session 3 will occur in 3 days and has a lead time of 3 days
        s3_begin = now + timedelta(days=3)
        s3_end = s3_begin + timedelta(hours=3)
        s3_status = 'active'
        s3_confirmed = True
        s3_price = 30000
        s3_modality = 'Generic'
        e3 = self.event_manager.create(self.admin_token, 'Event 3', 'Event 3', 'Event 3', s3_begin.isoformat(), s3_end.isoformat(),
            self.organization2.id, {'venue' : self.venue2.id, 'lead_time' : 259200})
        self.s3 = self.session_manager.create(self.admin_token, s3_begin.isoformat(), s3_end.isoformat(), s3_status,
            s3_confirmed, s3_price, e3.id, 'short name 1', 'long name 1', {'modality' : s3_modality})

        # session 4 will occur in 10 days and has a lead time of 7 days
        s4_begin = now + timedelta(days=10)
        s4_end = s4_begin + timedelta(hours=3)
        s4_status = 'active'
        s4_confirmed = True
        s4_price = 40000
        s4_modality = 'Generic'
        e4 = self.event_manager.create(self.admin_token, 'Event 4', 'Event 4', 'Event 4', s4_begin.isoformat(), s4_end.isoformat(),
            self.organization2.id, {'venue' : self.venue2.id, 'lead_time' : 604800})
        s4 = self.session_manager.create(self.admin_token, s4_begin.isoformat(), s4_end.isoformat(), s4_status,
            s4_confirmed, s4_price, e4.id, 'short name 1', 'long name 1', {'modality' : s4_modality})

        # we need session user roles before we can assign users
        instructor_role = facade.models.SessionUserRole.objects.get(name__exact='Instructor')
        student_role = facade.models.SessionUserRole.objects.get(name__exact='Student')

        # we need session user role requirements for each session before we can assign users
        instructor_req1 = self.session_user_role_requirement_manager.create(self.admin_token, str(s1.id), str(instructor_role.id), 1, 2)
        learner_req1 = self.session_user_role_requirement_manager.create(self.admin_token, str(s1.id), str(student_role.id), 1, 30)
        instructor_req2 = self.session_user_role_requirement_manager.create(self.admin_token, str(self.s2.id), str(instructor_role.id),1, 2)
        learner_req2 = self.session_user_role_requirement_manager.create(self.admin_token, str(self.s2.id), str(student_role.id), 1, 30)
        instructor_req3 = self.session_user_role_requirement_manager.create(self.admin_token, str(self.s3.id), str(instructor_role.id), 1, 2)
        learner_req3 = self.session_user_role_requirement_manager.create(self.admin_token, str(self.s3.id), str(student_role.id), 1, 30)
        instructor_req4 = self.session_user_role_requirement_manager.create(self.admin_token, str(s4.id), str(instructor_role.id), 1, 2)
        learner_req4 = self.session_user_role_requirement_manager.create(self.admin_token, str(s4.id), str(student_role.id), 1, 30)

        # we need some users to be assigned in the various sessions
        instructor1 = self.user_manager.create(self.admin_token, 'instructor_1', 'password', 'Mr.', 'David', 'Smith', '', 'david@example.smith.us', 'active')
        instructor2 = self.user_manager.create(self.admin_token, 'instructor_2', 'password', 'Mr.', 'Sally', 'Snodgrass', '', 'sally@example.com', 'active')
        learner1 = self.user_manager.create(self.admin_token, 'learner_1', 'password', 'Ms.', 'Josephine', 'Howard', '', 'jhoward@example.info', 'active')
        learner2 = self.user_manager.create(self.admin_token, 'learner_2', 'password', 'Mr.', 'Jon', 'Haskell', '', 'jhaskell@fake.acme.com', 'active')
        learner3 = self.user_manager.create(self.admin_token, 'learner_3', 'password', '', 'Eleanor', 'Jones', '', 'eleaner_jones@example.foo.bar.info', 'active')
        learner4 = self.user_manager.create(self.admin_token, 'learner_4', 'password', '', 'Luella', 'Ball', '', 'luella_ball@example.foo.bar.info', 'active')

        # group the users by enrollment
        s1_instructors = [str(instructor1.id)]
        s1_learners = [str(learner1.id), str(learner2.id), str(learner3.id), str(learner4.id)]
        s2_instructors = [str(instructor2.id)]
        s2_learners = [str(learner2.id), str(learner4.id)]
        s3_instructors = [str(instructor1.id), str(instructor2.id)]
        s3_learners = [str(learner4.id)]
        s4_instructors = [str(instructor1.id)]
        s4_learners = [str(learner1.id), str(learner2.id), str(learner4.id)]

        # assign the users
        self.assignment_manager.bulk_create(self.admin_token, instructor_req1.id, s1_instructors)
        self.assignment_manager.bulk_create(self.admin_token, learner_req1.id, s1_learners)
        self.assignment_manager.bulk_create(self.admin_token, instructor_req2.id, s2_instructors)
        self.assignment_manager.bulk_create(self.admin_token, learner_req2.id, s2_learners)
        self.assignment_manager.bulk_create(self.admin_token, instructor_req3.id, s3_instructors)
        self.assignment_manager.bulk_create(self.admin_token, learner_req3.id, s3_learners)
        self.assignment_manager.bulk_create(self.admin_token, instructor_req4.id, s4_instructors)
        self.assignment_manager.bulk_create(self.admin_token, learner_req4.id, s4_learners)


class TestAdminPasswordSetup(django.test.TestCase):
    def test_admin_password_setup(self):
        InitialSetupMachine().initial_setup(default_admin_password='Oog5faga')
        user_manager = facade.managers.UserManager()
        self.assertRaises(exceptions.AuthenticationFailureException,
            user_manager.login, 'admin', 'admin')
        admin_token_str = user_manager.login('admin', 'Oog5faga')['auth_token']
        admin_token = facade.subsystems.Utils.get_auth_token_object(admin_token_str)
        self.assertEqual(admin_token.user.first_name, 'admin')

class TestManagerGetterSetters(TestCase):
    def test_getters_setters(self):
        for manager_name in facade.managers.import_map.keys():
            manager = getattr(facade.managers, manager_name)()
            if not isinstance(manager, ObjectManager):
                continue
            for attr, getter in manager.GETTERS.iteritems():
                if not hasattr(Getter, getter):
                    self.fail(
                        'Unknown getter %s for attribute %s of manager %s' % (
                            getter, attr, manager_name))
            for attr, setter in manager.SETTERS.iteritems():
                if not hasattr(Setter, setter):
                    self.fail(
                        'Unknown setter %s for attribute %s of manager %s' % (
                            setter, attr, manager_name))

class TestACLCRUD(TestCase):
    """
    This is a base class for testing the ACL CRUD validity in various
    setup regimes. You want to inherit from it, override setUp with one that
    sets self.initial_setup_args and then calls this setUp, and provide a
    test_* method that calls self.do_test()
    """
    def setUp(self):
        super(TestACLCRUD, self).setUp()
        self.valid_crud = {}
        for manager_name in facade.managers.import_map.keys():
            manager = getattr(facade.managers, manager_name)()
            if not isinstance(manager, ObjectManager):
                continue
            model = manager.my_django_model._meta.object_name
            app = manager.my_django_model._meta.app_label
            crud = {
                'r' : set(manager.GETTERS),
                'u' : set(manager.SETTERS),
            }
            self.valid_crud[model] = crud
            self.valid_crud['%s.%s' % (app, model)] = crud
        # manually add some special cases without managers
        self.valid_crud.update({
            # these don't have managers, we only ever check_create them
            'CSVData' : { 'r' : set(default_read_fields), 'u' : set([]) },
            'Refund' : { 'r' : set(default_read_fields), 'u' : set([]) },
            # these through table models don't have managers, but can be
            # manipulated with set_many via an endpoint of the relationship
            'AchievementAward' : {
                'r' : set(['achievement', 'assignment', 'date', 'user'])|set(default_read_fields),
                'u' : set(['achievement', 'assignment', 'date', 'user']),
            },
            'CurriculumEnrollmentUserAssociation' : {
                'r' : set(default_read_fields),
                'u' : set([]),
            }
        })

    def do_test(self):
        for acl in ACL.objects.all():
            crud = cPickle.loads(str(acl.acl))
            for model, perms in crud.iteritems():
                if not self.valid_crud.has_key(model):
                    self.fail(('Model %s has CRUD permissions in role %s, '+
                        'but no manager in the facade.') %
                        (model, acl.role.name))
                invalid_attrs = set(perms['r']) - self.valid_crud[model]['r']
                if len(invalid_attrs):
                    self.fail(('An ACL for role "%s" contains read '+
                        'permissions for unknown attribute(s) (%s) of model %s')
                        % (acl.role.name, ', '.join(invalid_attrs), model))
                invalid_attrs = set(perms['u']) - self.valid_crud[model]['u']
                if len(invalid_attrs):
                    self.fail(('An ACL for role "%s" contains update '+
                        'permissions for unknown attribute(s) (%s) of model %s')
                        % (acl.role.name, ', '.join(invalid_attrs), model))

class TestDefaultACLCRUD(TestACLCRUD):
    # don't need to set self.initial_setup_args, we are testing defaults
    def test_acl_crud(self):
        self.do_test()

class TestEmailGeneration(BasicTestCase):
    def test_log_error_mails(self):
        self.log_manager.error(self.admin_token, 'this is an error test')
        self.log_manager.critical(self.admin_token, 'this is a critical test')
        self.assertEqual(len(mail.outbox), 2)
        mess = mail.outbox[0]
        self.assertTrue('ERROR Message Logged' in mess.subject)
        self.assertTrue('this is an error test' in mess.body)
        mess = mail.outbox[1]
        self.assertTrue('CRITICAL Message Logged' in mess.subject)
        self.assertTrue('this is a critical test' in mess.body)


class TestOrgSlots(GeneralTestCase):
    """
    Test cases for organization slots.

    Organization slots are UserOrgRole objects which persist
    regardless of whether or not a user is associated with the `UserOrgRole`.

    Reference Issue #17

    """
    def setUp(self):
        super(TestOrgSlots, self).setUp()

        create_org = self.organization_manager.create
        create_role = self.org_role_manager.create

        # create some slots
        self.slot1 = UserOrgRole.objects.create(
                organization=create_org('foo org'),
                role=create_role('foo role'),
                title='slot1', persistent=True)

        self.slot2 = UserOrgRole.objects.create(
                organization=create_org('bar org'),
                role=create_role('bar role'),
                title='slot2', persistent=True)

        self.user_org_role_manager.update(self.slot1.id,
                {'owner': self.user1.id})
        self.user_org_role_manager.update(self.slot2.id,
                {'owner': self.user2.id})

    def _get_user_roles(self, user):
        return self.user_manager.get_filtered(
            {'exact': {'id': user.id}}, ['roles'])[0]['roles']

    def _clear_user_roles(self, user):
        self.user_manager.update(user.id,
                {'roles': {'remove': self._get_user_roles(user)}})

    def test_free_slot(self):
        """
        Test that roles marked "persistent" remain after having been
        disassociated with a user.

        """

        # add one role which is not persistent
        some_org = self.organization_manager.create(
                "Foo-Bar Legal Associates")
        some_role = self.org_role_manager.create(
                "Paper Pusher")
        self.user_manager.update(self.user1.id,
                {'roles': {'add': [
                    {'id': some_role.id,
                     'organization': some_org.id
                    }]}})

        # check that roles are set up as we expect
        user1_roles = self._get_user_roles(self.user1)
        self.assertEquals(len(user1_roles), 2)
        user2_roles = self._get_user_roles(self.user2)
        self.assertEquals(len(user2_roles), 1)

        # clear roles for user1 and user2
        self._clear_user_roles(self.user1)
        self._clear_user_roles(self.user2)

        # check that roles were cleared
        user1_roles = self._get_user_roles(self.user1)
        self.assertEquals(len(user1_roles), 0)
        user2_roles = self._get_user_roles(self.user2)
        self.assertEquals(len(user2_roles), 0)

        # compare remaining UserOrgRole object's with the slots we made earlier
        self.assertEquals(len(UserOrgRole.objects.all()), 2)
        self.assertEquals(UserOrgRole.objects.get(id=self.slot1.id), self.slot1)
        self.assertEquals(UserOrgRole.objects.get(id=self.slot2.id), self.slot2)

        # check that slots are not associated with users
        self.assertEquals(self.slot1.owner, None)
        self.assertEquals(self.slot2.owner, None)

    def test_delete(self):
        """
        Ensure that UserOrgRoles which have persistent=True can
        be explicitly deleted if necessary

        """
        delete = self.user_org_role_manager.delete

        # check that we made 2 role objects
        self.assertEquals(len(UserOrgRole.objects.all()), 2)

        # clear all users' roles
        self._clear_user_roles(self.user1)
        self._clear_user_roles(self.user2)

        # check that roles are not owned
        self.assertEquals(self.slot1.owner, None)
        self.assertEquals(self.slot2.owner, None)

        # explicitly delete both slots
        delete(self.slot1.id)
        delete(self.slot2.id)

        # check that slots were deleted
        self.assertEquals(len(UserOrgRole.objects.all()), 0)

    def test_create(self):
        result = self._get_user_roles(self.user1)
        self.assertEquals(len(result), 1)
        self.assertEqual(result[0], self.slot1.role.id)

        result = self._get_user_roles(self.user2)
        self.assertEqual(result[0], self.slot2.role.id)

        some_org = self.organization_manager.create("Foo-Bar Legal Associates")
        some_role = self.org_role_manager.create("Paper Pusher")
        slot1 = self.user_org_role_manager.create(some_org.id, some_role.id, {'persistent':True})
        self.user_org_role_manager.create(some_org.id, some_role.id, {'persistent':True})
        self.user_org_role_manager.create(some_org.id, some_role.id, {'owner':self.user1.id})

        self.assertEquals(len(self._get_user_roles(self.user1)), 2)
        slot1reload = UserOrgRole.objects.get(id=slot1.id)
        self.assertEquals(slot1.persistent, True)
        self.assertEquals(slot1.persistent, slot1reload.persistent)

# vim:tabstop=4 shiftwidth=4 expandtab
