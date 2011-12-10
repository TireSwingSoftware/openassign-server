# PowerReg
from pr_services.credential_system.assignment_attempt_manager import AssignmentAttemptManager
from pr_services.rpc.service import service_method
import facade

class FileDownloadAttemptManager(AssignmentAttemptManager):
    """
    Manage FileDownloadAttempt objects in the PowerReg system.
    """

    GETTERS = {
        'assignment': 'get_foreign_key',
        'date_completed': 'get_time',
        'date_started': 'get_time',
        'file_download': 'get_foreign_key',
        'user': 'get_foreign_key',
    }
    SETTERS = {
        'date_completed': 'set_time',
        'date_started': 'set_time',
    }

    def __init__(self):
        super(FileDownloadAttemptManager, self).__init__()
        self.my_django_model = facade.models.FileDownloadAttempt

    @service_method
    def create(self, auth_token, assignment):
        """
        Create a new FileDownloadAttempt object.

        @param auth_token   The authentication token of the acting user
        @type auth_token    facade.models.AuthToken
        @param assignment   FK for an assignment
        @type assignment    int
        @return             A dictionary with two items. 'id' contains the
                            primary key of the FileDownloadAttempt object. 'url'
                            contains the URL where the user can download the
                            associated file.
        """
        assignment_object = self._find_by_id(assignment, facade.models.Assignment)
        file_download_attempt = self.my_django_model(assignment=assignment_object)
        file_download_attempt.save()
        self.authorizer.check_create_permissions(auth_token, file_download_attempt)
        return file_download_attempt
