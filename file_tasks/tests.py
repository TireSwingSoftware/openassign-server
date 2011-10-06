# Python
import os

# Celery
from celery import conf

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
        # Modify the celery configuration to run tasks eagerly for unit tests.
        self._always_eager = conf.ALWAYS_EAGER
        conf.ALWAYS_EAGER = True
        self.file_download_manager = facade.managers.FileDownloadManager()

    def tearDown(self):
        conf.ALWAYS_EAGER = self._always_eager
        super(TestFileDownload, self).tearDown()

    def _upload_file(self, auth_token=None, file_name=None, name=None,
                     description=None, expected_return_code=None):
        auth_token = auth_token or self.admin_token
        file_name = file_name or 'testfile.txt'
        name = name or 'Test File'
        description = description or 'Testing 1-2-3'
        expected_return_code = expected_return_code or 200
        file_path = os.path.join(os.path.dirname(__file__), 'test_data', file_name)
        with file(file_path, 'r') as f:
            postdata = {
                'auth_token' : auth_token.session_id,
                'name' : name,
                'description' :description,
                'file_data' : f,
            }
            response = self.client.post(reverse('file_tasks:upload_file_for_download'), postdata)
        self.assertEquals(response.status_code, expected_return_code)
        if expected_return_code != 200:
            return
        else:
            file_download_id = int(response.content)
            return facade.models.FileDownload.objects.get(id=file_download_id)

    def test_upload_file_as_admin(self):
        file_download = self._upload_file()
        self.assertTrue(file_download)
        self.assertTrue(file_download.file_data.name)
        print file_download.file_url
        self.assertTrue(file_download.file_url)

    def test_delete_file_as_admin(self):
        raise NotImplementedError

    def test_download_file_as_student(self):
        raise NotImplementedError
