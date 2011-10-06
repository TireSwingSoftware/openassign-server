#import base64
#from django import forms
#from django.conf import settings
#from django.core.files.uploadedfile import SimpleUploadedFile
#from django.core.urlresolvers import reverse
#from django.db import transaction
#from django.http import HttpResponse
#from django.utils import simplejson as json
#import logging
#from pr_services import exceptions
#from pr_services import storage
#from pr_services import middleware
#from pr_services.utils import upload
#from pr_services.utils import Utils
#import traceback
#from upload_queue import prepare_upload, queue_upload
#from vod_aws.tasks import queue_encoding
#from celery.task.sets import subtask
#import urlparse
#import os.path

# PowerReg
import facade
from pr_services.credential_system.task_manager import TaskManager
from pr_services.rpc.service import service_method

class FileDownloadManager(TaskManager):
    """Manage FileDownload tasks in the PowerReg system."""

    def __init__(self):
        super(FileDownloadManager, self).__init__()
        self.getters.update({
            'file_size': 'get_general',
            #'file_md5': 'get_general',
            #'file_type': 'get_general',
        })
        self.setters.update({
            #'file_type': 'set_general',
        })
        self.my_django_model = facade.models.FileDownload

    @service_method
    def create(self, auth_token, name, description, optional_attributes=None):
        """
        Create a new FileDownload task.

        :param auth_token:          The authentication token of the acting user
        :type auth_token:           facade.models.AuthToken
        :param name:                The name of the file download to be created.
        :type name:                 string
        :param description:         The description of the file download to be
                                    created.
        :type description:          string
        :param optional_attributes: A dictionary of optional FileDownload
                                    attributes.
        :type optional_attributes:  dict
        :return:                    The new FileDownload instance.
        """
        if optional_attributes is None:
            optional_attributes = {}
        file_download = self.my_django_model(name=name, description=description)
        if isinstance(auth_token, facade.models.AuthToken):
            file_download.owner = auth_token.user
        file_download.save()
        if optional_attributes:
            facade.subsystems.Setter(auth_token, self, file_download,
                                     optional_attributes)
            file_download.save()
        self.authorizer.check_create_permissions(auth_token, file_download)
        return file_download

    @service_method
    def delete(self, auth_token, file_download_id):
        """Mark a file download as deleted and remove it from storage."""
        file_download = self._find_by_id(file_download_id)
        self.authorizer.check_delete_permissions(auth_token, file_download)
        file_download.file_data.delete(False)
        file_download.file_size = 0
        file_download.save()

# vim:tabstop=4 shiftwidth=4 expandtab
