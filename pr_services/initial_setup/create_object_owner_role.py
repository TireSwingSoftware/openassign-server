from decorators import authz
from django.conf import settings

@authz
def setup(machine):
    methods = [
        {'name': 'actor_assigned_to_curriculum_enrollment'},
        {'name': 'actor_has_completed_assignment_prerequisites'},
        {'name': 'actor_is_acting_upon_themselves'},
        {'name': 'actor_owns_achievement_award'},
        {'name': 'actor_owns_achievement_award_for_achievement'},
        {'name': 'actor_owns_address'},
        {'name': 'actor_owns_assignment'},
        {'name': 'actor_owns_assignment_attempt'},
        {'name': 'actor_owns_credential'},
        {'name': 'actor_owns_prmodel'},
        {'name': 'actor_owns_question_response'},
        {'name': 'assignment_attempt_meets_date_restrictions'},
        {'name': 'assignment_attempt_prerequisites_met'},
        {'name': 'populated_exam_session_is_finished'},
    ]
    if 'vod_aws' in settings.INSTALLED_APPS:
        methods.append({'name' : 'assignment_is_not_video', 'params' : {}})

    crud = {
        'Achievement' : {
            'c' : False,
            'r' : set(('description', 'name')),
            'u' : set(),
            'd' : False,
        },
        'AchievementAward' : {
            'c' : False,
            'r' : set(('achievement', 'assignment', 'date', 'user')),
            'u' : set(),
            'd' : False,
        },
        'Assignment' : {
            'c' : True,
            'r' : set(('assignment_attempts', 'achievement_awards',
                       'date_completed', 'date_started', 'due_date',
                       'effective_date_assigned', 'prerequisites_met',
                       'status', 'task', 'task_content_type', 'user')),
            'u' : set(),
            'd' : False,
        },
        'AssignmentAttempt' : {
            'c' : True,
            'r' : set(('assignment', 'date_started', 'date_completed')),
            'u' : set(),
            'd' : False,
        },
        'Credential' : {
            'c' : False,
            'r' : set(('authority', 'credential_type', 'date_assigned',
                   'date_expires', 'date_granted', 'date_started',
                   'serial_number', 'status', 'user')),
            'u' : set(),
            'd' : False,
        },
        'CurriculumEnrollment' : {
            'c' : False,
            'r' : set(('curriculum_name', 'start', 'end')),
            'u' : set(),
            'd' : False,
        },
        'Exam': {
            'r': set(('achievements', 'description', 'name', 'passing_score',
                      'title', 'type')),
        },
        'ExamSession' : {
            'c' : True,
            'r' : set(('id', 'exam', 'score', 'passed', 'date_started',
                   'passing_score', 'number_correct', 'date_completed',
                   'response_questions')),
            'u' : set(('date_completed',)),
            'd' : False,
        },
        'FileDownloadAttempt' : {
            'c' : True,
            'r' : set(('assignment', 'date_started', 'date_completed',
                'file_download')),
            'u' : set(),
            'd' : False,
        },
        'FileUploadAttempt' : {
            'c' : True,
            'r' : set(('assignment', 'date_started', 'date_completed',
                      'file_upload')),
            'u' : set(),
            'd' : False,
        },
        'Response' : {
            'c' : True,
            'r' : set(('exam_session', 'question', 'text', 'value', 'valid')),
            'u' : set(),
            'd' : False,
        },
        'ScoSession' : {
            'c' : True,
            'r' : set(('date_completed', 'date_started', 'sco')),
            'u' : set(),
            'd' : False,
        },
        'User' : {
            # We allow users to create themselves
            'c' : True,
            'r' : set(('achievements', 'achievement_awards', 'credentials',
                   'session_user_role_requirements', 'product_lines_managed',
                   'product_lines_instructor_manager_for', 'product_lines_instructor_for',
                   'groups', 'roles', 'photo_url', 'url', 'username',
                   'title', 'first_name', 'middle_name', 'last_name', 'name_suffix',
                   'full_name',
                   'phone', 'phone2', 'phone3', 'email', 'email2',
                   'status', 'color_code', 'biography',
                   'shipping_address', 'billing_address', 'organizations', 'owned_userorgroles',
                   'preferred_venues',
                   'suppress_emails', 'default_username_and_domain',
                   'alleged_organization')),
            'u' : set(('photo_url', 'url',
                   'title', 'first_name', 'middle_name', 'last_name', 'name_suffix',
                   'phone', 'phone2', 'phone3', 'email', 'email2', 'color_code',
                   'biography', 'shipping_address', 'billing_address',
                   'preferred_venues', 'suppress_emails',
                   'alleged_organization')),
            'd' : False,
        },
        'UserOrgRole' : {
            'c' : False,
            'r' : set(('owner', 'organization', 'organization_name', 'role',
                'role_name', 'parent', 'children')),
            'u' : set(),
            'd' : False,
        },
        'Venue' : {
            'c' : False,
            'r' : set(('region', 'address')),
            'u' : set(),
            'd' : False,
        },
        'VideoSession' : {
            'c' : True,
            'r' : set(('assignment', 'date_started', 'date_completed')),
            'u' : set(),
            'd' : False,
        },
    }
    machine.add_acl_to_role('Object Owner', methods, crud)
