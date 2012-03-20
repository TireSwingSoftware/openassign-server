"""
Common test routines which have been abstracted for re-use in multiple test
scenarios.

The most common re-use pattern is checking the same
operation using different auth tokens. All of the tests contained in this file
should not assume that the auth token being tested is the *admin token*.

Care should be taken to use the admin token for operations which are tested
elsewhere or are not the primary focus of the test (such as the creation of some
other related object for the sake of boilerplate setup for the test).

Every subclass of the common test classes (below) will run the same
test cases which means in order to run tests with a different token,
the `auth_token` instance member must be defined in each subclass
(or the default will be the admin auth token).

See pr_services.testlib.TestCase
"""

import codecs

from datetime import timedelta
from functools import partial
from operator import attrgetter, itemgetter

import facade

from pr_services import pr_time, exceptions
from pr_services.testlib import mixins
from pr_services.testlib.helpers import object_dict, datestring, load_fixtures

facade.import_models(locals())

_id = itemgetter('id')

class AssignmentViewTests:

    @load_fixtures('unprivileged_user', 'exams_and_achievements')
    def __setup_assignment_view_test(self):
        user = User.objects.get(id=2)
        exams = Exam.objects.all().order_by('id')
        assignments = Assignment.objects.all().order_by('id')
        return user, exams, assignments

    def test_exam_view(self):
        user, exams, assignments = self.__setup_assignment_view_test()
        view = partial(self.assignment_manager.exam_view,
            filters={'exact': {'user': user.id}},
            auth_token=self.auth_token)
        assignment, exam = assignments[0], exams[0]
        expected = {
            'id': assignment.id,
            'user': user.id,
            'status': assignment.status,
            'task': {
                'id': exam.id,
                'name': unicode(exam.name),
                'title': unicode(exam.title),
                'type': u'pr_services.exam',
                'description': unicode(exam.description),
                'passing_score': exam.passing_score,
            }
        }
        result = sorted(view(), key=_id)
        self.assertEquals(len(result), 5)
        self.assertDictEqual(result[0], expected)

    def test_detailed_exam_view(self):
        user, exams, assignments = self.__setup_assignment_view_test()
        view = partial(self.assignment_manager.detailed_exam_view,
            filters={'exact': {'user': user.id}},
            auth_token=self.auth_token)
        assignment, exam = assignments[0], exams[0]
        expected = {
            'id': assignment.id,
            'user': {
                'id': user.id,
                'first_name': user.first_name,
                'last_name': user.last_name,
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
        result = sorted(view(), key=_id)
        self.assertEquals(len(result), 5)
        self.assertDictEqual(result[0], expected)

        result = sorted(view(fields=('status', 'task')), key=_id)
        self.assertEquals(len(result), 5)
        self.assertDictEqual(result[0], expected)

        result = sorted(view(filters={'exact': {'id': assignment.id}}), key=_id)
        self.assertEquals(len(result), 1)

    def test_transcript_view(self):
        user, exams, assignments = self.__setup_assignment_view_test()
        view = partial(self.assignment_manager.transcript_view,
            {'exact': {'user': user.id}}, auth_token=self.auth_token)
        # start the first 8 assignments
        for a in assignments[:8]:
            a.date_started = (self.right_now - self.one_day)
            a.save()

        # mark the first five completed and build the expected transcript
        expected = []
        for exam, assignment in zip(exams, assignments[:5]):
            assignment.mark_completed()
            assignment.save()
            awards = assignment.achievement_awards.values_list('id', flat=True)
            expected.append({
                'id': assignment.id,
                'user': user.id,
                'status': unicode(assignment.status),
                'date_completed': datestring(assignment.date_completed),
                'date_started': datestring(assignment.date_started),
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
        result = sorted(result, key=_id)
        expected = sorted(expected, key=_id)
        self.assertSequenceEqual(result, expected)


class EnrollmentTests(mixins.UserTestMixin, mixins.EventTestMixin):
    """
    Tests for user enrollment.

    The test scenarios assume that exams and curriculum will be
    created by an admin. Those two processes should be tested separately.
    """

    NUM_ENROLLED = 3
    NUM_EXAMS = 3

    CHECKED_ENROLLMENT_ATTRS = ('id', 'users', 'assignments',
                              'user_completion_statuses')

    CHECKED_USER_ATTRS = ('completed_curriculum_enrollments',
                        'incomplete_curriculum_enrollments')

    CURRICULUM_NAME = 'Curriculum X'

    def _get_curriculum_enrollment(self, id):
        get_filtered = self.curriculum_enrollment_manager.get_filtered
        enrollments = get_filtered({'exact' : {'id': id}},
                self.CHECKED_ENROLLMENT_ATTRS)
        self.assertEquals(len(enrollments), 1)
        return enrollments[0]

    def _get_curriculum_enrolled_users(self):
        get_filtered = self.user_manager.get_filtered
        users = get_filtered({'member': {'id': self.learner_ids}}, self.CHECKED_USER_ATTRS)
        self.assertEquals(len(users), self.NUM_ENROLLED)
        for attr in self.CHECKED_USER_ATTRS:
            self.assertIn(attr, users[0])
        return sorted(users, key=_id)

    def _setup_curriculum(self, as_admin=False):
        # allow simulating this step as the admin user
        # for pin-pointing failures
        if as_admin:
            create_curr = self.admin_curriculum_manager.create
            create_exam = self.admin_exam_manager.create
        else:
            create_curr = self.curriculum_manager.create
            create_exam = self.exam_manager.create

        # create curriculum
        self.curriculum = create_curr(self.CURRICULUM_NAME, self.organization1.id)

        # create exams
        exams = [create_exam('%s: Exam %d' % (self.__class__.__name__, i),
            organization=self.organization1.id)
                     for i in range(self.NUM_EXAMS)]

        # add exams to curriculum
        add_exam = partial(self.curriculum_task_association_manager.create,
                self.curriculum.id)
        for exam in exams:
            add_exam(exam.id)

    def _setup_curriculum_enrollment(self, as_admin=False):
        self._setup_curriculum(as_admin)

        create_enrollment = partial(self.curriculum_enrollment_manager.create,
                self.curriculum.id)

        # create some active users
        learners = self.create_users(self.NUM_ENROLLED,
                create_update_dict={'status': 'active'},
                compare=False, as_admin=True)

        # store the users' ids
        self.learner_ids = map(attrgetter('id'), learners)

        start = self.right_now.isoformat()
        end = (self.right_now + self.one_day).isoformat()
        return create_enrollment(start, end, self.learner_ids)

    def _check_curriculum_enrollment_status(self, enrollment, expected_status):
        status = enrollment['user_completion_statuses']
        self.assertEquals(len(status), self.NUM_ENROLLED)
        for user in status:
            self.assertEquals(status[user], expected_status)

    def _check_user_curriculum_enrollments(self, users, num_complete, num_incomplete):
        for user in users:
            test_complete = user['completed_curriculum_enrollments']
            test_incomplete = user['incomplete_curriculum_enrollments']
            self.assertEquals(len(test_complete), num_complete)
            self.assertEquals(len(test_incomplete), num_incomplete)

    def test_create_curriculum(self):
        self._setup_curriculum(False)
        self.assertEquals(self.curriculum.name, self.CURRICULUM_NAME)

    def test_enroll_users_in_curriculum(self):
        _enrollment = self._setup_curriculum_enrollment(True)

        enrollment = self._get_curriculum_enrollment(_enrollment.id)
        self._check_curriculum_enrollment_status(enrollment, expected_status=False)

        self.assertEquals(len(enrollment['users']), self.NUM_ENROLLED)
        self.assertEquals(len(enrollment['assignments']),
                self.NUM_ENROLLED * self.NUM_EXAMS)

        # verify enrollment status on user object
        users = self._get_curriculum_enrolled_users()
        self._check_user_curriculum_enrollments(users, 0, 1)

    def test_change_curriculum_enrollment_status(self):
        enrollment = self._setup_curriculum_enrollment(True)
        mark_assignment_completed = partial(self.assignment_manager.update,
                value_map={'status': 'completed'})

        enrollment_id = enrollment.id
        enrollment = self._get_curriculum_enrollment(enrollment_id)
        for attr in self.CHECKED_ENROLLMENT_ATTRS:
            self.assertIn(attr, enrollment)

        for assignment in enrollment['assignments']:
            mark_assignment_completed(assignment)

        enrollment = self._get_curriculum_enrollment(enrollment_id)
        # verify that the enrollment reflects the status change above
        self._check_curriculum_enrollment_status(enrollment, True)
        users = self._get_curriculum_enrolled_users()
        self._check_user_curriculum_enrollments(users, 1, 0)

    def test_enroll_user_in_event(self):
        event, event_dict = self._create_event()
        session, session_dict = self._create_session(event)
        create_surr = self.session_user_role_requirement_manager.create
        create_assignment = self.assignment_manager.create

        student_role = facade.models.SessionUserRole.objects.get(name="Student")
        surr = create_surr(session.id, student_role.id, 1, 3, False)
        create_assignment(surr.id, self.user2.id)

        sessions = self.session_manager.get_user_filtered(self.auth_token,
                self.user2.id, field_names=('event', ))
        self.assertEquals(len(sessions), 1)
        self.assertEquals(sessions[0]['id'], session.id)
        self.assertEquals(sessions[0]['event'], event.id)


class EventTests(mixins.EventTestMixin):
    def test_create_event(self):
        event, event_dict = self._create_event(as_admin=False)
        for k, v in event_dict.iteritems():
            self.assertEquals(getattr(event, k), v)

    def test_update_event(self):
        event, event_dict = self._create_event()
        # as it turns out... the event will be delayed
        oneweek = timedelta(weeks=1)
        start, end = (event.start + oneweek), (event.end + oneweek)
        updates = {'start': start.isoformat(), 'end': end.isoformat()}
        self.event_manager.update(event.id, updates)
        event = self.event_manager.get_filtered(
                {'exact': {'id': event.id}}, ['start', 'end'])[0]

        del event['id'] # get_filtered returning more than we want again :P
        self.assertDictEqual(event, updates)



class ObjectTests:
    def test_check_exists(self):
        """checking field value exists (value is unique)"""
        check_exists = self.user_manager.check_exists
        self.assertTrue(check_exists('email', self.user1.email))
        self.assertTrue(check_exists('email', self.user2.email))
        self.assertFalse(check_exists('email', 'nonexistent@email.com'))


class ResourceTests(mixins.ResourceTestMixin, mixins.EventTestMixin):
    def test_create_resource(self):
        self._create_resource("Foo", as_admin=False)

    def test_view_resource_schedule(self):
        # create a resource, resource type, an event, and
        # some sessions with staggered times
        res, res_type = self._create_resource("Foo", as_admin=True)
        event, event_dict = self._create_event(as_admin=True)
        sessions, schedule = self._create_sessions_with_schedule(event,
                resource=res, resource_type=res_type, as_admin=True)

        # test that we can get the resource by id
        _res = self.resource_manager.get_filtered({'exact': {'id': res.id}},
                ['session_resource_type_requirements'])[0]
        self.assertEquals(_res['id'], res.id)
        reqs = _res['session_resource_type_requirements']
        self.assertEquals(len(reqs), 3)

        # get the sessions using the resource
        test_sessions = self.session_manager.get_filtered(
            {'member': {'session_resource_type_requirements': reqs}},
            ['start', 'end'])

        # make sure we got back the same sessions we started with
        test_ids = set([s['id'] for s in test_sessions])
        expected_ids = set([s.id for s, d in sessions])
        self.assertSetEqual(test_ids, expected_ids)

        # build the schedule based on the session times
        test_schedule = []
        for s in test_sessions:
            start = pr_time.iso8601_to_datetime(s['start'])
            end = pr_time.iso8601_to_datetime(s['end'])
            test_schedule.append((start, end))

        # sort test schedule by start time, then compare
        test_schedule = sorted(test_schedule, key=itemgetter(0))
        self.assertSequenceEqual(schedule, test_schedule)


class UserTests(mixins.UserTestMixin):
    def _get_user_by_id(self, user_id):
        return facade.models.User.objects.get(id=user_id)

    def _test_user_update(self, changes, user=None):
        assert isinstance(changes, dict)
        if not user:
            user, create_dict, = self.create_user(compare=False)
        self.user_manager.update(user.id, changes)
        user = self._get_user_by_id(user.id)
        self.assertDictEqual(object_dict(user, changes.keys()), changes)

    def test_user_create_basic(self):
        user, create_dict, expected_dict = self.create_user(compare=True)
        user_dict = self.user_as_dict(user)
        self.assertDictEqual(user_dict, expected_dict)
        self.assertEquals(user.username, 'local:%s' % create_dict['username'])

    def test_user_update_basic(self):
        changes = {
            'first_name': 'last_name',
            'last_name': 'first_name',
            'phone': '123.456.7789',
        }
        self._test_user_update(changes)

    def test_user_update_self(self):
        changes = {
            'first_name': 'I Changed My Name',
            'phone': '123.456.7789',
            'phone2': '456.789.1011',
        }
        assert self.user1 == self.auth_token.user
        self._test_user_update(changes, self.user1)

    def test_user_change_status_active(self):
        self._test_user_update({'status': 'active'})

    def test_user_change_status_inactive(self):
        self._test_user_update({'status': 'inactive'})

    def test_user_change_status_suspended(self):
        self._test_user_update({'status': 'suspended'})

    def test_user_add_initial_organization(self):
        user, create_dict = self.create_user(compare=False)
        changes = {
            'status': 'active',
            'organizations': {'add': [{'id': self.organization1.id}]}
        }
        self.user_manager.update(user.id, changes)
        user = self._get_user_by_id(user.id)
        self.assertEquals(self.organization1, user.organizations.get())

    def test_user_add_second_organization(self):
        user, create_dict = self.create_user(compare=False)
        other_org = Organization.objects.create(name='Foo Org')
        changes = {
            'status': 'active',
            'organizations': {'add': [{'id': self.organization1.id}]}
        }
        self.user_manager.update(user.id, changes)
        changes = {
            'organizations': {'add': [{'id': other_org.id}]}
        }
        self.user_manager.update(user.id, changes)

        user = self._get_user_by_id(user.id)
        self.assertSequenceEqual([self.organization1, self.organization2],
                user.organizations.all().order_by('id'))

    def test_user_add_organization_role(self):
        user, create_dict = self.create_user(compare=False)
        user_role, created = facade.models.OrgRole.objects.get_or_create(name="User")
        changes = {'roles':
            {'add': [{
                 'id': user_role.id,
                 'organization': self.organization1.id
                 }]
            }
        }
        self.user_manager.update(user.id, changes)
        user = self._get_user_by_id(user.id)
        self.assertEquals(self.organization1, user.organizations.get())

    def test_user_batch_create(self):
        users, compare_dicts = self.create_users(n=5)
        user_dicts = map(self.user_as_dict, users)
        self.assertSequenceEqual(user_dicts, compare_dicts)
        for user in users:
            self.assertEquals(user.blame.user, self.auth_token.user)

    def test_read_users_in_org(self):
        users, compare_dicts = self.create_users(n=2,
                as_admin=True)
        for i, user in enumerate(users):
            compare_dicts[i].update(id=user.id)
            self.admin_user_manager.update(user.id,
                value_map={'organizations': {'add': [self.organization1.id]}})

        compare_keys = compare_dicts[0].keys()
        user_filter = {'member': {'id': [u.id for u in users]}}
        users = self.user_manager.get_filtered(user_filter, compare_keys)
        self.assertEquals(len(users), len(compare_dicts))
        if len(users[0]) != len(compare_dicts[0]):
            raise exceptions.PermissionDeniedException()
        self.assertSequenceEqual(users, compare_dicts)

    def test_read_users_in_other_org(self):
        users, compare_dicts = self.create_users(n=2, as_admin=True)
        otherorg = Organization.objects.create(name='Some other Org')
        for i, user in enumerate(users):
            compare_dicts[i].update(id=user.id)
            self.admin_user_manager.update(user.id,
                    value_map={'organizations': {'add': [otherorg.id]}})

        compare_keys = compare_dicts[0].keys()
        user_filter = {'member': {'id': [u.id for u in users]}}
        users = self.user_manager.get_filtered(user_filter, compare_keys)
        self.assertEquals(len(users), len(compare_dicts))
        if len(users[0]) != len(compare_dicts[0]):
            raise exceptions.PermissionDeniedException()
        self.assertSequenceEqual(users, compare_dicts)

    def test_read_users_in_no_org(self):
        users, compare_dicts = self.create_users(n=2, as_admin=True)
        for i, user in enumerate(users):
            compare_dicts[i].update(id=user.id)
        compare_keys = compare_dicts[0].keys()
        user_filter = {'member': {'id': [u.id for u in users]}}
        users = self.user_manager.get_filtered(user_filter, compare_keys)
        self.assertEquals(len(users), len(compare_dicts))
        if len(users[0]) != len(compare_dicts[0]):
            raise exceptions.PermissionDeniedException()
        self.assertSequenceEqual(users, compare_dicts)


class VenueTests(mixins.EventTestMixin):
    def test_view_venue_schedule(self):
        # create an event, and some sessions for the event
        event, event_dict = self._create_event(optional_attributes={
            'venue': self.venue1.id}, as_admin=True)
        # set the session starts relative to the event start
        sessions, schedule = self._create_sessions_with_schedule(event)

        # perform the test by populating a schedule
        test_schedule = []

        # XXX: maybe for the sake of completion
        # we also  want to test getting the event from a venue?
        # events = self.venue_manager.get_filtered({'exact': {'id': event.venue.id}}, ['events'])
        # ...
        sessions = self.session_manager.get_filtered(
                {'exact': {'event': event.id}}, ['start', 'end'])
        for session in sessions:
            start = pr_time.iso8601_to_datetime(session['start'])
            end = pr_time.iso8601_to_datetime(session['end'])
            test_schedule.append((start, end))

        test_schedule.sort(key=itemgetter(0))
        self.assertSequenceEqual(schedule, test_schedule)



class ExamTests(mixins.ExamTestMixin):
    def test_exam_creation_managers(self):
        e = self._create_exam('mother_exam', 'The Mother of All Exams',
                              passing_score=90)
        qp = self._create_question_pool(e, "Mama's Question Pool")
        q = self._create_question(qp, 'bool', 'Is mama always right?')
        self._create_answer(q, 'Yes', correct=True)
        self._create_answer(q, 'No')

    def test_exam_manager_xml(self):
        # import a new exam
        xml_data = codecs.open('pr_services/test_data/complex_exam.xml', 'r',
                               encoding='utf-8').read()
        exam = self.exam_manager.create_from_xml(self.admin_token, xml_data)
        qs = facade.models.Answer.objects.all()
        qs = qs.filter(question__question_pool__exam=exam)
        qs = qs.filter(next_question_pool__isnull=False)
        self.assertTrue(qs.count() > 0)
        for a in qs:
            qs2 = facade.models.QuestionPool.objects.all()
            self.assertEquals(qs2.filter(randomize_questions=True).count(), 1)
            qs2 = qs2.filter(exam=exam)
            qs2 = qs2.filter(pk=a.next_question_pool.pk)
            self.assertEquals(qs2.count(), 1)
        new_xml_data = self.exam_manager.export_to_xml(self.admin_token, exam.id)

        # Now rename the original exam, import the xml and export again, then
        # check to see if the XML matches.
        exam.name = 'renamed_exam'
        exam.save()
        new_exam = self.exam_manager.create_from_xml(self.admin_token, new_xml_data)
        new_xml_data2 = self.exam_manager.export_to_xml(self.admin_token, new_exam.id)
        self.assertEquals(new_xml_data, new_xml_data2)

        # Try one other exam with correct answers listed.
        xml_data = codecs.open('pr_services/test_data/instructor_exam.xml', 'r',
                               encoding='utf-8').read()
        exam = self.exam_manager.create_from_xml(self.admin_token, xml_data)
        new_xml_data = self.exam_manager.export_to_xml(self.admin_token, exam.id)


class CredentialTests:

    def _create_achievement_cred_exam(self):
        achievement = self.admin_achievement_manager.create(
                'Super Star', 'Award for people who are super stars')
        credential_type = self.admin_credential_type_manager.create(
            'B.S.', 'Electrical Engineering',
            optional_parameters={'required_achievements': [achievement.id]})
        exam = self.admin_exam_manager.create('EE Exam', '',
                self.organization1.id, {'achievements' : [achievement.id]})
        return achievement, credential_type, exam

    def test_grant_from_achievement(self):
        achievement, credential_type, exam = self._create_achievement_cred_exam()
        # Create an assignment, and mark it as completed
        assignment = self.admin_assignment_manager.create(exam.id, self.user1.id)
        self.assertEqual(assignment.status, 'assigned')

        self.assignment_manager.update(assignment.id, {'status': 'completed'})
        result = self.assignment_manager.get_filtered(
                {'exact': {'id': assignment.id}}, ('status', ))
        self.assertEquals(len(result), 1)
        self.assertEqual(result[0]['status'], 'completed')

        result = self.credential_manager.get_filtered(
                {'exact': {'user': self.user1.id}},
                ('status', 'credential_type'))
        self.assertEquals(len(result), 1)
        self.assertEqual(result[0]['status'], 'granted')
        self.assertEqual(result[0]['credential_type'], credential_type.id)

    def test_grant_from_pending_credential(self):
        achievement, credential_type, exam = self._create_achievement_cred_exam()
        # Create a student with a pending credential.
        student, student_at = self.user1, self.user1_auth_token
        credential = self.credential_manager.create(student.id,
            credential_type.id, {'serial_number': '1234', 'authority': 'NCSU'})
        ret = self.credential_manager.get_filtered(
            {'exact': {'id': credential.id}}, ['status'])
        self.assertEqual(ret[0]['status'], 'pending')

        # Create an assignment, and mark it as completed
        assignment = self.assignment_manager.create(exam.id, student.id)
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
        achievement1 = self.achievement_manager.create(
                'Super Star', 'Award for people who are super stars')
        achievement2 = self.achievement_manager.create(
                'Super Duper Star', 'Award for people who are super duper stars')
        exam1 = self.exam_manager.create('EE Exam', '', self.organization1.id,
                {'achievements' : [achievement1.id]})
        exam2 = self.exam_manager.create('CS Exam', '', self.organization1.id,
                {'achievements' : [achievement2.id]})
        credential_type = self.credential_type_manager.create(
            'B.S.', 'Computer Engineering',
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
