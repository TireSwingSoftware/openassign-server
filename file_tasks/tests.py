# Many of these tests will fail unless your settings have
# CELERY_ALWAYS_EAGER == True


# Python
from __future__ import with_statement

import os

from functools import partial

# Django
from django.core.urlresolvers import reverse

# PowerReg
import facade
from pr_services import testlib

class FileTaskTestCase(testlib.GeneralTestCase):
    fixtures = [
        'initial_setup_precor',
        'legacy_objects'
    ]

class TestFileDownload(FileTaskTestCase):
    """Test cases for the FileDownload Task."""

    def setUp(self):
        super(TestFileDownload, self).setUp()
        self.file_download_manager = facade.managers.FileDownloadManager()
        self.file_download_attempt_manager = facade.managers.FileDownloadAttemptManager()

    def tearDown(self):
        for file_download in facade.models.FileDownload.objects.all():
            if file_download.file_data.name:
                file_download.file_data.delete()
        super(TestFileDownload, self).tearDown()

    def _upload_file(self, auth_token=None, file_name=None, name=None,
                     description=None, expected_return_code=None, use_form=False,
                     pk=None):
        auth_token = auth_token or self.admin_token
        file_name = file_name or 'testfile.txt'
        name = name or 'Test File'
        description = description or 'Testing 1-2-3'
        expected_return_code = expected_return_code or 200
        file_path = os.path.join(os.path.dirname(__file__), 'test_data', file_name)
        if use_form:
            upload_url = self.file_download_manager.get_upload_url(auth_token, pk)
            response = self.client.get(upload_url)
            self.assertEquals(response.status_code, expected_return_code)
        else:
            upload_url = self.file_download_manager.get_upload_url()
        with file(file_path, 'r') as f:
            postdata = {
                'id': pk,
                'auth_token': auth_token.session_id,
                'name': name,
                'description': description,
                'organization': self.organization1.id,
                'file_data': f,
            }
            if use_form:
                del postdata['auth_token']
            if use_form or not pk:
                del postdata['id']
            response = self.client.post(upload_url, postdata)
        self.assertEquals(response.status_code, expected_return_code)
        if expected_return_code != 200:
            return
        elif use_form:
            return True
        else:
            file_download_id = int(response.content)
            return facade.models.FileDownload.objects.get(id=file_download_id)

    def test_upload_file_as_admin(self):
        file_download = self._upload_file()
        self.assertTrue(file_download)
        self.assertTrue(file_download.file_data.name)
        self.assertTrue(file_download.file_url)
        self.assertEqual(file_download.organization, self.organization1)
        self.assertEqual(facade.models.FileDownload.objects.all().count(), 1)

    def test_upload_file_as_admin_via_form(self):
        result = self._upload_file(use_form=True)
        self.assertTrue(result)
        file_download = facade.models.FileDownload.objects.get()
        self.assertTrue(file_download.file_data.name)
        self.assertTrue(file_download.file_url)
        self.assertEqual(facade.models.FileDownload.objects.all().count(), 1)

    def test_upload_replacement_file_as_admin(self):
        file_download = self._upload_file()
        self.assertTrue(file_download)
        self.assertEqual(file_download.file_name, 'testfile.txt')
        file_download2 = self._upload_file(file_name='testfile.rtf', pk=file_download.id)
        self.assertTrue(file_download2)
        self.assertEqual(file_download.id, file_download2.id)
        self.assertEqual(file_download2.file_name, 'testfile.rtf')

    def test_get_file_url_as_admin(self):
        file_download = self._upload_file()
        result = self.file_download_manager.get_filtered(self.admin_token,
            {'exact': {'id': file_download.id}},
            ['name', 'description', 'file_size', 'file_url', 'deleted'])
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]['name'])
        self.assertTrue(result[0]['description'])
        self.assertTrue(result[0]['file_size'])
        self.assertTrue(result[0]['file_url'])
        self.assertFalse(result[0]['deleted'])
        file_download = self._upload_file(name='Test 2')
        result = self.file_download_manager.get_filtered(self.admin_token, {},
            ['name', 'description', 'file_size', 'file_url'])
        self.assertEqual(len(result), 2)

    def test_delete_file_as_admin(self):
        file_download = self._upload_file()
        result = self.file_download_manager.delete(self.admin_token, file_download.id)
        result = self.file_download_manager.get_filtered(self.admin_token, {},
            ['name', 'description', 'file_size', 'file_url', 'deleted'])
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]['deleted'])
        self.assertEqual(facade.models.FileDownload.objects.all().count(), 1)
        self.assertEqual(facade.models.FileDownload.objects.filter(deleted=False).count(), 0)
        # Silently return if the file has already been marked deleted.
        self.file_download_manager.delete(self.admin_token, file_download.id)

    def test_file_download_assignments_for_user(self):
        file_download = self._upload_file()
        self.assignment_manager.create(self.admin_token, file_download.id, self.user1.id)
        ret = self.assignment_manager.file_download_view(self.user1_auth_token)
        self.assertEquals(len(ret), 1)
        assignment = ret[0]
        self.assertEquals(assignment['user'], self.user1.id)
        self.assertEquals(assignment['status'], 'assigned')
        self.assertTrue('task' in assignment)
        task = assignment['task']
        self.assertTrue('file_size' in task)
        self.assertFalse('file_url' in task) # User not allowed to see real file_url
        self.assertTrue('name' in task)
        self.assertTrue('description' in task)

    def test_assignment_details(self):
        am = self.assignment_manager
        view = partial(am.detailed_file_download_view, user_id=self.user1.id)
        fd = self._upload_file()
        u = self.user1
        a = am.create(fd.id, u.id)
        expected = {
            'id': a.id,
            'status': u'assigned',
            'task': {
                'id': fd.id,
                'description': fd.description,
                'name': fd.name,
                'title': fd.title,
                'type': 'file_tasks.file download'
            },
            'user': {
                'id': u.id,
                'first_name': u.first_name,
                'last_name': u.last_name
            }
        }
        result = view()
        self.assertEquals(len(result), 1)
        self.assertDictEqual(result[0], expected)

        # test using additional filters
        result = view(filters={'exact': {'status': 'assigned'}})
        self.assertEquals(len(result), 1)
        self.assertDictEqual(result[0], expected)

        result = view(filters={'greater_than': {'user': u.id}})
        self.assertEquals(len(result), 0)

        # test requesting additional fields
        a.due_date = self.right_now + self.one_day
        a.save()
        expected['due_date'] = a.due_date.isoformat()
        result = view(fields=('due_date', ))
        self.assertEquals(len(result), 1)
        self.assertDictEqual(result[0], expected)

    def test_download_when_file_is_not_ready(self):
        # this FileDownload does not have an actual file, similar to a case where
        # the asynchronous processing of an uploaded file hasn't taken place yet.
        file_download = facade.models.FileDownload.objects.create(name='Test FD',
                organization=self.organization1)
        assignment = self.assignment_manager.create(self.admin_token, file_download.id, self.user1.id)
        download_url = self.file_download_manager.get_download_url_for_assignment(self.user1_auth_token, assignment.pk)
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, 404)

    def test_download_file_as_user(self):
        file_download = self._upload_file()
        # Before having an assignment, the user cannot see any file downloads.
        result = self.file_download_manager.get_filtered(self.user1_auth_token, {})
        self.assertFalse(result)
        # Now create an Assignment for this FileDownload Task.
        assignment = self.assignment_manager.create(self.admin_token,
            file_download.id, self.user1.id)
        # Now we can retrieve the FileDownload Task info.  The user should not
        # be able to access the direct file_url.
        result = self.file_download_manager.get_filtered(self.user1_auth_token,
            {'exact': {'id': file_download.id}},
            ['name', 'description', 'file_size', 'file_url'])
        self.assertTrue(result)
        self.assertTrue(result[0]['name'])
        self.assertTrue(result[0]['description'])
        self.assertTrue(result[0]['file_size'])
        self.assertFalse('file_url' in result[0])
        # now try to access it as a Task
        result = self.task_manager.get_filtered(self.user1_auth_token,
            {'exact': {'id': file_download.id}}, ['name', 'description'])
        self.assertTrue(result)
        self.assertTrue(result[0]['name'])
        self.assertTrue(result[0]['description'])
        # There should be no completed Assignments or FileDownloadAttempts for
        # the acting user.
        assignment_qs = facade.models.Assignment.objects.filter(user=self.user1)
        assignment_qs = assignment_qs.exclude(date_completed=None)
        self.assertEqual(assignment_qs.count(), 0)
        self.assertEqual(facade.models.FileDownloadAttempt.objects.count(), 0)
        # Now obtain the download URL and hit the download view, which should
        # redirect to the actual file URL.
        download_url = self.file_download_manager.get_download_url_for_assignment(self.user1_auth_token, assignment.pk)
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, 302)
        # Verify that the Assignment has now been marked as completed and that
        # there is one FileDownloadAttempt recorded.
        assignment_qs = facade.models.Assignment.objects.filter(user=self.user1)
        assignment_qs = assignment_qs.exclude(date_completed=None)
        self.assertEqual(assignment_qs.count(), 1)
        self.assertEqual(facade.models.FileDownloadAttempt.objects.count(), 1)
        assignment = facade.models.Assignment.objects.get(pk=assignment.pk)
        date_completed = assignment.date_completed
        # If we hit the download URL again, the Assignment completion date
        # should not change, but a new FileDownloadAttempt will be created.
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, 302)
        assignment = facade.models.Assignment.objects.get(pk=assignment.pk)
        self.assertEqual(assignment.date_completed, date_completed)
        self.assertEqual(facade.models.FileDownloadAttempt.objects.count(), 2)

