"""
SessionUserRoleRequirement manager class
"""

from pr_services.rpc.service import service_method
from pr_services.utils import Utils
import facade

class SessionUserRoleRequirementManager(facade.managers.TaskManager):
    """
    Manage SessionUserRoleRequirements in the Power Reg system
    """

    GETTERS = {
        'credential_types': 'get_many_to_many',
        'ignore_room_capacity': 'get_general',
        'max': 'get_general',
        'min': 'get_general',
        'notes': 'get_many_to_many',
        'role_name': 'get_general',
        'session': 'get_foreign_key',
        'session_user_role': 'get_foreign_key',
    }
    SETTERS = {
        'credential_types': 'set_many',
        'ignore_room_capacity': 'set_general',
        'max': 'set_general',
        'min': 'set_general',
        'notes': 'set_many',
        'session': 'set_foreign_key',
        'session_user_role': 'set_foreign_key',
    }
    def __init__(self):
        """ constructor """

        super(SessionUserRoleRequirementManager, self).__init__()
        self.my_django_model = facade.models.SessionUserRoleRequirement

    @service_method
    def create(self, auth_token, session_id, session_user_role_id, min, max,
        credential_type_ids=None, optional_attributes=None):

        """
        Create a new SessionUserRoleRequirement

        @param session_id               Primary key for an session
        @param session_user_role_id     Primary key for an session_user_role
        @param min                      Minimum number required
        @param max                      Maximum number allowed
        @param credential_type_ids      Array of credential_type primary keys
        @return                         A reference to the newly created SessionUserRoleRequirement
        """

        if credential_type_ids is None:
            credential_type_ids = []

        session = self._find_by_id(session_id,
                facade.models.Session)
        session_user_role = self._find_by_id(session_user_role_id,
                facade.models.SessionUserRole)
        org = self._infer_task_organization(auth_token,
                session.event.organization.id)
        new_surr = self.my_django_model(
                organization=org,
                session=session,
                session_user_role=session_user_role,
                min=min,
                max=max)
        new_surr.save()
        if credential_type_ids:
            facade.subsystems.Setter(auth_token, self, new_surr,
                    {'credential_types' : {'add' : credential_type_ids}})
        new_surr.save()

        if optional_attributes is not None:
            self._set_optional_attributes(new_surr, optional_attributes)
            new_surr.save()
        self.authorizer.check_create_permissions(auth_token, new_surr)
        return new_surr

    @service_method
    def surr_view(self, auth_token, *args, **kwargs):
        view = self.build_view(
                fields=('session', 'min', 'max', 'credential_types'),
                merges=(
                    ('achievements',
                        ('name', )),
                    ('prerequisite_tasks',
                        ('name', 'description', 'title', 'type')),
                    ('task_fees',
                        ('name', 'price')),
                    ('session_user_role',
                        ('name', ))
                ))
        return view(auth_token, *args, **kwargs)

# vim:tabstop=4 shiftwidth=4 expandtab
