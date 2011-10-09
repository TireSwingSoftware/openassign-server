# Django
from django import forms

# File Tasks
from file_tasks.models import FileDownload

class FileDownloadForm(forms.ModelForm):
    """Form for uploading a file for download."""

    def __init__(self, *args, **kwargs):
        super(FileDownloadForm, self).__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['id'].required = True
        self.fields['id'].widget = forms.HiddenInput()
        if self.initial.get('auth_token', None):
            self.fields['auth_token'].widget = forms.HiddenInput()

    class Meta:
        model = FileDownload
        fields = ('file_data', 'name', 'description')

    id = forms.IntegerField(required=False)
    auth_token = forms.CharField(max_length=64, required=False)
