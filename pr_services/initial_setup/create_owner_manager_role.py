
from pr_services.initial_setup.admin_privs import admin_privs

import facade

def setup(machine):
    role_name = 'Owner Manager'
    checks = [
        { # Allow method calls as long as the user has the orgrole
            'name': 'method.caller_has_orgrole',
            'params': {'role_name': role_name}
        },
        # XXX: Perform regular OrgRole checks for create, update, and delete
        # operations on all objects.
        {
            'name': 'membership.orgrole.actor_has_role_for_actee',
            'params': {
                'role_name': role_name,
                'restricted_ops': frozenset('cud')
            }
        },
        { # XXX: Exclude Task from the OrgRole check when doing
          # read operations
            'name': 'membership.orgrole.actor_has_role_for_actee',
            'params': {
                'role_name': role_name,
                'restricted_ops': frozenset('r'),
                'excluded_types': frozenset((facade.models.Task,))
            }
        },
        # Ensure the actor is authenticated and has the proper role for
        # anything skipped above.
        {
            'name': 'membership.orgrole.actor_has_orgrole',
            'params': {'role_name': role_name}
        },
    ]
    create = (
        'Assignment',
        'Event',
        'Session',
        'Task', # includes all subclasses
    )
    read = (
        'Assignment',
        'Credential',
        'CredentialType',
        'Event',
        'Exam',
        'FileDownload',
        'FileUpload',
        'OrgRole',
        'Organization',
        'Session',
        'SessionUserRoleRequirement',
        'Task',
        'User',
        'UserOrgRole',
    )
    update = (
        'Assignment',
        'Event',
        'Exam',
        'FileDownload',
        'FileUpload',
        'Session',
        'SessionUserRoleRequirement',
        'Task', # includes all subclasses
    )
    privs = {}
    for op, names in (('c', create), ('r', read), ('u', update)):
        for name in names:
            privs.setdefault(name, {})[op] = admin_privs[name][op]

    privs.update({
        'ExamManager': {
            'methods': set(('export_to_xml', 'create_from_xml'))
        },
    })
    machine.add_acl_to_role(role_name, checks, privs)

