"""
TaskManager class
"""
__docformat__ = "restructuredtext en"

from pr_services import exceptions
from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
import facade

class TaskManager(ObjectManager):
    """
    Manage Tasks in the Power Reg system
    """

    GETTERS = {
        'achievements': 'get_many_to_many',
        'description': 'get_general',
        'min': 'get_general',
        'max': 'get_general',
        'name': 'get_general',
        'organization': 'get_foreign_key',
        'prerequisite_tasks': 'get_many_to_many',
        'prevent_duplicate_assignments': 'get_general',
        'remaining_capacity': 'get_general',
        'task_fees': 'get_many_to_one',
        'title': 'get_general',
        'type': 'get_content_type',
        'users': 'get_many_to_many',
        'version_id': 'get_general',
        'version_label': 'get_general',
        'version_comment': 'get_general',
        'yielded_tasks': 'get_many_to_many',
    }
    SETTERS = {
        'achievements': 'set_many',
        'description': 'set_general',
        'min': 'set_general',
        'max': 'set_general',
        'name': 'set_general',
        'organization': 'set_foreign_key',
        'prerequisite_tasks': 'set_many',
        'prevent_duplicate_assignments': 'set_general',
        'remaining_capacity': 'set_general',
        'task_fees': 'set_many',
        'title': 'set_general',
        'users': 'set_many',
        'version_id': 'set_general',
        'version_label': 'set_general',
        'version_comment': 'set_general',
        'yielded_tasks': 'set_many',
    }
    def __init__(self):
        """ constructor """

        super(TaskManager, self).__init__()
        self.my_django_model = facade.models.Task

    @service_method
    def create(self, auth_token, name, description, organization,
            prerequisite_tasks=None):
        """
        Create a new task

        Creating a task using the TaskManager is not allowed.  Please use one of the
        TaskManager's subclasses to create your Task!

        :param name: name of the task
        :type name: string
        :param description: description of the task
        :type description: string
        :param prerequisite_tasks:   list of primary keys of tasks that must be completed before
                                    this one can be attempted
        :type prerequisite_tasks:   list of int
        :return:                    a reference to the newly created task
        """
        raise exceptions.OperationNotPermittedException('Creating a task using the ' +\
            'TaskManager is not allowed.  Please use one of the TaskManager\'s subclasses ' +\
            'to create your Task!')

    def _set_optional_attributes(self, task, optional_attributes):
        for attr in [   'prevent_duplicate_assignments',
                        'description',
                        'name',
                        'title',
                        'version_id',
                        'version_label',
                        'version_comment',
                    ]:
            if attr in optional_attributes:
                setattr(task, attr, optional_attributes[attr])
        return task

    def _infer_task_organization(self, auth_token, organization_id=None):
        if not organization_id:
            user_orgs = auth_token.user.organizations.all()
            if len(user_orgs) != 1:
                raise ValueError("Task creator must specify an "
                        "organization_id for an organization to which "
                        "he belongs")
            return user_orgs[0]

        return self._find_by_id(organization_id, facade.models.Organization)

# vim:tabstop=4 shiftwidth=4 expandtab
