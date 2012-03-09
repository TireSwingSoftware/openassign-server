"""
Role specific test cases which will borrow most tests routines from the library
of common tests in testlib.
"""

import facade

from functools import partial

from pr_services import pr_time
from pr_services.exceptions import PermissionDeniedException
from pr_services.testlib import (TestCase, BasicTestCase, RoleTestCase,
        GeneralTestCase, common)
from pr_services.testlib.helpers import expectPermissionDenied, object_dict

facade.import_models(locals(), globals())

class TestObjectOwnerRole(BasicTestCase):

    fixtures = BasicTestCase.fixtures + ['basic_curriculum_enrollment']

    def setUp(self):
        super(TestObjectOwnerRole, self).setUp()
        self.user = User.objects.get(id=2)
        self.exam = Exam.objects.get(id=1)
        self.curr = Curriculum.objects.get(id=1)
        self.enrollment = CurriculumEnrollment.objects.get(id=1)
        self.auth_token = self._get_auth_token('user1', 'password')

    def test_read_curriculum_enrollment(self):
        # fixture created a curriculum with 1 exam and enrolled user1
        # check that the enrollment can be read by the user
        expected = {
            'id': self.enrollment.id,
            'curriculum_name': self.enrollment.curriculum_name,
            'start': self.enrollment.start.isoformat(),
            'end': self.enrollment.end.isoformat(),
        }
        result = self.curriculum_enrollment_manager.get_filtered(
                {'exact': {'id': self.enrollment.id}},
                ('curriculum_name', 'start', 'end'))
        self.assertEquals(len(result), 1)
        self.assertDictEqual(result[0], expected)


class TestSessionParticipantRole(TestCase):
    """
    (github issue #53): Learner should be able to view session and SURR details
    when assigned to SURR.
    """

    fixtures = [
        'initial_setup_precor',
        'session_participant_role',
    ]

    def setUp(self):
        super(TestSessionParticipantRole, self).setUp()

        self.event = Event.objects.get(id=1)
        self.user = User.objects.get(id=2)
        self.session = Session.objects.get(id=1)
        self.surr = SessionUserRoleRequirement.objects.get(session=self.session)
        self.surr_assignment = Assignment.objects.get(user=self.user)

        get_surr = self.session_user_role_requirement_manager.get_filtered
        surr_filter = {'exact': {'id': self.surr.id}}
        self.get_surr = partial(get_surr, filters=surr_filter)

        # perform the test operations as user1
        self.auth_token = self._get_auth_token('user1', 'password')

#    XXX: Test that arbitrary users can't assign themselves to sessions with
#    escalated privileges.
#    @expectPermissionDenied
#    def test_create_assignment(self):
#        self.surr_assignment.delete()
#        instructor_role = SessionUserRole.objects.get(name='Instructor')
#        self.assignment_manager.create(self.session.id,
#                instructor_role.id, 1, 2)

    def test_read_surr_without_assignment(self):
        self.surr_assignment.delete()
        surr = self.get_surr()
        self.assertEquals(len(surr), 1)
        self.assertDictEqual(surr[0], {'id': self.surr.id})

    def test_read_surr(self):
        expected = {
            'id': self.surr.id,
            'name': self.surr.name,
            'title': self.surr.title,
            'description': self.surr.description,
            'session': self.surr.session_id,
        }
        surr = self.get_surr(field_names=list(expected))
        self.assertEquals(len(surr), 1)
        self.assertDictEqual(surr[0], expected)

    def test_read_session(self):
        s = self.session
        expected = {
            'id': s.id,
            'end': s.end.replace(tzinfo=pr_time.UTC()).isoformat(),
            'event': s.event.id,
            'start': s.start.replace(tzinfo=pr_time.UTC()).isoformat(),
            'status': s.status
        }
        get_sessions = self.session_manager.get_filtered
        sessions = get_sessions({'exact': {'id': s.id}}, list(expected))
        self.assertEquals(len(sessions), 1)
        self.assertDictEqual(sessions[0], expected)

    def test_read_session_event(self):
        e = self.event
        expected = {
            'id': e.id,
            'description': e.description,
            'end': e.end.isoformat(),
            'name': e.name,
            'organization': e.organization.id,
            'start': e.start.isoformat(),
            'title': e.title,
        }
        get_events = self.event_manager.get_filtered
        events = get_events({'exact': {'id': e.id}}, list(expected))
        self.assertEquals(len(events), 1)
        self.assertDictEqual(events[0], expected)


