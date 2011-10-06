# PowerReg
import facade
from pr_services import exceptions

class Authorizer(facade.subsystems.Authorizer):

    def assignment_is_not_file_download(self, auth_token, actee):
        """Returns True iff the actee is an Assignment the Task in which is not
           a FileDownload."""

        if not isinstance(actee, facade.models.Assignment):
            raise exceptions.InvalidActeeTypeException()
        task = actee.task.downcast_completely()
        if isinstance(task, facade.models.FileDownload):
            return False
        return True
