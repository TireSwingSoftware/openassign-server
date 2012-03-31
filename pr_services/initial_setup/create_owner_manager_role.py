
from pr_services.initial_setup.admin_privs import admin_privs

def setup(machine):
    role_name = 'Owner Manager'
    checks = [
        { # Allow method calls as long as the user has the orgrole
            'name': 'method.caller_has_orgrole',
            'params': {'role_name': role_name}
        },
        {
            'name': 'membership.orgrole.actor_role_in_actee_org',
            'params': {'role_name': role_name}
        }
    ]
    create = (
        'Assignment',
        'Event',
        'Session',
        'Task', # includes all subclasses
    )
    read = (
        'Assignment',
        'Event',
        'Exam',  # expose additional attributes for Exams
        'FileDownload',
        'FileUpload',
        'Session',
        'SessionUserRoleRequirement',
        'Task', # includes all subclasses
        'User',
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

