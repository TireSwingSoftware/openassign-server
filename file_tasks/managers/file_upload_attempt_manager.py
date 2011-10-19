# Python
import datetime

# Django
from django.core.urlresolvers import reverse

# PowerReg
from pr_services.credential_system.assignment_attempt_manager import AssignmentAttemptManager
from pr_services import pr_time
from pr_services.rpc.service import service_method
from pr_services.utils import Utils
import facade

class FileUploadAttemptManager(AssignmentAttemptManager):
    """
    Manage FileUploadAttempt objects in the PowerReg system.
    """

    def __init__(self):
        super(FileUploadAttemptManager, self).__init__()
        self.getters.update({
            'user': 'get_foreign_key',
            'file_upload': 'get_foreign_key',
            'file_size': 'get_general',
            'file_name': 'get_general',
            'file_url': 'get_general',
            'deleted': 'get_general',
        })
        self.setters.update({
            'deleted': 'get_general',
        })
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

    @service_method
    def get_upload_url(self, auth_token=None, id=None):
        """
        Return the URL where POST data should be submitted to upload a file.
        A GET request for this URL will return an HTML form where the file can
        be submitted, useful if the client needs to display the upload form in
        a iframe.  If present, auth_token and id will be used to construct the
        returned URL.

        :param auth_token:  The authentication token of the acting user.
        :type auth_token:   facade.models.AuthToken or None
        :param id:          The primary key of the FileUploadAttempt instance.
        :type id:           int or None
        :return:            URL to the upload form.
        """
        if auth_token:
            args = [auth_token.session_id]
            if id:
                args.append(id)
            return reverse('file_tasks:upload_file_form', args=args)
        else:
            return reverse('file_tasks:upload_file')

    @service_method
    def register_file_upload_attempt(self, auth_token, file_upload_id):
        """
        Create or find an assignment to upload a file, then use it to create a
        FileUploadAttempt object.

        :param auth_token:      The authentication token of the acting user
        :type auth_token:       facade.models.AuthToken
        :param file_upload_id:  FK for a FileUpload task
        :type file_upload_id:   int
        :return:                dict with the FileUploadAttempt PK as 'id'
                                and upload_url as 'url'
        """
        # Check that the given ID is for a FileUpload object.
        file_upload = facade.models.FileUpload.objects.get(id=file_upload_id)
        assignments = facade.models.Assignment.objects.filter(
            task__id=file_upload_id, user__id=auth_token.user.id).order_by('-id')
        if len(assignments):
            assignment = assignments[0]
        else:
            assignment = facade.managers.AssignmentManager().create(auth_token,
                file_upload_id)
        attempts = facade.models.AssignmentAttempt.objects.filter(
            assignment__id=assignment.id).order_by('-date_started')
        if len(attempts):
            attempt = attempts[0]
        else:
            attempt = self.my_django_model.objects.create(assignment=assignment)
            self.authorizer.check_create_permissions(auth_token, attempt)
        return {
            'id': attempt.id,
            'url': self.get_upload_url(auth_token, attempt.id),
        }