class TestFileUpload(FileTaskTestCase):
    """Test cases for the FileUpload Task."""

    def setUp(self):
        super(TestFileUpload, self).setUp()
        self.file_upload_manager = facade.managers.FileUploadManager()
        self.file_upload_attempt_manager = facade.managers.FileUploadAttemptManager()

    def tearDown(self):
        for file_upload_attempt in facade.models.FileUploadAttempt.objects.all():
            if file_upload_attempt.file_data.name:
                file_upload_attempt.file_data.delete()
        super(TestFileUpload, self).tearDown()

    def _upload_file(self, auth_token=None, assignment_id=None, file_name=None,
                     expected_return_code=None, use_form=False):
        auth_token = auth_token or self.user1_auth_token
        file_name = file_name or 'testfile.txt'
        expected_return_code = expected_return_code or 200
        file_path = os.path.join(os.path.dirname(__file__), 'test_data', file_name)
        if use_form:
            upload_url = self.file_upload_manager.get_upload_url_for_assignment(auth_token, assignment_id)
            response = self.client.get(upload_url)
            self.assertEquals(response.status_code, expected_return_code)
            file_upload_attempt = response.context['form'].instance
        else:
            upload_url = self.file_upload_manager.get_upload_url_for_assignment()
            file_upload_attempt = None
        with file(file_path, 'r') as f:
            postdata = {
                'id': file_upload_attempt.id if file_upload_attempt else None,
                'auth_token': auth_token.session_id,
                'assignment_id': assignment_id,
                'file_data': f,
            }
            if use_form:
                del postdata['auth_token']
            if use_form or not assignment_id:
                del postdata['assignment_id']
            if not use_form:
                del postdata['id']
            response = self.client.post(upload_url, postdata)
        self.assertEquals(response.status_code, expected_return_code)
        if expected_return_code != 200:
            return
        elif use_form:
            return True
        else:
            file_upload_attempt_id = int(response.content)
            return facade.models.FileUploadAttempt.objects.get(id=file_upload_attempt_id)

    def test_create_file_upload_as_admin(self):
        file_upload = self.file_upload_manager.create(self.admin_token, 'Test Upload',
            'To complete this task, upload a file.')
        self.assertTrue(file_upload)
        result = self.file_upload_manager.get_filtered(self.admin_token,
            {'exact': {'id': file_upload.id}},
            ['name', 'description'])
        self.assertTrue(result)
        self.assertTrue(result[0]['name'])
        self.assertTrue(result[0]['description'])
        return file_upload

    def test_file_upload_assignments_for_user(self):
        file_upload = self.test_create_file_upload_as_admin()
        self.assignment_manager.create(self.admin_token, file_upload.id, self.user1.id)
        ret = self.assignment_manager.file_upload_view(self.user1_auth_token)
        self.assertEquals(len(ret), 1)
        assignment = ret[0]
        self.assertEquals(assignment['user'], self.user1.id)
        self.assertEquals(assignment['status'], 'assigned')
        self.assertTrue('task' in assignment)
        task = assignment['task']
        self.assertTrue('name' in task)
        self.assertTrue('description' in task)

    def test_upload_file_as_user(self, use_form=False):
        file_upload = self.test_create_file_upload_as_admin()
        # Before having an assignment, the user cannot see any file uploads.
        result = self.file_upload_manager.get_filtered(self.user1_auth_token, {})
        self.assertFalse(result)
        # Now create an Assignment for this FileUpload Task.
        assignment = self.assignment_manager.create(self.admin_token,
            file_upload.id, self.user1.id)
        # Now we can retrieve the FileUpload Task info.
        result = self.file_upload_manager.get_filtered(self.user1_auth_token,
            {'exact': {'id': file_upload.id}}, ['name', 'description'])
        self.assertTrue(result)
        self.assertTrue(result[0]['name'])
        self.assertTrue(result[0]['description'])
        # There should be no completed Assignments or FileUploadAttempts for
        # the acting user.
        assignment_qs = facade.models.Assignment.objects.filter(user=self.user1)
        assignment_qs = assignment_qs.exclude(date_completed=None)
        self.assertEqual(assignment_qs.count(), 0)
        self.assertEqual(facade.models.FileUploadAttempt.objects.count(), 0)
        # Now upload the file.
        result = self._upload_file(self.user1_auth_token, assignment.id, use_form=use_form)
        self.assertTrue(result)
        # Verify that the Assignment has now been marked as completed and that
        # there is one FileUploadAttempt recorded.
        assignment_qs = facade.models.Assignment.objects.filter(user=self.user1)
        assignment_qs = assignment_qs.exclude(date_completed=None)
        self.assertEqual(assignment_qs.count(), 1)
        self.assertEqual(facade.models.FileUploadAttempt.objects.count(), 1)
        assignment = facade.models.Assignment.objects.get(pk=assignment.pk)
        date_completed = assignment.date_completed
        # If we hit the upload URL again, the Assignment completion date
        # should not change, but a new FileUploadAttempt will be created.
        result = self._upload_file(self.user1_auth_token, assignment.id, use_form=use_form)
        self.assertTrue(result)
        assignment = facade.models.Assignment.objects.get(pk=assignment.pk)
        self.assertEqual(assignment.date_completed, date_completed)
        self.assertEqual(facade.models.FileUploadAttempt.objects.count(), 2)

    def test_upload_file_as_user_via_form(self):
        return self.test_upload_file_as_user(use_form=True)

    def test_review_file_upload_attempt_as_admin(self):
        # Create the FileUpload Task, Assignment and do the upload as a user.
        file_upload = self.test_create_file_upload_as_admin()
        assignment = self.assignment_manager.create(self.admin_token,
            file_upload.id, self.user1.id)
        file_upload_attempt = self._upload_file(self.user1_auth_token, assignment.id)
        result = self.file_upload_attempt_manager.get_filtered(self.admin_token,
            {'exact': {'id': file_upload_attempt.id}},
            ['file_name', 'file_size', 'file_url', 'date_completed'])
        self.assertTrue(result)
        self.assertTrue('file_name' in result[0])
        self.assertTrue('file_size' in result[0])
        self.assertTrue('file_url' in result[0])
        self.assertTrue('date_completed' in result[0])