class TestOrganizationAdminRole(RoleTestCase, GeneralTestCase,
                                common.CredentialTests,
                                common.EnrollmentTests,
                                common.ExamTests,
                                common.EventTests,
                                common.ResourceTests,
                                common.UserTests,
                                common.VenueTests):
    """
    Verifies the privileges for the "Organization Administrator" role which
    implies that the user has the "Administrator" OrgRole for an organization.
    """

    fixtures = [
        'initial_setup_precor',
        'legacy_objects',
        'precor_org_roles',
    ]

    # check that the following tests fail because of
    # a PermissionDenied exception
    CHECK_PERMISSION_DENIED = [
        'test_create_resource',
        'test_create_curriculum',
        'test_user_add_second_organization'
    ]

    def setUp(self):
        super(TestOrganizationAdminRole, self).setUp()
        update_user = self.admin_user_manager.update
        # put user1 and 2 in organization1
        org_dict = {'organizations': {'add': [{'id': self.organization1.id}]}}
        update_user(self.user2.id, org_dict)
        # make user1 an organization admin
        admin_role = OrgRole.objects.get(name='Administrator')
        new_role = {'id': admin_role.id, 'organization': self.organization1.id}
        role_dict = {'roles': {'add': [new_role]}}
        update_user(self.user1.id, role_dict)
        # use auth token from user1 for all subsequent tests
        self.auth_token = self.user1_auth_token

    @expectPermissionDenied
    def test_modify_user_in_different_org(self):
        """modifying user in a different organization"""
        user, create_dict = self.create_user(compare=False)
        other_org = Organization.objects.create(name='Foo Org')
        # put user in another org
        self.admin_user_manager.update(user.id,
            {'organizations': {'add': [{'id': other_org.id}]}})
        # hope for denied permissions
        self.user_manager.update(user.id, {'status': 'inactive'})

    def test_create_credential_type(self):
        create = self.credential_type_manager.create
        expected = {
            'name': 'B.S. Software Engineering',
            'description': 'Nice to have'
        }
        test = create(expected['name'], expected['description'])
        self.assertDictEqual(object_dict(test, expected.keys()), expected)
        expected = {
            'name': 'M.S. Software Engineering',
            'description': 'Waste of time'
        }
        test = create(expected['name'], expected['description'])
        self.assertDictEqual(object_dict(test, expected.keys()), expected)

    def test_grant_credential(self):
        credentials = self.user1.credentials
        self.assertEquals(credentials.count(), 0)
        degree = self.admin_credential_type_manager.create(
            'B.S. Software Engineering', 'Nice to have')
        cred = self.credential_manager.create(self.user1.id, degree.id)
        has_credential = credentials.filter(credential_type__id=degree.id).exists()
        self.assertTrue(has_credential)

    @expectPermissionDenied
    def test_grant_credential_to_no_org_user(self):
        user, create_dict = self.create_user(compare=False)
        degree = self.admin_credential_type_manager.create(
            'B.S. Software Engineering', 'Nice to have')
        self.credential_manager.create(user.id, degree.id)

    @expectPermissionDenied
    def test_grant_credential_to_wrong_org_user(self):
        # make a user and put them in a different org
        user, create_dict = self.create_user(compare=False)
        org = Organization.objects.create(name='The "Org" Organization')
        self.admin_user_manager.update(user.id,
                {'organizations': {'add': [org.id]}})

        degree = self.admin_credential_type_manager.create(
            'B.S. Software Engineering', 'Nice to have')
        self.credential_manager.create(user.id, degree.id)

    def test_task_with_bad_organization(self):
        badorg = Organization.objects.create(name="Bar")
        create_exam = self.exam_manager.create
        create_exam('Foo Exam', organization_id=self.organization1.id)
        with self.assertRaises(PermissionDeniedException):
            create_exam('Bad Exam', organization_id=badorg.id)
