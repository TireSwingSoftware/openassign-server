"""
Venue manager class
"""

from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
import facade
from pr_services import pr_time

class VenueManager(ObjectManager):
    """
    Manage Venues in the Power Reg system
    """
    GETTERS = {
        'address': 'get_address',
        'contact': 'get_general',
        'events': 'get_many_to_one',
        'hours_of_operation': 'get_general',
        'name': 'get_general',
        'owner': 'get_foreign_key',
        'phone': 'get_general',
        'region': 'get_foreign_key',
        'rooms': 'get_many_to_one',
    }
    SETTERS = {
        'address': 'set_address',
        'contact': 'set_general',
        'events': 'set_many',
        'hours_of_operation': 'set_general',
        'name': 'set_general',
        'owner': 'set_foreign_key',
        'phone': 'set_general',
        'region': 'set_foreign_key',
        'rooms': 'set_many',
    }
    def __init__(self):
        """ constructor """

        ObjectManager.__init__(self)
        self.my_django_model = facade.models.Venue

    @service_method
    def create(self, auth_token, name, phone, region, optional_attributes=None):
        """
        Common method for Venue creation

        Makes sure that the old address does not get orphaned.

        @param auth_token           The actor's authentication token
        @param name                 Name for the Venue
        @param phone                Phone number
        @param region               Foreign Key for a region
        @param optional_attributes  Dictionary of optional arguments
        @return                     a reference to the newly created Venue
        """

        if optional_attributes is None:
            optional_attributes = {}

        r = self._find_by_id(region, facade.models.Region)
        venue_blame = facade.managers.BlameManager().create(auth_token)
        v = self.my_django_model(name=name, phone=phone, region=r, blame=venue_blame)
        v.owner = auth_token.user
        if optional_attributes:
            facade.subsystems.Setter(auth_token, self, v, optional_attributes)
        v.save()
        self.authorizer.check_create_permissions(auth_token, v)
        return v

    @service_method
    def get_available_venues(self, auth_token, start, end, requested_fields=None):
        """
        Query for venues with avaiable rooms during the specified timespan

        @param auth_token         The actor's authentication token
        @param start              Start time as ISO8601 string or datetime
        @param end                End time as ISO8601 string or datetime
        @param requested_fields   Optional list of field names to be returned
        @return                   a filtered list of available venues, with the requested fields
        """
        # convert time arguments from isoformat string to datetime, if not already
        if isinstance(start, basestring):
            start = pr_time.iso8601_to_datetime(start)
        if isinstance(end, basestring):
            end = pr_time.iso8601_to_datetime(end)

        # find any conflicting sessions, remove their room IDs
        available_room_ids = facade.models.Room.objects.all().values_list('id', flat=True)
        blocked_room_ids = [ ]
        conflicting_sessions = (
            facade.models.Session.objects.filter(start__lt=end) &
            facade.models.Session.objects.filter(end__gt=start)
        )

        blocked_room_ids.extend( conflicting_sessions.values_list('room', flat=True) )
        # remove duplicates from the list of blocked IDs
        blocked_room_ids = list(set(blocked_room_ids))
        available_room_ids = [i for i in available_room_ids if i not in blocked_room_ids]

        # query for available rooms
        available_venue_ids = facade.models.Room.objects.filter( 
            id__in = available_room_ids).values_list('venue', flat=True)

        return self.get_filtered(auth_token, 
            {'member' : {'id' : available_venue_ids} },
            requested_fields or [])
        

# vim:tabstop=4 shiftwidth=4 expandtab
