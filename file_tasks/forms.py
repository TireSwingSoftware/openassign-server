# Django
from django import forms

# File Tasks
from file_tasks.models import FileDownload, FileUploadAttempt

__all__ = ('FileDownloadForm', 'FileUploadAttemptForm')

class FileTaskForm(forms.ModelForm):
    """Common Form base class for file tasks."""
    
    id = forms.IntegerField(required=False)
    auth_token = forms.CharField(max_length=64, required=False)

    def __init__(self, *args, **kwargs):
        super(FileTaskForm, self).__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['id'].required = True
        self.fields['id'].widget = forms.HiddenInput()
        if self.initial.get('auth_token', None):
            self.fields['auth_token'].widget = forms.HiddenInput()

class FileDownloadForm(FileTaskForm):
    """Form for uploading a file for download."""

    class Meta:
        model = FileDownload
        fields = ('file_data', 'name', 'description')

class FileUploadAttemptForm(FileTaskForm):
    """Form for uploading a file to complete a FileUploadAttempt."""

    assignment_id = forms.IntegerField(required=True)

    def __init__(self, *args, **kwargs):
        super(FileUploadAttemptForm, self).__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['assignment_id'].required = False
        if self.initial.get('assignment_id', None) or self.instance.pk:
            self.fields['assignment_id'].widget = forms.HiddenInput()

    class Meta:
        model = FileUploadAttempt
        fields = ('file_data',)
