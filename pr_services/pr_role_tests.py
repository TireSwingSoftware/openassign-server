"""
Role specific test cases which will borrow most tests routines from the library
of common tests in testlib.
"""

import facade

from functools import partial

from pr_services import pr_time
from pr_services.testlib import TestCase
from pr_services.testlib.helpers import expectPermissionDenied

facade.import_models(locals(), globals())

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
