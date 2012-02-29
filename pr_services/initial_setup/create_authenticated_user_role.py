from decorators import authz

@authz
def setup(machine):
    methods = [
        {'name' : 'auth.actor_is_authenticated', 'params' : {}},
        {'name' : 'membership.actor_is_in_actee_which_is_a_group', 'params' : {}},
    ]
    crud = {
        'Group' : {
            'c' : False,
            'r' : set(('name',)),
            'u' : set(),
            'd' : False,
        },
    }
    machine.add_acl_to_role('Authenticated User', methods, crud)
