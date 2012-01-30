"""
TrainingUnitAccount manager class
"""

from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
import facade

class TrainingUnitAccountManager(ObjectManager):
    """
    Manage TrainingUnitAccounts in the Power Reg system
    """
    #: Dictionary of attribute names and the functions used to set them

    SETTERS = {
        'notes': 'set_many',
        'organization': 'set_foreign_key',
        'user': 'set_foreign_key',
        'starting_value': 'set_general',
    }
    #: Dictionary of attribute names and the functions used to get them
    GETTERS = {
        # This is not in the data model, but it derived. It will not have a
        # setter for obvious reasons.
        'balance': 'get_balance_from_training_unit_account',
        'notes': 'get_many_to_many',
        'organization': 'get_foreign_key',
        'training_unit_transactions': 'get_many_to_one',
        'user': 'get_foreign_key',
    }
    def __init__(self):
        """ constructor """

        ObjectManager.__init__(self)
        self.my_django_model = facade.models.TrainingUnitAccount

    @service_method
    def create(self, auth_token, user=None, organization=None):
        """
        Create a new TrainingUnitAccount

        @param user             User associated with this account. Mutually exclusive with company.
        @param organization     organization associated with this account. Mutually exclusive with user.
        @return                 a reference to the newly created TrainingUnitAccount
        """

        t = self.my_django_model()
        facade.subsystems.Setter(auth_token, self, t, {'user' : user, 'organization' : organization})
        t.blame = facade.managers.BlameManager().create(auth_token)
        t.save()
        self.authorizer.check_create_permissions(auth_token, t)
        return t

# vim:tabstop=4 shiftwidth=4 expandtab
