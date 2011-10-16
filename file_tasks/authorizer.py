# PowerReg
import facade
from pr_services import exceptions

class Authorizer(facade.subsystems.Authorizer):
    """Authorizer subclass for file tasks."""

    def actor_owns_assignment_for_task(self, auth_token, actee):
        """Returns True iff actor owns an assignment for the given task."""

        if not isinstance(actee, facade.models.Task):
            raise exceptions.InvalidActeeTypeException()
        if facade.models.Assignment.objects.filter(\
            task__id=actee.id, user__id=auth_token.user.id).count():
            return True
        else:
            return False
