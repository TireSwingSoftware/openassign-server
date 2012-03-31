
from pr_services.initial_setup.admin_privs import admin_privs

def setup(machine):
    role_name = 'Administrator'
    checks = [
        { # Allow method calls as long as the user has the orgrole
            'name': 'method.caller_has_orgrole',
            'params': {'role_name': role_name}
        },
        { # Check the actor has the OrgRole for the actee's org
            'name': 'membership.orgrole.actor_role_in_actee_org',
            'params': {'role_name': role_name}
        }
    ]
    privs = {}

    # the organization admin role will have full admin privileges
    # on the following model objects.
    full_admin_objects = (
        'Achievement',
        'Answer',
        'Assignment',
        'Credential',
        'CurriculumEnrollment',
        'CurriculumEnrollmentUserAssociation',
        'CurriculumTaskAssociation',
        'Event',
        'Exam', # subclass of Task
        'FileDownload', # subclass of Task
        'FileUpload', # subclass of Task
        'Session',
        'SessionUserRoleRequirement', # subclass of Task
        'User',
        'UserOrgRole',
        'Question',
        'QuestionPool',
        )
    for name in full_admin_objects:
        privs[name] = admin_privs[name]

    read_only_objects = (
        'CredentialType',
        'Resource',
        'Response', # for exams
        'Task',
        'Venue')
    for name in read_only_objects:
        read_privs = admin_privs[name]['r']
        if name in privs:
            privs[name]['r'] = read_privs
        else:
            privs[name] = dict(r=read_privs)

    privs.update({
        'CredentialType': {
            'c': True
        },
        'AssignmentManager': {
            'methods': set(('email_task_assignees', ))
        },
        'ExamManager': {
            'methods': set(('export_to_xml', 'create_from_xml'))
        },
    })

    machine.add_acl_to_role('Organization Administrator', checks, privs)
