"""
credential_type manager class
"""

from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
from pr_services.utils import Utils

import facade
facade.import_models(locals())


class CredentialTypeManager(ObjectManager):
    """
    Manage credential_types in the Power Reg system

    <pre>
    credential_type attributes:
    name          Name of the credential_type
    description   description of the credential_type
    </pre>
    """
    GETTERS = {
        'description': 'get_general',
        'min_required_tasks': 'get_general',
        'name': 'get_general',
        'notes': 'get_many_to_many',
        'prerequisite_credential_types': 'get_many_to_many',
        'required_achievements': 'get_many_to_many',
    }

    SETTERS = {
        'description': 'set_general',
        'min_required_tasks': 'set_general',
        'name': 'set_general',
        'notes': 'set_many',
        'prerequisite_credential_types': 'set_many',
        'required_achievements': 'set_many',
    }

    def __init__(self):
        """ constructor """

        ObjectManager.__init__(self)
        self.my_django_model = facade.models.CredentialType

    @service_method
    def create(self, auth_token, name, description, optional_parameters=None):
        """
        Create a new credential_type

        @param name                name of the credential_type
        @param description         description of the credential_type
        @return                    a reference to the newly created credential_type
                                   struct with new primary key indexed as 'id'
        """
        c = self.my_django_model(name=name, description=description)
        c.save()

        if not optional_parameters:
            c.save()
            self.authorizer.check_create_permissions(auth_token, c)
            return c

        ## XXX: Set the following parameters manually to avoid requiring update
        # permission to create an object with optional parameters.
        achievements = optional_parameters.pop('required_achievements', None)
        if achievements:
            achievements = [Achievement.objects.get(id=x) for x in achievements]
            c.required_achievements.add(*achievements)

        min_required_tasks = optional_parameters.pop('min_required_tasks', None)
        if min_required_tasks:
            c.min_required_tasks = min_required_tasks

        prereqs = optional_parameters.pop('prerequisite_credential_types', None)
        if prereqs:
            prereqs = [CredentialType.objects.get(id=x) for x in prereqs]
            c.prerequisite_credential_types.add(*prereqs)

        if optional_parameters:
            raise ValueError("unsupported optional parameters")

        c.save()
        self.authorizer.check_create_permissions(auth_token, c)
        return c

    @service_method
    def achievement_detail_view(self, auth_token, *args, **kwargs):
        view = self.build_view(
            fields=('name', 'description'),
            merges=(
                ('required_achievements',
                    ('name', 'description')),
            ))
        return view(auth_token, *args, **kwargs)

# vim:tabstop=4 shiftwidth=4 expandtab
