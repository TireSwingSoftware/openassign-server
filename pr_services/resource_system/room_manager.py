"""
Room manager class
"""

from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
import facade
from pr_services import pr_time

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

    @service_method
    def get_available_rooms(self, auth_token, start, end, room_ids, requested_fields=None):
        """
        Query rooms available (from a selected set of room IDs) during the specified timespan

        @param auth_token         The actor's authentication token
        @param start              Start time as ISO8601 string or datetime
        @param end                End time as ISO8601 string or datetime
        @param room_ids           Required list of room IDs to check
        @return                   a result set produced by get_filtered()
        """
        requested_fields = requested_fields or []
        test_room_ids = room_ids or [ ]

        # convert time arguments from isoformat string to datetime, if not already
        if isinstance(start, basestring):
            start = pr_time.iso8601_to_datetime(start)
        if isinstance(end, basestring):
            end = pr_time.iso8601_to_datetime(end)
        
        # find any conflicting sessions, remove their room IDs
        blocked_room_ids = [ ]
        conflicting_sessions = (
            facade.models.Session.objects.filter(start__lt=end) &
            facade.models.Session.objects.filter(end__gt=start)
        )
        blocked_room_ids.extend( conflicting_sessions.values_list('room', flat=True) )
        # remove duplicates from the list of blocked IDs
        blocked_room_ids = list(set(blocked_room_ids))
        available_room_ids = [i for i in test_room_ids if i not in blocked_room_ids]
        # query for available rooms
        e = facade.models.Room.objects.filter( 
            id__in = available_room_ids)
        # iterate over these objects, filtering out those from blacked-out
        # venues and any whose IDs are hidden from this user
        avail_ids = []
        auth = self.authorizer
        venue_manager = facade.managers.VenueManager()
        available_venues = venue_manager.get_available_venues(auth_token, start, end)
        avail_venue_ids = [ven_info['id'] for ven_info in available_venues]
        for pr_object in e.iterator():
            if pr_object.venue.id not in avail_venue_ids:
                continue
            auth.check_read_permissions(auth_token, pr_object, ['id'])
            avail_ids.append(str(pr_object.id))
        return self.get_filtered(auth_token, {'member' : {'id' : avail_ids}}, requested_fields)


# vim:tabstop=4 shiftwidth=4 expandtab
