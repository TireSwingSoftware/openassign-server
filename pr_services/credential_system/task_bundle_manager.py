"""
TaskBundleManager class
"""
__docformat__ = "restructuredtext en"

from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
import facade
from pr_services.utils import Utils

class TaskBundleManager(ObjectManager):
    """
    Manage Task Bundles in the Power Reg system
    """

    GETTERS = {
        'active': 'get_general',
        'name': 'get_general',
        'description': 'get_general',
        'tasks': 'get_many_to_many',
    }
    SETTERS = {
        'active': 'set_general',
        'name': 'set_general',
        'description': 'set_general',
        'tasks': 'set_many',
    }
    def __init__(self):
        """ constructor """

        super(TaskBundleManager, self).__init__()
        self.my_django_model = facade.models.TaskBundle

    @service_method
    def create(self, auth_token, name, description, tasks=None):
        """
        Creates a new task bundle

        :param name:            user-visible name of the task bundle
        :type name:             string
        :param description:     description of the task bundle
        :type description:      string
        :param tasks:           list of dictionaries, each with key "id" for the
                                Task FK. Optionally include key "presentation_order"
                                and/or key "continue_automatically"
        :type tasks:            list

        :returns: a reference to the newly created task bundle
        """

        task_bundle = self.my_django_model.objects.create(name=name,
            description=description)
        if tasks:
            facade.subsystems.Setter(auth_token, self, task_bundle, {'tasks' : tasks})

        self.authorizer.check_create_permissions(auth_token, task_bundle)

        return task_bundle

    @service_method
    def task_detail_view(self, auth_token, *args, **kwargs):
        view = self.build_view(
                fields=('name', 'description'),
                merges=(
                    ('tasks', ('name', 'description', 'title', 'type')),
                ))
        return view(auth_token, *args, **kwargs)

# vim:tabstop=4 shiftwidth=4 expandtab
