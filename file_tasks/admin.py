# Django
from django.contrib import admin

# File Tasks
from file_tasks.models import *

class FileDownloadAdmin(admin.ModelAdmin):
    """Django admin interface for the FileDownload model."""

class FileDownloadAttemptAdmin(admin.ModelAdmin):
    """Django admin interface for the FileDownloadAttempt model."""

admin.site.register(FileDownload, FileDownloadAdmin)
admin.site.register(FileDownloadAttempt, FileDownloadAttemptAdmin)
