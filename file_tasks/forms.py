# Django
from django import forms

# File Tasks
from file_tasks.models import FileDownload

class FileDownloadForm(forms.ModelForm):
    """Form for uploading a file for download."""

    class Meta:
        model = FileDownload
        fields = ('file_data', 'name', 'description')

    auth_token = forms.CharField(max_length=64, required=False)
