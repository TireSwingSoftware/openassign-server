"""
curriculum manager class
"""

from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
from pr_services.utils import Utils
import facade

class CurriculumManager(ObjectManager):
    """
    Manage curriculums in the Power Reg system
    """
    GETTERS = {
        'achievements': 'get_many_to_many',
        'curriculum_task_associations': 'get_many_to_one',
        'description': 'get_general',
        'name': 'get_general',
        'organization': 'get_foreign_key',
        'tasks': 'get_many_to_many',
    }
    SETTERS = {
        'achievements': 'set_many',
        'description': 'set_general',
        'name': 'set_general',
        'organization': 'set_foreign_key',
        'tasks': 'set_many',
    }
    def __init__(self):
        """ constructor """

        ObjectManager.__init__(self)

        self.my_django_model = facade.models.Curriculum

    @service_method
    def create(self, auth_token, name, optional_attributes=None):
        """
        Create a new curriculum.

        :param  name:           human-readable name
        :param  organization:   organization to which this belongs
        :return:                a reference to the newly created curriculum
        """
        if optional_attributes is None:
            optional_attributes = {}

        c = self.my_django_model(name=name)
        c.save()
        facade.subsystems.Setter(auth_token, self, c, optional_attributes, censored=False)
        c.save()
        self.authorizer.check_create_permissions(auth_token, c)
        return c

    @service_method
    def admin_curriculums_view(self, auth_token, *args, **kwargs):
        view = self.build_view(
                fields=('description', 'name', 'organization'),
                merges=(
                    ('achievements',
                        ('name', )),
                    ('curriculum_task_associations',
                        ('task', 'task_name', 'task_type'))
                ))
        return view(auth_token, *args, **kwargs)


# vim:tabstop=4 shiftwidth=4 expandtab
