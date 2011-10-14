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

    def __init__(self):
        """ constructor """

        ObjectManager.__init__(self)
        self.setters.update({
            'name' : 'set_general',
            'description' : 'set_general',
            'resource_types' : 'set_many',
            'session_resource_type_requirements' : 'set_many',
        })
        self.getters.update({
            'name' : 'get_general',
            'description' : 'get_general',
            'resource_types' : 'get_many_to_many',
            'session_resource_type_requirements' : 'get_many_to_one',
        })
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
    # TODO: confirm that service_method is appropriate here
    def find_available_resources(self, auth_token, start, end):
        session_manager = facade.managers.SessionManager()
        res_requirement_manager = facade.managers.SessionResourceTypeRequirementManager()
        # start with all IDs, then filter out those who are associated with sessions during this time
        available_resource_info = self.get_filtered(auth_token, {})
        available_resource_ids = [res['id'] for res in available_resource_info]
        # eg,  [{'id': 1}, {'id': 2}, {'id': 3}, {'id': 4}]
        
        # convert time arguments from isoformat string to datetime, if not already
        if isinstance(start, basestring):
            start = pr_time.iso8601_to_datetime(start)
        if isinstance(end, basestring):
            end = pr_time.iso8601_to_datetime(end)
            
        conflicting_sessions = session_manager.get_filtered(auth_token,
            { 'greater_than_or_equal' : {'start' : start },
              'less_than_or_equal' : {'end' : end } }, ['name', 'status', 'session_resource_type_requirements'])
        
        for sess in conflicting_sessions:
            for req_id in sess['session_resource_type_requirements']:
                blocked_resource_info = res_requirement_manager.get_filtered(auth_token,
                     {'member' : {'resources' : [req_id]} }, [])
                blocked_resource_ids = [res['id'] for res in blocked_resource_info]
            
                # chase resource-type requirements to any underlying resources
                for blocked_id in blocked_resource_ids:
                    if blocked_id in available_resource_ids:
                        available_resource_ids.remove( blocked_id )
                
        return self.get_filtered(auth_token, {'member' : {'id' : available_resource_ids} }, ['name', 'description'])

    @service_method    
    def resource_used_during(self, auth_token, resource_id, start, end):
        # A more targeted "probe" for a particular Resource during a specified time span.
        # Returns True if the resource is already scheduled within the chosen duration, False if not
        res_requirement_manager = facade.managers.SessionResourceTypeRequirementManager()
        session_manager = facade.managers.SessionManager()
        related_sessions = res_requirement_manager.get_sessions_using_resource(auth_token, resource_id)

        if isinstance(start, basestring):
            start = pr_time.iso8601_to_datetime(start)
        if isinstance(end, basestring):
            end = pr_time.iso8601_to_datetime(end)
    
        session_ids = [s['id'] for s in related_sessions ]  # TODO: use list comprehension to extract just IDs?
        conflicting_sessions = session_manager.get_filtered(auth_token, 
            { 'member' : {'id': session_ids},
              'greater_than_or_equal' : {'start' : start},
              'less_than_or_equal' : {'end' : end}
            }, [])
        if len(conflicting_sessions) > 0:
            return True
        return False # no conflict found
        
# vim:tabstop=4 shiftwidth=4 expandtab
