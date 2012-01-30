"""
TrainingUnitAuthorization manager class
"""

from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
import facade

class TrainingUnitAuthorizationManager(ObjectManager):
    """
    Manage TrainingUnitAuthorizations in the Power Reg system
    """

    GETTERS = {
        'end': 'get_time',
        'max_value': 'get_general',
        'notes': 'get_many_to_many',
        'start': 'get_time',
        'training_unit_account': 'get_foreign_key',
        'used_value': 'get_used_value_from_training_unit_authorization',
        'user': 'get_foreign_key',
    }
    SETTERS = {
        'end': 'set_time',
        'max_value': 'set_general',
        'notes': 'set_many',
        'start': 'set_time',
        'training_unit_account': 'set_foreign_key',
        'user': 'set_foreign_key',
    }
    def __init__(self):
        """ constructor """

        ObjectManager.__init__(self)
        self.my_django_model = facade.models.TrainingUnitAuthorization

    @service_method
    def create(self, auth_token, training_unit_account, user, start, end, max_value):
        """
        Create a new TrainingUnitAuthorization

        @param training_unit_account    Foreign Key for a training unit account
        @param user                     Foreign Key for a user
        @param start                    Start time as ISO8601 string
        @param end                      End time as ISO8601 string
        @param max_value                Integer representing how many training units may be used
        @return                         a reference to the newly created TrainingUnitAuthorization
        """

        blame = facade.managers.BlameManager().create(auth_token)
        t = self.my_django_model(max_value = max_value, blame = blame)
        facade.subsystems.Setter(auth_token, self, t, {
                'training_unit_account' : training_unit_account,
                'user' : user,
                'start' : start,
                'end' : end,
        })

        t.save()
        self.authorizer.check_create_permissions(auth_token, t)
        return t

# vim:tabstop=4 shiftwidth=4 expandtab
