from django.conf import settings
from decorators import authz

@authz
def setup(machine):
    methods = [
        {'name' : 'auth.actor_is_guest', 'params' : {}},
    ]
    arb_perm_list = ['check_usernames']
    crud = {}
    if 'test_services' in settings.INSTALLED_APPS:
        crud['NotASubclassOfPRModel'] = {
            'c': True,
            'r': set(),
            'u': set(),
            'd': False,
        }
    machine.add_acl_to_role('Guest', methods, crud, arb_perm_list)
