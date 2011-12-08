"""
UserOrgRole manager class
"""

from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
from pr_services.utils import Utils
import facade

class UserOrgRoleManager(ObjectManager):
    """
    Manage user roles within organizations in the Power Reg system
    """

    GETTERS = {
        'children': 'get_many_to_one',
        'organization': 'get_foreign_key',
        'organization_name': 'get_general',
        'owner': 'get_foreign_key',
        'parent': 'get_foreign_key',
        'persistent': 'get_general',
        'role': 'get_foreign_key',
        'role_name': 'get_general',
        'title': 'get_general',
    }
    SETTERS = {
        'organization': 'set_forbidden',
        'owner': 'set_foreign_key',
        'parent': 'set_foreign_key',
        'persistent': 'set_general',
        'role': 'set_foreign_key',
        'title': 'set_general',
    }
    def __init__(self):
        """ constructor """

        ObjectManager.__init__(self)
        self.my_django_model = facade.models.UserOrgRole

    @service_method
    def create(self, auth_token, organization, role, optional_attributes=None):
        """
        Create a new UserOrgRole

        :param organization:        PK for the organization
        :param role:                PK for the OrgRole
        :param optional_attributes: dict of optional attributes including 'title',
                                    'persistent', 'owner'
        :return                     a reference to the newly created UserOrgRole
        """
        if optional_attributes is None:
            optional_attributes = {}

        user_org_role = self.my_django_model.objects.create(
            organization = self._find_by_id(organization, facade.models.Organization),
            role = self._find_by_id(role, facade.models.OrgRole))

        facade.subsystems.Setter(auth_token, self, user_org_role, optional_attributes)
        user_org_role.save()

        self.authorizer.check_create_permissions(auth_token, user_org_role)
        return user_org_role

    @service_method
    def user_org_role_detail_view(self, auth_token, filters=None, fields=None):
        """
        Ignores the "fields" argument.
        """
        filters = filters or {}
        ret = self.get_filtered(auth_token, filters, ['role', 'owner', 'persistent', 'title'])

        ret = Utils.merge_queries(ret, facade.managers.UserManager(), auth_token, ['first_name', 'last_name', 'email'], 'owner')

        return Utils.merge_queries(ret, facade.managers.OrgRoleManager(), auth_token, ['name'], 'role')

# vim:tabstop=4 shiftwidth=4 expandtab
