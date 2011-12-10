# Many of these tests will fail unless your settings have
# CELERY_ALWAYS_EAGER == True


# Python
from __future__ import with_statement
import os

# Django
from django.core.urlresolvers import reverse

# PowerReg
import facade
from pr_services.tests import TestCase

class TestFileDownload(TestCase):
    """Test cases for the FileDownload Task."""

    def setUp(self):
        self.initial_setup_args = ['precor']
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
        ret = self.assignment_manager.file_download_assignments_for_user(self.auth_token)
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

    def test_download_file_as_user(self):
        file_download = self._upload_file()
        # Before having an assignment, the user cannot see any file downloads.
        result = self.file_download_manager.get_filtered(self.auth_token, {})
        self.assertFalse(result)
        # Now register a download attempt, which implicitly creates an
        # Assignment if needed.
        result = self.file_download_attempt_manager.register_file_download_attempt(\
            self.auth_token, file_download.id)
        self.assertTrue(result['id'])
        self.assertTrue(result['url'])
        file_download_attempt_id = result['id']
        file_download_url = result['url']
        # Now we can get the file download attempt fields.
        result = self.file_download_attempt_manager.get_filtered(self.auth_token,
            {'exact': {'id': file_download_attempt_id}},
            ['file_download', 'date_started', 'date_completed'])
        self.assertTrue(result)
        self.assertTrue(result[0]['file_download'])
        self.assertTrue(result[0]['date_started'])
        self.assertFalse(result[0]['date_completed'])
        file_download_id = result[0]['file_download']
        # And now the file download task info.  The user should not be able to
        # access the direct file_url, only the one returned from the file
        # download attempt.
        result = self.file_download_manager.get_filtered(self.auth_token,
            {'exact': {'id': file_download_id}},
            ['name', 'description', 'file_size', 'file_url'])
        self.assertTrue(result)
        self.assertTrue(result[0]['name'])
        self.assertTrue(result[0]['description'])
        self.assertTrue(result[0]['file_size'])
        self.assertFalse('file_url' in result[0])
        # Now hit the download URL and verify the file download attempt has
        # been marked as completed.
        response = self.client.get(file_download_url)
        self.assertEqual(response.status_code, 302)
        result = self.file_download_attempt_manager.get_filtered(self.auth_token,
            {'exact': {'id': file_download_attempt_id}}, ['date_completed'])
        self.assertTrue(result)
        self.assertTrue(result[0]['date_completed'])

class TestFileUpload(TestCase):
    """Test cases for the FileUpload Task."""

    def setUp(self):
        self.initial_setup_args = ['precor']
        super(TestFileUpload, self).setUp()
        self.file_upload_manager = facade.managers.FileUploadManager()
        self.file_upload_attempt_manager = facade.managers.FileUploadAttemptManager()

    def tearDown(self):
        for file_upload_attempt in facade.models.FileUploadAttempt.objects.all():
            if file_upload_attempt.file_data.name:
                file_upload_attempt.file_data.delete()
        super(TestFileUpload, self).tearDown()

    def _upload_file(self, auth_token=None, file_name=None,
                     expected_return_code=None, use_form=False, pk=None):
        auth_token = auth_token or self.auth_token
        file_name = file_name or 'testfile.txt'
        expected_return_code = expected_return_code or 200
        file_path = os.path.join(os.path.dirname(__file__), 'test_data', file_name)
        if use_form:
            upload_url = self.file_upload_attempt_manager.get_upload_url(auth_token, pk)
            response = self.client.get(upload_url)
            self.assertEquals(response.status_code, expected_return_code)
        else:
            upload_url = self.file_upload_attempt_manager.get_upload_url()
        with file(file_path, 'r') as f:
            postdata = {
                'id': pk,
                'auth_token': auth_token.session_id,
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

    def test_upload_file_as_user(self):
        file_upload = self.test_create_file_upload_as_admin()
        result = self._upload_file(pk=file_upload.id)
        self.assertTrue(result)
        self.assertTrue(result.file_data.name)
        self.assertTrue(result.file_url)
        self.assertTrue(result.date_completed)

    def test_upload_file_as_user_via_form(self):
        file_upload = self.test_create_file_upload_as_admin()
        result = self._upload_file(pk=file_upload.id, use_form=True)
        self.assertTrue(result)
        file_upload_attempt = facade.models.FileUploadAttempt.objects.get()
        self.assertTrue(file_upload_attempt.file_data.name)
        self.assertTrue(file_upload_attempt.file_url)
        self.assertTrue(file_upload_attempt.date_completed)
