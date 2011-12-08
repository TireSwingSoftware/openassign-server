"""
Room manager class
"""

from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
import facade

class RoomManager(ObjectManager):
    """
    Manage Rooms in the Power Reg system

    This class manages physical addresses.
    """
    GETTERS = {
        'capacity': 'get_general',
        'name': 'get_general',
        'venue': 'get_foreign_key',
        'venue_address': 'get_general',
        'venue_name': 'get_general',
    }
    SETTERS = {
        'capacity': 'set_general',
        'name': 'set_general',
        'venue': 'set_foreign_key',
    }
    def __init__(self):
        """ constructor """

        ObjectManager.__init__(self)
        self.my_django_model = facade.models.Room

    @service_method
    def create(self, auth_token, name, venue, capacity):
        """
        Create a new Room

        @param name               Name for the Room
        @param venue              Foreign Key for a venue
        @param capacity           Number of people who can be in the Room
        @return                   a reference to the newly created Room
        """

        new_room = self._create(auth_token, name, venue, capacity)
        self.authorizer.check_create_permissions(auth_token, new_room)
        return new_room

    def _create(self, auth_token, name, venue, capacity):
        """
        Common method for Room creation

        @param name               Name for the Room
        @param venue              Foreign Key for a venue
        @param capacity           Number of people who can be in the Room
        @return                   a reference to the newly created Room
        """

        room_blame = facade.managers.BlameManager().create(auth_token)
        r = self.my_django_model(name = name, capacity = capacity, blame=room_blame)
        facade.subsystems.Setter(auth_token, self, r, {'venue' : venue})
        r.save()
        return r

# vim:tabstop=4 shiftwidth=4 expandtab
