from decorators import authz
from django.conf import settings

@authz
def setup(machine):
    methods = [
        {'name': 'assignment.actor_assigned_to_curriculum_enrollment'},
        {'name': 'assignment.actor_assigned_to_session'},
        {'name': 'assignment.actor_has_completed_assignment_prerequisites'},
        {'name': 'constraint.actor_is_acting_upon_themselves'},
        {'name': 'ownership.actor_owns_achievement_award'},
        {'name': 'ownership.actor_owns_achievement_award_for_achievement'},
        {'name': 'ownership.actor_owns_address'},
        {'name': 'ownership.actor_owns_assignment'},
        {'name': 'ownership.actor_owns_assignment_for_task'},
        {'name': 'ownership.actor_owns_assignment_attempt'},
        {'name': 'ownership.actor_owns_credential'},
        {'name': 'ownership.actor_owns_prmodel'},
        {'name': 'ownership.actor_owns_question_response'},
        {'name': 'assignment.assignment_attempt_meets_date_restrictions'},
        {'name': 'assignment.assignment_attempt_prerequisites_met'},
        {'name': 'constraint.populated_exam_session_is_finished'},
    ]
    if 'vod_aws' in settings.INSTALLED_APPS:
        methods.append({'name' : 'assignment_is_not_video'})

    crud = {
        'Achievement' : {
            'r': set(('description', 'name')),
        },
        'AchievementAward': {
            'r': set(('achievement', 'assignment', 'date', 'user')),
        },
        'Assignment': {
            'c': True,
            'r': set(('assignment_attempts', 'achievement_awards',
                      'date_completed', 'date_started', 'due_date',
                      'effective_date_assigned', 'prerequisites_met',
                      'status', 'task', 'task_content_type', 'user')),
        },
        'AssignmentAttempt': {
            'c': True,
            'r': set(('assignment', 'date_started', 'date_completed')),
        },
        'Credential': {
            'r': set(('authority', 'credential_type', 'date_assigned',
                      'date_expires', 'date_granted', 'date_started',
                      'serial_number', 'status', 'user')),
        },
        'CurriculumEnrollment': {
            'r': set(('curriculum_name', 'start', 'end')),
        },
        'Exam': {
            'r': set(('achievements', 'description', 'name', 'passing_score',
                      'title', 'type')),
        },
        'ExamSession': {
            'c': True,
            'r': set(('exam', 'score', 'passed', 'date_started',
                      'passing_score', 'number_correct', 'date_completed',
                      'response_questions')),
            'u': set(('date_completed',)),
        },
        'Response': {
            'c': True,
            'r': set(('exam_session', 'question', 'text', 'value', 'valid')),
        },
        'ScoSession': {
            'c': True,
            'r': set(('date_completed', 'date_started', 'sco')),
        },
        'Session': {
            'r': set(('start', 'end'))
        },
        'SessionUserRoleRequirement': {
            'r': set(('session', 'name', 'title', 'type', 'description'))
        },
        'Task': {
            'r': set(('name', 'title', 'type', 'description', 'achievements')),
        },
        'User': {
            # We allow users to create themselves
            'c': True,
            'r': set(('achievement_awards', 'achievements',
                      'alleged_organization', 'billing_address', 'biography',
                      'color_code', 'credentials',
                      'default_username_and_domain', 'email', 'email2',
                      'first_name', 'full_name', 'groups', 'last_name',
                      'middle_name', 'name_suffix', 'organizations',
                      'owned_userorgroles', 'phone', 'phone2', 'phone3',
                      'photo_url', 'preferred_venues',
                      'product_lines_instructor_for',
                      'product_lines_instructor_manager_for',
                      'product_lines_managed', 'roles',
                      'session_user_role_requirements', 'shipping_address',
                      'status', 'suppress_emails', 'title', 'url', 'username')),
            'u': set(('alleged_organization', 'billing_address', 'biography',
                      'color_code', 'email', 'email2', 'first_name',
                      'last_name', 'middle_name', 'name_suffix', 'phone',
                      'phone2', 'phone3', 'photo_url', 'preferred_venues',
                      'shipping_address', 'suppress_emails', 'title', 'url')),
        },
        'UserOrgRole': {
            'r': set(('owner', 'organization', 'organization_name', 'role',
                      'role_name', 'parent', 'children')),
        },
        'Venue': {
            'r': set(('region', 'address')),
        },
    }

    if 'file_tasks' in settings.INSTALLED_APPS:
        crud.update({
            'FileDownloadAttempt' : {
                'c' : True,
                'r' : set(('assignment', 'date_started', 'date_completed',
                           'file_download')),
            },
            'FileUploadAttempt' : {
                'c' : True,
                'r' : set(('assignment', 'date_started', 'date_completed',
                           'file_upload')),
            }
        })

    if 'vod_aws' in settings.INSTALLED_APPS:
        crud.update({
            'VideoSession' : {
                'c' : True,
                'r' : set(('assignment', 'date_started', 'date_completed')),
            }
        })

    machine.add_acl_to_role('Object Owner', methods, crud)
