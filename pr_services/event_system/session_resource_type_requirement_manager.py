"""
SessionResourceTypeRequirement manager class
"""
from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
import facade

class SessionResourceTypeRequirementManager(ObjectManager):
    """
    Manage SessionResourceTypeRequirements in the Power Reg system
    """

    def __init__(self):
        """ constructor """

        ObjectManager.__init__(self)
        self.getters.update({
            'session' : 'get_foreign_key',
            'max' : 'get_general',
            'min' : 'get_general',
            'resource_type' : 'get_foreign_key',
            'resources' : 'get_many_to_many',
        })
        self.setters.update({
            'session' : 'set_foreign_key',
            'max' : 'set_general',
            'min' : 'set_general',
            'resource_type' : 'set_foreign_key',
            'resources' : 'set_many',
        })
        self.my_django_model = facade.models.SessionResourceTypeRequirement

    @service_method
    def create(self, auth_token, session_id, resource_type_id, min, max, resource_ids=None):
        """
        Create a new SessionResourceTypeRequirement
        
        @param session_id         Primary key for an session
        @param resource_type_id   Primary key for an resource_type
        @param min                Minimum number required
        @param max                Maximum number allowed
        @param resource_ids       Array of resource foreign keys
        @return                   A reference to the newly created SessionResourceTypeRequirement
        """

        if resource_ids is None:
            resource_ids = []
            
        session_instance = self._find_by_id(session_id, facade.models.Session)
        # if there are already assigned resources, make sure they're free during this session
        if len(resource_ids) > 0:
            for res_id in resource_ids:
                scheduled_sessions = self.get_sessions_using_resource(auth_token, res_id)
                
                for test_session in scheduled_sessions:
                    conflict_found = False
                    # TODO: Add buffer time to allow for transportation, maintenance of resources? 
                    # This is hard to anticipate for all possible resource types!
                    if test_session.start > session_instance.start and test_session.start < session_instance.end:
                        conflict_found = True
                    if test_session.end > session_instance.start and test_session.end < session_instance.end:
                        conflict_found = True
                    if conflict_found:
                        # an assigned resource is't free during this time period
                        return None
        
        resource_type_instance = self._find_by_id(resource_type_id, facade.models.ResourceType)
        e = self.my_django_model(session = session_instance,
                resource_type=resource_type_instance, min=min, max=max)
        # We must save so that we can get a primary key, and thus establish many-to-many
        # relationships below
        e.save()
        if resource_ids:
            facade.subsystems.Setter(auth_token, self, e, {'resources' : { 'add' : resource_ids}})
        self.authorizer.check_create_permissions(auth_token, e)
        return e

    @service_method
    def get_sessions_using_resource(self, auth_token, resource_id, activeOnly=False):
        # if activeOnly is True, return only Sessions whose status is active
        related_sessions = facade.models.Session.resource_tracker.get_sessions_using_resource(resource_id, activeOnly)
        # TODO: impose added security via get_filtered()?
        return related_sessions

# vim:tabstop=4 shiftwidth=4 expandtab
