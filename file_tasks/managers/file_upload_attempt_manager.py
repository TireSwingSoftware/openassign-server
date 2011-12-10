# PowerReg
from pr_services.credential_system.assignment_attempt_manager import AssignmentAttemptManager
from pr_services.rpc.service import service_method
import facade

class FileUploadAttemptManager(AssignmentAttemptManager):
    """
    Manage FileUploadAttempt objects in the PowerReg system.
    """

    GETTERS = {
        'user': 'get_foreign_key',
        'file_upload': 'get_foreign_key',
        'file_size': 'get_general',
        'file_name': 'get_general',
        'file_url': 'get_general',
        'deleted': 'get_general',
    }
    SETTERS = {
        'deleted': 'set_general',
    }

    def __init__(self):
        super(FileUploadAttemptManager, self).__init__()
        self.my_django_model = facade.models.FileUploadAttempt

    @service_method
    def create(self, auth_token, assignment):
        """
        Create a new FileUploadAttempt object.

        @param auth_token   The authentication token of the acting user
        @type auth_token    facade.models.AuthToken
        @param assignment   FK for an assignment
        @type assignment    int
        @return             The newly created FileUploadAttempt instance.
        """
        assignment_object = self._find_by_id(assignment, facade.models.Assignment)
        file_upload_attempt = self.my_django_model(assignment=assignment_object)
        file_upload_attempt.save()
        self.authorizer.check_create_permissions(auth_token, file_upload_attempt)
        return file_upload_attempt
