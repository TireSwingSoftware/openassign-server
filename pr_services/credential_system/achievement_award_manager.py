"""
achievement award manager class
"""

from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
import facade

class AchievementAwardManager(ObjectManager):
    """
    Manage achievement awards in the Power Reg system
    """

    GETTERS = {
        'achievement': 'get_foreign_key',
        'assignment': 'get_foreign_key',
        'date': 'get_time',
        'user': 'get_foreign_key',
    }
    SETTERS = {
        'achievement': 'set_foreign_key',
        'assignment': 'set_foreign_key',
        'date': 'set_time',
        'user': 'set_foreign_key',
    }
    my_django_model = facade.models.AchievementAward

    @service_method
    def create(self, auth_token, achievement, user, optional_attributes=None):
        """
        Create a new achievement award

        @param achievement          PK of an Achievement 
        @param user                 PK of a User
        @param optional_attributes  none currently supported
        @return                         a reference to the newly created achievement
        """

        achievement_award = self.my_django_model.objects.create(
            user = self._find_by_id(user, facade.models.User),
            achievement = self._find_by_id(achievement, facade.models.Achievement),
        )

        self.authorizer.check_create_permissions(auth_token, achievement_award)
        return achievement_award

# vim:tabstop=4 shiftwidth=4 expandtab
