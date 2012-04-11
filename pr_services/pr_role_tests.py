"""
Role specific test cases which will borrow most tests routines from the library
of common tests in testlib.
"""

import facade

from abc import abstractproperty
from functools import partial

from pr_services import pr_time
from pr_services.exceptions import PermissionDeniedException
from pr_services.testlib import (TestCase, BasicTestCase, RoleTestCase,
        GeneralTestCase, common)
from pr_services.testlib.helpers import *

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


class OrgRoleBase(RoleTestCase, GeneralTestCase):
    fixtures = [
        'initial_setup_precor',
        'legacy_objects',
        'precor_org_roles',
    ]

    ORGROLE_NAME = abstractproperty()

    def setUp(self):
        super(OrgRoleBase, self).setUp()
        update_user = self.admin_user_manager.update
        # put user1 and 2 in organization1
        org_dict = {'organizations': {'add': [{'id': self.organization1.id}]}}
        update_user(self.user2.id, org_dict)

        self.orgrole = OrgRole.objects.get(name=self.ORGROLE_NAME)
        new_role = {'id': self.orgrole.id, 'organization': self.organization1.id}
        role_dict = {'roles': {'add': [new_role]}}
        update_user(self.user1.id, role_dict)
        # use auth token from user1 for all subsequent tests
        self.auth_token = self.user1_auth_token


class OrgRoleTests:
    # These are separate so nose doesnt run tests in the abstract base class.

    @load_fixtures('precor_orgs', 'precor_org_roles')
    def test_privileges_apply_for_descendent_org(self):
        from authorizer.checks.membership.orgrole import actor_has_role_for_actee
        org1 = self.organization1
        org2 = Organization.objects.create(name='XYZ', parent=org1)
        org3 = Organization.objects.create(name='ABC', parent=org2)
        exam1 = Exam.objects.create(name='Exam 1', organization=org2)
        exam2 = Exam.objects.create(name='Exam 2', organization=org3)
        func = partial(actor_has_role_for_actee, self.auth_token,
                role_name=self.ORGROLE_NAME, op='r')

        result = func(exam1)
        self.assertTrue(result)
        result = func(exam2)
        self.assertTrue(result)
        org3.parent = None
        org3.save()
        result = func(exam2)
        self.assertFalse(result)
        result = func(exam1)
        self.assertTrue(result)


class TestOrganizationAdminRole(OrgRoleBase, OrgRoleTests,
                                common.AssignmentViewTests,
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

    ORGROLE_NAME = 'Administrator'

    # check that the following tests fail because of
    # a PermissionDenied exception
    CHECK_PERMISSION_DENIED = [
        'test_create_curriculum',
        'test_create_resource',
        'test_grant_credential_to_no_org_user',
        'test_grant_credential_to_wrong_org_user',
        'test_modify_user_in_different_org',
        'test_read_users_in_other_org',
        'test_user_add_second_organization',
    ]

    def test_task_with_bad_organization(self):
        badorg = Organization.objects.create(name="Bar")
        create_exam = self.exam_manager.create
        create_exam('Foo Exam', organization=self.organization1.id)
        with self.assertRaises(PermissionDeniedException):
            create_exam('Bad Exam', organization=badorg.id)


    def test_role_required_for_noorg_user(self):
        # check that the admin role is required to update a user with no org
        UserOrgRole.objects.all().delete()
        user, user_dict = self.create_user(compare=False, as_admin=True)
        self.assertEquals(user.organizations.count(), 0)
        with self.assertRaises(PermissionDeniedException):
            self.user_manager.update(user.id, {'status': 'active'})


class TestOwnerManagerRole(OrgRoleBase, OrgRoleTests,
                           common.AssignmentViewTests,
                           common.EnrollmentTests,
                           common.ExamTests,
                           common.EventTests,
                           common.UserTests,
                           common.VenueTests):
    """
    Verifies the privileges for the "Owner Manager" authorizer role which
    implies that the user has the "Owner Manager" OrgRole for an organization.
    """

    ORGROLE_NAME = 'Owner Manager'

    # check that the following tests fail because of
    # a PermissionDenied exception
    CHECK_PERMISSION_DENIED = [
        'test_change_curriculum_enrollment_status',
        'test_create_curriculum',
        'test_create_curriculum_enrollment',
        'test_enroll_users_in_curriculum',
        'test_modify_user_in_different_org',
        'test_read_users_in_other_org',
        'test_user_add_initial_organization',
        'test_user_add_organization_role',
        'test_user_add_second_organization',
        'test_user_batch_create',
        'test_user_change_status_active',
        'test_user_change_status_inactive',
        'test_user_change_status_suspended',
        'test_user_create_basic',
        'test_user_update_basic',
    ]


class TestAdminAssistantRole(OrgRoleBase, OrgRoleTests,
                             common.AssignmentViewTests,
                             common.EnrollmentTests,
                             common.ExamTests,
                             common.EventTests,
                             common.UserTests,
                             common.VenueTests):
    """
    Verifies the privileges for the "Admin Assistant" authorizer role which
    implies that the user has the "Admin Assitant" OrgRole for an organization.
    (issue #132).
    """

    ORGROLE_NAME = 'Admin Assistant'

    # check that the following tests fail because of
    # a PermissionDenied exception
    CHECK_PERMISSION_DENIED = [
        'test_create_curriculum',
        'test_create_curriculum_enrollment',
        'test_create_event',
        'test_enroll_user_in_event',
        'test_modify_user_in_different_org',
        'test_read_users_in_other_org',
        'test_update_event',
        'test_user_add_second_organization',
        'test_user_update_basic',
    ]
