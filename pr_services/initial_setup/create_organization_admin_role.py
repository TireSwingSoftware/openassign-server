
from pr_services.initial_setup.admin_privs import admin_privs

import facade

facade.import_models(locals())

def setup(machine):
    role_name = 'Administrator'
    checks = [
        { # Allow method calls as long as the user has the orgrole
            'name': 'method.caller_has_orgrole',
            'params': {'role_name': role_name}
        },
        # XXX: Perform regular OrgRole checks for create, update, and delete
        # operations on all objects.
        {'name': 'membership.orgrole.actor_has_role_for_actee',
            'params': {'role_name': role_name,
                'restricted_ops': frozenset('cud'),
            }
        },
        # XXX: Exclude several types from the OrgRole check when doing
        # read operations
        {'name': 'membership.orgrole.actor_has_role_for_actee',
            'params': {'role_name': role_name,
                'restricted_ops': frozenset('r'),
                'excluded_types': frozenset((
                    Curriculum,
                    CurriculumEnrollment,
                    Exam,
                    FileDownload,
                    FileUpload,
                    SessionUserRoleRequirement,
                    Task,
                    TaskFee,
                    ))
                }
        },
        # Ensure the actor is authenticated and has the proper role for
        # anything skipped above.
        {
            'name': 'membership.orgrole.actor_has_orgrole',
            'params': {'role_name': role_name}
        },
    ]
    privs = {}

    # the organization admin role will have full admin privileges
    # on the following model objects.
    full_admin_objects = (
        'Achievement',
        'Answer',
        'Assignment',
        'Credential',
        'CredentialType',
        'Curriculum',
        'CurriculumEnrollment',
        'CurriculumEnrollmentUserAssociation',
        'CurriculumTaskAssociation',
        'Event',
        'Exam', # subclass of Task
        'FileDownload', # subclass of Task
        'FileUpload', # subclass of Task
        'Group',
        'Question',
        'QuestionPool',
        'Session',
        'SessionUserRoleRequirement', # subclass of Task
        'TaskFee',
        'User',
        'UserOrgRole',
        )
    for name in full_admin_objects:
        privs[name] = admin_privs[name]

    read_only_objects = (
        'CredentialType',
        'Organization',
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
        'AssignmentManager': {
            'methods': set(('email_task_assignees', ))
        },
        'ExamManager': {
            'methods': set(('export_to_xml', 'create_from_xml'))
        },
    })

    machine.add_acl_to_role('Organization Administrator', checks, privs)
