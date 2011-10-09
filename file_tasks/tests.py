# Python
import os

# Django
from django.test import TestCase
from django.core.urlresolvers import reverse

# PowerReg
import facade
from pr_services.tests import TestCase

class TestFileDownload(TestCase):
    """Test cases for the FileDownload Task."""

    def setUp(self):
        super(TestFileDownload, self).setUp()
        self.file_download_manager = facade.managers.FileDownloadManager()
        self.file_download_attempt_manager = facade.managers.FileDownloadAttemptManager()

    def tearDown(self):
        for file_download in facade.models.FileDownload.objects.all():
            file_download.delete()
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
            args = [auth_token.session_id]
            if pk:
                args.append(pk)
            upload_url = reverse('file_tasks:upload_file_for_download_form', args=args)
            response = self.client.get(upload_url)
            self.assertEquals(response.status_code, expected_return_code)
        else:
            upload_url = reverse('file_tasks:upload_file_for_download')
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

    def test_download_file_as_user(self):
        file_download = self._upload_file()
        self.file_download_attempt_manager
        raise NotImplementedError
