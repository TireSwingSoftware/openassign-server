# Python
import datetime

# PowerReg
from pr_services.credential_system.assignment_attempt_manager import AssignmentAttemptManager
from pr_services import pr_time
from pr_services.rpc.service import service_method
from pr_services.utils import Utils
import facade

class FileDownloadAttemptManager(AssignmentAttemptManager):
    """Manage FileDownloadAttempt objects in the PowerReg system."""

    def __init__(self):
        super(FileDownloadAttemptManager, self).__init__()
        self.getters.update({
            'assignment': 'get_foreign_key',
            'date_completed': 'get_time',
            'date_started': 'get_time',
            'user': 'get_foreign_key',
            'file_download': 'get_foreign_key',
        })
        self.setters.update({
            'date_completed': 'set_time',
            'date_started': 'set_time',
        })
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
        return {
            'id': file_download_attempt.id,
            'url': file_download_attempt.file_download.file_url,
        }

    @service_method
    def register_file_download_attempt(self, auth_token, file_download_id):
        """
        Create or find an assignment to download the file, then use it to
        create a FileDownloadAttempt object. If a FileDownloadAttempt for this
        (user, file download) combination was created in the last 12 hours,
        does nothing.

        @param auth_token           The authentication token of the acting user
        @type auth_token            facade.models.AuthToken
        @param file_download_id     FK for a file download
        @type file_download_id      int
        """
        # Check that the given ID is for a FileDownload object.
        file_download = facade.models.FileDownload.objects.get(id=file_download_id)
        assignments = facade.models.Assignment.objects.filter(
            task__id=file_download_id, user__id=auth_token.user.id).order_by('-id')
        if len(assignments):
            assignment = assignments[0]
        else:
            assignment = facade.managers.AssignmentManager().create(auth_token, file_download_id)
        start_cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=12)
        attempts = facade.models.AssignmentAttempt.objects.filter(
            assignment__id=assignment.id,
            date_started__gt=start_cutoff).order_by('-date_started')
        if len(attempts):
            attempt = attempts[0]
        else:
            attempt = self.my_django_model.objects.create(assignment=assignment)
            self.authorizer.check_create_permissions(auth_token, attempt)
        return {'id': attempt.id}
