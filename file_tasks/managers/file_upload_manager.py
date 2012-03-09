# Django
from django.core.urlresolvers import reverse

# PowerReg
import facade
from pr_services.credential_system.task_manager import TaskManager
from pr_services.rpc.service import service_method

class FileUploadManager(TaskManager):
    """
    Manage FileUpload tasks in the PowerReg system.
    """

    def __init__(self):
        super(FileUploadManager, self).__init__()
        self.my_django_model = facade.models.FileUpload

    @service_method
    def create(self, auth_token, name, description, organization=None,
            optional_attributes=None):
        """
        Create a new FileUpload task.

        :param auth_token:          The authentication token of the acting user
        :type auth_token:           facade.models.AuthToken
        :param name:                The name of the file upload task.
        :type name:                 string
        :param description:         The description of the file upload task.
        :type description:          string
        :param optional_attributes: A dictionary of optional FileUpload
                                    attributes.
        :type optional_attributes:  dict
        :return:                    The new FileUpload instance.
        """
        org = self._infer_task_organization(auth_token, organization)
        file_upload = self.my_django_model(
                name=name,
                description=description,
                organization=org)
        if isinstance(auth_token, facade.models.AuthToken):
            file_upload.owner = auth_token.user
        file_upload.save()
        if optional_attributes:
            facade.subsystems.Setter(auth_token, self, file_upload,
                                     optional_attributes)
            file_upload.save()
        self.authorizer.check_create_permissions(auth_token, file_upload)
        return file_upload

    @service_method
    def get_upload_url_for_assignment(self, auth_token=None, assignment_id=None):
        """
        Return the URL where POST data should be submitted to upload a file.
        A GET request for this URL will return an HTML form where the file can
        be submitted, useful if the client needs to display the upload form in
        a iframe.  Auth_token and assignment id will be used to construct the
        returned URL.

        :param auth_token:  The authentication token of the acting user.
        :type auth_token:   facade.models.AuthToken or None
        :param id:          The primary key of the Assignment instance.
        :type id:           int or None
        :return:            URL to the upload form.
        """
        if auth_token:
            args = [auth_token.session_id]
            if assignment_id:
                args.append(assignment_id)
            return reverse('file_tasks:upload_file_for_assignment_form', args=args)
        else:
            return reverse('file_tasks:upload_file_for_assignment')
