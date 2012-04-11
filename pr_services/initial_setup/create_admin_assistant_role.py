
from pr_services.initial_setup.admin_privs import admin_privs

import facade

facade.import_models(locals())

def setup(machine):
    role_name = 'Admin Assistant'
    checks = [
        { # Allow method calls as long as the user has the orgrole
            'name': 'method.caller_has_orgrole',
            'params': {
                'role_name': role_name
            }
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
        { # XXX: Exclude several types from the OrgRole check when doing
          # read operations
            'name': 'membership.orgrole.actor_has_role_for_actee',
            'params': {
                'role_name': role_name,
                'restricted_ops': frozenset('r'),
                'excluded_types': frozenset((
                    Curriculum,
                    Event,
                    EventTemplate,
                    Session,
                    SessionTemplate,
                    Task,
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
        'CurriculumEnrollmentUserAssociation',
        'CurriculumTaskAssociation',
        'Task',
        'User',
        'UserOrgRole',
    )
    read = (
        'Assignment',
        'Curriculum',
        'CurriculumEnrollment',
        'CurriculumEnrollmentUserAssociation',
        'CurriculumTaskAssociation',
        'Event',
        'EventTemplate',
        'Exam',
        'FileDownload',
        'FileDownloadAttempt',
        'FileUpload',
        'FileUploadAttempt',
        'Organization',
        'Session',
        'SessionTemplate',
        'SessionUserRoleRequirement',
        'Task',
        'User',
        'UserOrgRole',
    )
    update = (
        'UserOrgRole',
    )

    # supplement the above privs with more explicit definitions
    privs = {
        'Assignment': {
            'u': set(('status', )),
        },
        'CurriculumEnrollment': {
            'u': set(('users', ))
        },
        'User': {
            'u': set(('status', 'organizations', 'roles'))
        }
# TODO(jcon): Add when other ACLs are added for the following views.
#        'AssignmentManager': {
#            'methods': set((
#                'detailed_exam_view',
#                'detailed_file_download_view',
#                'detailed_view',
#                'exam_view',
#                'file_download_view',
#                'file_upload_view',
#                'session_view',
#                'transcript_view',
#                'view',
#                ))
#        }
    }
    for op, names in (('c', create), ('r', read), ('u', update)):
        for name in names:
            privs.setdefault(name, {})[op] = admin_privs[name][op]

    machine.add_acl_to_role(role_name, checks, privs)
