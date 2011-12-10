# Python
import datetime

# Django
from django.db import models
from django.conf import settings

# PowerReg
from pr_services import models as pr_models

__all__ = ('FileDownload', 'FileDownloadAttempt', 'FileUpload', 'FileUploadAttempt')

# Import Django storage backend as specified in settings.
_storage_class_name = getattr(settings, 'FILE_TASKS_STORAGE_BACKEND',
                              settings.DEFAULT_FILE_STORAGE)
_storage_class_module = __import__(_storage_class_name.rsplit('.', 1)[0],
                                   globals(), locals(),
                                   [_storage_class_name.rsplit('.', 1)[1]], -1)
_storage_class = getattr(_storage_class_module,
                         _storage_class_name.rsplit('.', 1)[1])

class FileDownload(pr_models.Task):
    """User Task that requires downloading a file."""

    #: The source of the file data for download.
    file_data = models.FileField(upload_to='file_downloads/', storage=_storage_class())
    #: The size of the file content.
    file_size = models.PositiveIntegerField(null=True, default=None)
    #: MD5 checksum for the file content.
    #file_md5 = models.CharField(max_length=32, blank=True, null=True, default=None)
    #: MIME content type for the file.
    #file_type = models.CharField(max_length=64, default='application/octet-stream')
    #: When True, only mark the task complete when a user has fully completed
    #: the file download, not simply when they first access the download URL.
    #require_complete_download = models.BooleanField(default=True)
    #: True when the underlying FileDownload task has been marked as deleted.
    deleted = pr_models.PRBooleanField(default=False)

    @property
    def file_name(self):
        if self.file_data.name:
            return self.file_data.name.split('__', 1)[1]
        else:
            return None

    @property
    def file_url(self):
        if not self.file_data.name:
            return None
        # Generate signed URL for S3, fallback to the plain URL in case the S3
        # backend is not being used.
        try:
            return self.file_data.file.key.generate_url(settings.AWS_URL_LIFETIME)
        except AttributeError:
            return self.file_data.url

    def save(self, *args, **kwargs):
        if self.file_data.name:
            self.file_size = self.file_data.size
        else:
            self.file_size = None
        super(FileDownload, self).save(*args, **kwargs)

class FileDownloadAttempt(pr_models.AssignmentAttempt):
    """An attempt by a User to download the associated FileDownload Task."""

    @property
    def file_download(self):
        file_download = self.assignment.task.downcast_completely()
        if isinstance(file_download, FileDownload):
            return file_download
        else:
            raise TypeError('Assigned Task is not a FileDownload')

    @property
    def user(self):
        return self.assignment.user

class FileUpload(pr_models.Task):
    """User Task that requires uploading a file."""

class FileUploadAttempt(pr_models.AssignmentAttempt):
    """An attempt by a user to upload a file for the given FileUpload Task."""

    #: The file data that has been uploaded.
    file_data = models.FileField(upload_to='file_uploads/', storage=_storage_class())
    #: The size of the file content.
    file_size = models.PositiveIntegerField(null=True, default=None)
    #: True when the underlying file has been deleted.
    deleted = pr_models.PRBooleanField(default=False)

    @property
    def file_upload(self):
        file_up = self.assignment.task.downcast_completely()
        if isinstance(file_up, FileUpload):
            return file_up
        else:
            raise TypeError('Assigned Task is not a FileUpload')

    @property
    def file_name(self):
        if self.file_data.name:
            return self.file_data.name.split('__', 1)[1]
        else:
            return None

    @property
    def file_url(self):
        if not self.file_data.name:
            return None
        # Generate signed URL for S3, fallback to the plain URL.
        try:
            return self.file_data.file.key.generate_url(settings.AWS_URL_LIFETIME)
        except AttributeError:
            return self.file_data.url

    def save(self, *args, **kwargs):
        if self.file_data.name:
            self.file_size = self.file_data.size
            if not self.date_completed:
                if not self.assignment.date_completed:
                    self.assignment.mark_completed()
                    self.date_completed = self.assignment.date_completed
                else:
                    self.date_completed = datetime.datetime.utcnow()
        else:
            self.file_size = None
        super(FileUploadAttempt, self).save(*args, **kwargs)
