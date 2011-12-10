# PowerReg
import facade
from pr_services.credential_system.task_manager import TaskManager
from pr_services.rpc.service import service_method

class FileUploadManager(TaskManager):
    """
    Manage FileDownload tasks in the PowerReg system.
    """

    def __init__(self):
        super(FileUploadManager, self).__init__()
        self.my_django_model = facade.models.FileUpload

    @service_method
    def create(self, auth_token, name, description, optional_attributes=None):
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
        if optional_attributes is None:
            optional_attributes = {}
        file_upload = self.my_django_model(name=name, description=description)
        if isinstance(auth_token, facade.models.AuthToken):
            file_upload.owner = auth_token.user
        file_upload.save()
        if optional_attributes:
            facade.subsystems.Setter(auth_token, self, file_upload,
                                     optional_attributes)
            file_upload.save()
        self.authorizer.check_create_permissions(auth_token, file_upload)
        return file_upload
