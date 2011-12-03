from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
import facade

class ConditionTestManager(ObjectManager):
    """
    Manage Condition Tests
    """
    GETTERS = {
        'companies': 'get_many_to_many',
        'condition_test_collection': 'get_foreign_key',
        'credentials': 'get_many_to_many',
        'end': 'get_time',
        'events': 'get_many_to_many',
        'groups': 'get_many_to_many',
        'match_all_defined_parameters': 'get_general',
        'sequence': 'get_general',
        'session_user_role_requirements': 'get_many_to_many',
        'sessions': 'get_many_to_many',
        'start': 'get_time',
    }
    SETTERS = {
        'companies': 'set_many',
        'condition_test_collection': 'set_foreign_key',
        'credentials': 'set_many',
        'end': 'set_time',
        'events': 'set_many',
        'groups': 'set_many',
        'match_all_defined_parameters': 'set_general',
        'sequence': 'set_general',
        'session_user_role_requirements': 'set_many',
        'sessions': 'set_many',
        'start': 'set_time',
    }
    def __init__(self):

        ObjectManager.__init__(self)
        self.my_django_model = facade.models.ConditionTest
        self.setter = facade.subsystems.Setter

    @service_method
    def create(self, auth_token, sequence, condition_test_collection,
            match_all_defined_parameters, optional_attributes = None):
        """
        Create a new ConditionTest

        @param sequence                     integer defining the order of evaluation relative
                                            to other tests in the collection
        @param condition_test_collection    PK of the related collection
        @param match_all_defined_parameters boolean determining if this is an AND or OR operation
        """

        blame = facade.managers.BlameManager().create(auth_token)
        collection = self._find_by_id(condition_test_collection, facade.models.ConditionTestCollection)

        new_condition_test = self.my_django_model.objects.create(sequence=sequence, blame=blame,
                match_all_defined_parameters=match_all_defined_parameters, condition_test_collection=collection)
        if optional_attributes:
            self.setter(auth_token, self, new_condition_test, optional_attributes)
        new_condition_test.save()

        self.authorizer.check_create_permissions(auth_token, new_condition_test)
        return new_condition_test

