
from pr_services.initial_setup.admin_privs import admin_privs

import facade

facade.import_models(locals())

def setup(machine):
    role_name = 'Serv Dealer Admin'
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
                    Event,
                    EventTemplate,
                    Exam,
                    FileDownload,
                    FileUpload,
                    OrgRole,
                    Organization,
                    Session,
                    SessionTemplate,
                    SessionUserRoleRequirement,
                    Task,
                    TaskBundle,
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
    create = (
        'Assignment',
        'Exam',
        'FileDownload',
        'FileDownloadAttempt',
        'FileUpload',
        'FileUploadAttempt',
        'SessionUserRoleRequirement',
        'Task',
        'TaskBundle',
        'User',
    )
    read = (
        'Achievement',
        'AchievementAward',
        'Assignment',
        'Credential',
        'CredentialType',
        'Curriculum',
        'CurriculumEnrollment',
        'CurriculumEnrollmentUserAssociation',
        'Event',
        'EventTemplate',
        'Exam',
        'FileDownload',
        'FileDownloadAttempt',
        'FileUpload',
        'FileUploadAttempt',
        'OrgRole',
        'Organization',
        'Session',
        'SessionTemplate',
        'SessionUserRoleRequirement',
        'Task',
        'TaskBundle',
        'User',
    )
    update = (
        'Exam',
        'FileDownload',
        'FileDownloadAttempt',
        'FileUpload',
        'FileUploadAttempt',
        'SessionUserRoleRequirement',
        'Task',
        'TaskBundle',
    )
    privs = {
        'Assignment': {
            'u': set(('status', ))
        },
        'User': {
            'u': set(('status', ))
        }
    }
    for op, names in (('c', create), ('r', read), ('u', update)):
        for name in names:
            privs.setdefault(name, {})[op] = admin_privs[name][op]

    machine.add_acl_to_role(role_name, checks, privs)
