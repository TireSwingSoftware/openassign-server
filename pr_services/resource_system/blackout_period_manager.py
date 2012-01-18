"""
BlackoutPeriod manager class
"""

from datetime import date, datetime, timedelta
from pr_services import pr_time
from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
import facade
import logging

class BlackoutPeriodManager(ObjectManager):
    """
    Manage BlackoutPeriods (0..* for each Venue) in the Power Reg system
    """
    GETTERS = {
        'venue': 'get_foreign_key',
        'start': 'get_time',
        'end': 'get_time',
        'description': 'get_general',
    }
    SETTERS = {
        'venue': 'set_foreign_key',
        'start': 'set_time',
        'end': 'set_time',
        'description': 'set_general',
    }
    def __init__(self):
        """ constructor """

        ObjectManager.__init__(self)
        self.my_django_model = facade.models.BlackoutPeriod

    @service_method
    def create(self, auth_token, venue, start, end, description=None):
        """
        Create a new BlackoutPeriod

        @param venue            foreign key for the blacked-out venue
        @param start            start time as ISO8601 string
        @type start string
        @param end              end time as ISO8601 string
        @type end string
        @param description      description of the BlackoutPeriod
        @type description string
        @return                 a reference to the newly created BlackoutRegion
        """

        # allow fine-grained start and end (to the minute)
        if not isinstance(start, date):
            start = pr_time.iso8601_to_datetime(start).replace(microsecond=0,
                    second=0)
        if not isinstance(end, date):
            end = pr_time.iso8601_to_datetime(end).replace(microsecond=0,
                    second=0)

        bp = self.my_django_model.objects.create(
            venue=self._find_by_id(venue, facade.models.Venue),
            start=start, 
            end=end, 
            description=description)
        bp.save()
        self.authorizer.check_create_permissions(auth_token, bp)
        return bp

# vim:tabstop=4 shiftwidth=4 expandtab
