"""
Event manager class
"""

from datetime import date

from pr_services import pr_time
from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method

import facade
import settings

class EventManager(ObjectManager):
    """
    Manage Events in the Power Reg system
    """

    GETTERS = {
        'description': 'get_general',
        'end': 'get_time',
        'event_template': 'get_foreign_key',
        'external_reference': 'get_general',
        'facebook_message': 'get_general',
        'lag_time': 'get_general',
        'lead_time': 'get_general',
        'name': 'get_general',
        'notify_cfgs': 'get_many_to_one',
        'organization': 'get_foreign_key',
        'owner': 'get_foreign_key',
        'product_line': 'get_foreign_key',
        'region': 'get_foreign_key',
        'sessions': 'get_many_to_one',
        'start': 'get_time',
        'status': 'get_status_from_event',
        'title': 'get_general',
        'twitter_message': 'get_general',
        'url': 'get_general',
        'venue': 'get_foreign_key',
    }
    SETTERS = {
        'description': 'set_general',
        'end': 'set_time',
        'event_template': 'set_foreign_key',
        'external_reference': 'set_general',
        'facebook_message': 'set_general',
        'lag_time': 'set_general',
        'lead_time': 'set_general',
        'name': 'set_general',
        'notify_cfgs': 'set_many',
        'organization': 'set_foreign_key',
        'owner': 'set_foreign_key',
        'product_line': 'set_foreign_key',
        'region': 'set_foreign_key',
        'start': 'set_time',
        'title': 'set_general',
        'twitter_message': 'set_general',
        'url': 'set_general',
        'venue': 'set_foreign_key',
    }
    def __init__(self):
        """ constructor """

        ObjectManager.__init__(self)
        self.my_django_model = facade.models.Event

    @service_method
    def create(self, auth_token, name_prefix, title, description, start, end, organization,
            optional_attributes=None):

        """
        Create a new Event.

        A region or a venue must be provided.

        @param name_prefix          prefix for the human-readable unique identifier 'name'
        @param title                title of the Event
        @param description          description of the Event
        @param start                Date on which the Event starts, as an ISO8601 string.
                                    If you provide hour, minute, or second, they will be ignored.
        @param end                  Date on which the Event ends, as an ISO8601 string.
                                    If you provide hour, minute, or second, they will be ignored.
        @param organization         FK for organization
        @param optional_attributes  currently only 'venue', 'region', 'event_template', 'product_line', 'lead_time'
                                    and 'sessions'. For 'sessions', provide a list of dicts with all attributes for
                                    the SessionManager.create() method except 'event', which will obviously be
                                    filled in by this method after the event is created.
        @return                     a reference to the newly created Event
        """

        if optional_attributes is None:
            optional_attributes = {}

        if not isinstance(start, date):
            start = pr_time.iso8601_to_datetime(start).replace(microsecond=0,
                    second=0, minute=0, hour=0)
        if not isinstance(end, date):
            end = pr_time.iso8601_to_datetime(end).replace(microsecond=0,
                    second=0, minute=0, hour=0)

        e = self.my_django_model.objects.create(title=title,
                description=description, start=start, end=end,
                organization=self._find_by_id(organization, facade.models.Organization),
                owner=auth_token.user)

        e.name = '%s%d' % (name_prefix if name_prefix is not None else '', e.id)
        if 'lag_time' not in optional_attributes:
            optional_attributes['lag_time'] = settings.DEFAULT_EVENT_LAG_TIME

        # create sessions if provided.
        if 'sessions' in optional_attributes:
            e.save()
            session_manager = facade.managers.SessionManager()
            for session in optional_attributes['sessions']:
                session['event'] = e.pk
                session_manager.create(auth_token, **session)
            del optional_attributes['sessions']

        facade.subsystems.Setter(auth_token, self, e, optional_attributes)
        e.save()

        self.authorizer.check_create_permissions(auth_token, e)
        return e

# vim:tabstop=4 shiftwidth=4 expandtab
