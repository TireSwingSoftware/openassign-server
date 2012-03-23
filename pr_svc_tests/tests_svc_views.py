
import tests_svc

class TestCase(tests_svc.TestCase):
    def check_call(self, func):
        def wrapper(*args, **kwargs):
            result = func(self.admin_token, *args, **kwargs)
            self.assertTrue(result)
            self.assertTrue('status' in result)
            self.assertEquals(result['status'], 'OK',
                    result.get('error', None))
            self.assertTrue('value' in result)
            return result['value']
        return wrapper


class TestAssignmentViews(TestCase):
    def setUp(self):
        super(TestAssignmentViews, self).setUp()
        manager = self.assignment_manager
        self.view = self.check_call(manager.view)
        self.detailed_view = self.check_call(manager.detailed_view)
        self.exam_view = self.check_call(manager.exam_view)
        self.detailed_exam_view = self.check_call(manager.detailed_exam_view)
        self.file_download_view = self.check_call(manager.file_download_view)
        self.detailed_file_download_view = self.check_call(manager.detailed_file_download_view)
        self.file_upload_view = self.check_call(manager.file_upload_view)
        self.session_view = self.check_call(manager.session_view)
        self.transcript_view = self.check_call(manager.transcript_view)

    def test_view(self):
        result = self.view()
        self.assertEquals(result, [])
        result = self.view({})
        self.assertEquals(result, [])
        result = self.view({}, ())
        self.assertEquals(result, [])

    def test_detailed_view(self):
        result = self.detailed_view()
        self.assertEquals(result, [])

    def test_exam_view(self):
        result = self.exam_view()
        self.assertEquals(result, [])

    def test_detailed_exam_view(self):
        result = self.detailed_view()
        self.assertEquals(result, [])

    def test_file_download_view(self):
        result = self.file_download_view()
        self.assertEquals(result, [])

    def test_detailed_file_download_view(self):
        result = self.detailed_file_download_view()
        self.assertEquals(result, [])

    def test_file_upload_view(self):
        result = self.file_upload_view()
        self.assertEquals(result, [])

    def test_session_view(self):
        result = self.session_view()
        self.assertEquals(result, [])

    def test_transcript_view(self):
        result = self.transcript_view()
        self.assertEquals(result, [])


class TestCredentialTypeViews(TestCase):
    def setUp(self):
        super(TestCredentialTypeViews, self).setUp()

        self.achievement_detail_view = self.check_call(
                self.credential_type_manager.achievement_detail_view)

    def test_achievement_detail_view(self):
        result = self.achievement_detail_view()
        self.assertEquals(result, [])


class TestCurriculumEnrollmentViews(TestCase):
    def setUp(self):
        super(TestCurriculumEnrollmentViews, self).setUp()

        self.user_detail_view = self.check_call(
                self.curriculum_enrollment_manager.user_detail_view)

    def test_user_detail_view(self):
        result = self.user_detail_view()
        self.assertEquals(result, [])


class TestCurriculumViews(TestCase):
    def setUp(self):
        super(TestCurriculumViews, self).setUp()

        self.admin_curriculums_view = self.check_call(
                self.curriculum_manager.admin_curriculums_view)

    def test_admin_curriculum_view(self):
        result = self.admin_curriculums_view()
        self.assertEquals(result, [])


class TestSessionViews(TestCase):
    def setUp(self):
        super(TestSessionViews, self).setUp()

        self.detailed_surr_view = self.check_call(
                self.session_manager.detailed_surr_view)

    def test_detailed_surr_view(self):
        result = self.detailed_surr_view()
        self.assertEquals(result, [])


class TestSURRViews(TestCase):
    def setUp(self):
        super(TestSURRViews, self).setUp()

        self.surr_view = self.check_call(
                self.session_user_role_requirement_manager.surr_view)

    def test_surr_view(self):
        result = self.surr_view()
        self.assertEquals(result, [])


class TestExamViews(TestCase):
    def setUp(self):
        super(TestExamViews, self).setUp()

        self.achievement_detail_view = self.check_call(
                self.exam_manager.achievement_detail_view)

    def test_achievement_detail_view(self):
        result = self.achievement_detail_view()
        self.assertEquals(result, [])


class TestOrganizationViews(TestCase):
    def setUp(self):
        super(TestOrganizationViews, self).setUp()

        self.admin_org_view = self.check_call(
                self.organization_manager.admin_org_view)

    def test_admin_org_view(self):
        result = self.admin_org_view()
        expected = [{
            'id': 1,
            'external_uid': None,
            'name': u'Organization 1',
            'org_email_domains': [],
            'parent': None,
            'use_external_uid': False,
            'user_org_roles': [],
        }]
        self.assertEquals(result, expected)


class TestUserViews(TestCase):
    def setUp(self):
        super(TestUserViews, self).setUp()

        self.admin_users_view = self.check_call(
                self.user_manager.admin_users_view)

    def test_admin_users_view(self):
        result = self.admin_users_view()
        expected = [{
            'status': u'active',
            'first_name': u'admin',
            'last_name': u'user',
            'title': None,
            'alleged_organization': None,
            'email': u'admin@admin.org',
            'phone': None,
            'groups': [{'name': u'Super Administrators', 'id': 1}],
            'default_username_and_domain': {
                'username': u'admin',
                'domain': u'local'},
            'owned_userorgroles': [], 'id': 1}]
        self.assertEquals(result, expected)


class TestUserOrgRoleViews(TestCase):
    def setUp(self):
        super(TestUserOrgRoleViews, self).setUp()

        self.user_org_role_detail_view = self.check_call(
                self.user_org_role_manager.user_org_role_detail_view)

    def test_user_org_role_detail_view(self):
        result = self.user_org_role_detail_view()
        self.assertEquals(result, [])
