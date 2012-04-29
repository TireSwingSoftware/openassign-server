"""
curriculum_enrollment manager class
"""

import facade

from pr_services import pr_time
from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
from pr_services.utils import Utils


class CurriculumEnrollmentManager(ObjectManager):
    """
    Manage curriculum_enrollments in the Power Reg system
    """
    GETTERS = {
        'assignments': 'get_many_to_one',
        'curriculum': 'get_foreign_key',
        'curriculum_name': 'get_general',
        'description': 'get_general',
        'end': 'get_time',
        'name': 'get_general',
        'organization': 'get_foreign_key',
        'start': 'get_time',
        'user_completion_statuses': 'get_general',
        'users': 'get_many_to_many',
    }

    SETTERS = {
        'curriculum': 'set_foreign_key',
        'description': 'set_general',
        'name': 'set_general',
        'organization': 'set_foreign_key',
        'users': 'set_many',
        'start': 'set_time',
        'end': 'set_time',
    }

    def __init__(self):
        """ constructor """

        ObjectManager.__init__(self)
        self.my_django_model = facade.models.CurriculumEnrollment

    @service_method
    def create(self, auth_token, curriculum, start, end, organization, optional_attributes=None):
        """
        Create a new curriculum_enrollment.

        :param  curriculum:     FK for a curriculum
        :param  start:          start date in ISO8601 format
        :param  end:            end date in ISO8601 format
        :return:                a reference to the newly created curriculum_enrollment
        """

        start_date = pr_time.iso8601_to_datetime(start).replace(
                microsecond=0, second=0, minute=0, hour=0)
        end_date = pr_time.iso8601_to_datetime(end).replace(
                microsecond=0, second=0, minute=0, hour=0)

        c = self.my_django_model(start=start_date, end=end_date)
        c.curriculum = self._find_by_id(curriculum, facade.models.Curriculum)
        c.organization = self._find_by_id(organization, facade.models.Organization)
        if 'name' not in optional_attributes:
            c.name = c.curriculum.name
        if 'description' not in optional_attributes:
            c.description = c.curriculum.description
        c.save()
        facade.subsystems.Setter(auth_token, self, c, optional_attributes, censored=False)
        c.save()
        self.authorizer.check_create_permissions(auth_token, c)
        return c

    @service_method
    def user_detail_view(self, auth_token, *args, **kwargs):
        view = self.build_view(
                fields=('description', 'name', 'start', 'end'),
                merges=(
                    ('users',
                        ('first_name', 'last_name', 'email')),
                    ('organization',
                        ('name',))
                ))
        return view(auth_token, *args, **kwargs)

# vim:tabstop=4 shiftwidth=4 expandtab
