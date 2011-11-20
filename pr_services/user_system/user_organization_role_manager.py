"""
UserOrgRole manager class
"""

from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
import facade

class UserOrgRoleManager(ObjectManager):
    """
    Manage user roles within organizations in the Power Reg system
    """

    def __init__(self):
        """ constructor """

        ObjectManager.__init__(self)
        self.getters.update({
            'owner' : 'get_foreign_key',
            'organization' : 'get_foreign_key',
            'organization_name' : 'get_general',
            'role' : 'get_foreign_key',
            'role_name' : 'get_general',
            'title': 'get_general',
            'persistent': 'get_general',
            'parent' : 'get_foreign_key',
            'children' : 'get_many_to_one',
        })
        self.setters.update({
            'owner' : 'set_foreign_key',
            'organization' : 'set_forbidden', # placeholder
            'role' : 'set_forbidden', # placeholder
            'title': 'set_forbidden',
            'persistent': 'set_general',
            'parent' : 'set_foreign_key',
        })
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

        user_org_role = self.my_django_model.objects.create(\
            organization = self._find_by_id(organization, facade.models.Organization),\
            role = self._find_by_id(role, facade.models.OrgRole))

        facade.subsystems.Setter(auth_token, self, user_org_role, optional_attributes)

        self.authorizer.check_create_permissions(auth_token, user_org_role)
        return user_org_role

# vim:tabstop=4 shiftwidth=4 expandtab
