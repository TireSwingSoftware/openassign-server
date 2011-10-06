# Python
import datetime

# Django
from django.db import models
from django.conf import settings

# PowerReg
from pr_services import models as pr_models

# Django Storages
from storages.backends.s3boto import S3BotoStorage

class FileDownload(pr_models.Task):
    """User Task that requires downloading a file."""

    #: The source of the file data for download.
    file_data = models.FileField(upload_to='file_downloads/', storage=S3BotoStorage())
    #: The size of the file content.
    file_size = models.PositiveIntegerField(null=True, default=None)
    #: MD5 checksum for the file content.
    #file_md5 = models.CharField(max_length=32, blank=True, null=True, default=None)
    #: MIME content type for the file.
    #file_type = models.CharField(max_length=64, default='application/octet-stream')
    #: When True, only mark the task complete when a user has fully completed
    #: the file download, not simply when they first access the download URL.
    #require_complete_download = models.BooleanField(default=True)

    @property
    def file_url(self):
        return self.file_data.url if self.file_data.name else None

    def save(self, *args, **kwargs):
        if self.file_data.name:
            self.file_size = self.file_data.size
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

    def save(self, *args, **kwargs):
        if self.pk is None:
            self.date_completed = datetime.datetime.utcnow()
            # FIXME: Ideally, we'd like to mark it complete AFTER the user has
            # completed the file download.
        super(FileDownloadAttempt, self).save(*args, **kwargs)
