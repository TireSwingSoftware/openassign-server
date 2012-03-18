# Django
from django.core.urlresolvers import reverse

# PowerReg
import facade
from pr_services.credential_system.task_manager import TaskManager
from pr_services.rpc.service import service_method
from pr_services.utils import Utils

class FileDownloadManager(TaskManager):
    """
    Manage FileDownload tasks in the PowerReg system.
    """

    GETTERS = {
        'deleted': 'get_general',
        'file_size': 'get_general',
        'file_url': 'get_general',
    }
    SETTERS = {
        'deleted': 'set_general',
    }

    def __init__(self):
        super(FileDownloadManager, self).__init__()
        self.my_django_model = facade.models.FileDownload

    @service_method
    def create(self, auth_token, name, description, organization=None, optional_attributes=None):
        """
        Create a new FileDownload task.

        :param auth_token:          The authentication token of the acting user
        :type auth_token:           facade.models.AuthToken
        :param name:                The name of the file download.
        :type name:                 string
        :param description:         The description of the file download.
        :type description:          string
        :param optional_attributes: A dictionary of optional FileDownload
                                    attributes.
        :type optional_attributes:  dict
        :return:                    The new FileDownload instance.
        """
        org = self._infer_task_organization(auth_token, organization)
        file_download = self.my_django_model(
                name=name,
                description=description,
                organization=org)
        if isinstance(auth_token, facade.models.AuthToken):
            file_download.owner = auth_token.user
        file_download.save()
        if optional_attributes:
            facade.subsystems.Setter(auth_token, self, file_download,
                                     optional_attributes)
            file_download.save()
        self.authorizer.check_create_permissions(auth_token, file_download)
        return file_download

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
        :param id:          The primary key of the FileDownload task.
        :type id:           int or None
        :return:            URL to the upload form.
        """
        if auth_token:
            args = [auth_token.session_id]
            if id:
                args.append(id)
            return reverse('file_tasks:upload_file_for_download_form', args=args)
        else:
            return reverse('file_tasks:upload_file_for_download')

    @service_method
    def get_download_url_for_assignment(self, auth_token, assignment_id):
        """
        Return the URL where the user can download the file mark the given
        Assignment as completed.

        :param auth_token:      The authentication token of the acting user.
        :type auth_token:       facade.models.AuthToken
        :param assignment_id:   The primary key of the FileDownload task.
        :type assignment_id:    int
        :return:                URL to the file download.
        """
        return reverse('file_tasks:download_file_for_assignment',
                       args=[auth_token.session_id, assignment_id])

    @service_method
    def delete(self, auth_token, file_download_id):
        """
        Mark a file download as deleted and remove it from storage.

        :param auth_token:          The authentication token of the acting user
        :type auth_token:           facade.models.AuthToken
        :param file_download_id:    The primary key of the FileDownload task.
        :type file_download_id:     int
        """
        file_download = self._find_by_id(file_download_id)
        self.authorizer.check_delete_permissions(auth_token, file_download)
        if file_download.file_data.name:
            file_download.file_data.delete(False)
        file_download.deleted = True
        file_download.save()

    @service_method
    def achievement_detail_view(self, auth_token, filters=None, fields=None):
        if not filters:
            filters = {}
        # apply our fields even if the passed fields is empty
        default_fields = set(['name', 'title', 'description', 'file_size', 'file_url', 'achievements', 'prerequisite_tasks', 'task_fees'])
        fields = list(set(fields or []) or default_fields)
        ret = self.get_filtered(auth_token, filters, fields)

        ret = Utils.merge_queries(ret, facade.managers.TaskManager(), auth_token, ['name', 'description', 'title', 'type'], 'prerequisite_tasks')

        ret = Utils.merge_queries(ret, facade.managers.TaskFeeManager(), auth_token, ['name', 'price'], 'task_fees')

        return Utils.merge_queries(ret, facade.managers.AchievementManager(), auth_token, ['name', 'description'], 'achievements')
