from decorators import authz

@authz
def setup(machine):
    methods = [
        {'name' : 'membership.actor_is_group_manager', 'params' : {}},
    ]
    crud = {
        'Group' : {
            'c' : False,
            'r' : set(('managers', 'name', 'users')),
            'u' : set(('managers', 'name', 'users')),
            'd' : False,
        },
    }
    machine.add_acl_to_role('Group Manager', methods, crud)
