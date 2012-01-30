"""
Resource manager class
"""

from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
import facade
from pr_services import pr_time

class ResourceManager(ObjectManager):
    """
    Manage Resources in the Power Reg system
    """
    SETTERS = {
        'description': 'set_general',
        'name': 'set_general',
        'notes': 'set_many',
        'resource_types': 'set_many',
        'session_resource_type_requirements': 'set_many',
    }
    GETTERS = {
        'description': 'get_general',
        'name': 'get_general',
        'notes': 'get_many_to_many',
        'resource_types': 'get_many_to_many',
        'session_resource_type_requirements': 'get_many_to_one',
    }
    def __init__(self):
        """ constructor """

        ObjectManager.__init__(self)
        self.my_django_model = facade.models.Resource

    @service_method
    def create(self, auth_token, name, optional_attributes=None):
        """
        Create a new Resource

        @param name               name of the Resource
        @param optional_attributes    Optional attribute values indexed by name
        @return                   instance of Resource
        """
        if optional_attributes is None:
            optional_attributes = {}

        r = self.my_django_model(name=name)
        r.save()
        if optional_attributes:
            facade.subsystems.Setter(auth_token, self, r, optional_attributes)
            r.save()
        self.authorizer.check_create_permissions(auth_token, r)
        return r

    @service_method
    def find_available_resources(self, auth_token, start, end, requested_fields=['name','description']):
        """
        Return a list of resources that are available during the specified timespan

        @param start              Start time as ISO8601 string or datetime
        @param end                End time as ISO8601 string or datetime
        @param requested_fields   Optional list of field names to be returned
        @return                   a filtered list of available resources, with the requested fields
        """
        # build a list of blocked resources, then exclude them from final results
        blocked_resource_ids = []

        # convert time arguments from isoformat string to datetime, if not already
        if isinstance(start, basestring):
            start = pr_time.iso8601_to_datetime(start)
        if isinstance(end, basestring):
            end = pr_time.iso8601_to_datetime(end)

        # get the intersection of two filters (modifies query)
        conflicting_sessions = (
            facade.models.Session.objects.filter(start__lt=end) &
            facade.models.Session.objects.filter(end__gt=start)
        )
        for sess in conflicting_sessions:
            for req in sess.session_resource_type_requirements.all():
                # add its resource IDs to our growing list
                blocked_resource_ids.extend( req.resources.all().values_list('id', flat=True) )

        # remove duplicates from the list of blocked IDs
        blocked_resource_ids = list(set(blocked_resource_ids))
        # return all NON-blocked resources (ie, those still available during this time)
        return self.get_filtered(auth_token, {'not': {'member' : {'id' : blocked_resource_ids} } }, requested_fields)

    @service_method
    def resource_used_during(self, auth_token, resource_id, start, end):
        """
        Probe for a particular Resource during a specified timespan

        @param resource_id        ID of the Resource
        @param start              Start time as ISO8601 string or datetime
        @param end                End time as ISO8601 string or datetime
        @return                   True if resource is already scheduled within the chosen duration, False if not
        """
        related_sessions = facade.models.Session.resource_tracker.get_sessions_using_resource(resource_id)

        if isinstance(start, basestring):
            start = pr_time.iso8601_to_datetime(start)
        if isinstance(end, basestring):
            end = pr_time.iso8601_to_datetime(end)

        # This allows identical boundary values (eg, identical test-end and session-start times)
        conflicting_sessions = (
            related_sessions.filter(start__lt=end) &
            related_sessions.filter(end__gt=start)
        )

        if conflicting_sessions.count() > 0:
            return True
        return False # no conflict found

# vim:tabstop=4 shiftwidth=4 expandtab
