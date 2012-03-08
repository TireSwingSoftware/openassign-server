from decorators import authz

@authz
def setup(machine):
    methods = [
        {'name': 'assignment.actor_assigned_to_event_session'},
        {'name': 'assignment.actor_assigned_to_session'},
        {'name': 'ownership.actor_owns_assignment'},
        {'name': 'ownership.actor_owns_assignment_attempt'},
        {'name': 'ownership.actor_owns_assignment_for_task'},

        # if the user is an instructor make sure she can only send
        # email to task assignees if the task is a surr
        {'name': 'method.instructor_can_email_task_assignees',
            'params': {
                'restrict': 'AssignmentManager.email_task_assignees'
            }
        }
    ]
    crud = {
        'Assignment' : {
            'c' : True,
            'r' : set(('task', 'task_content_type', 'user', 'date_started',
                       'date_completed', 'due_date', 'prerequisites_met',
                       'effective_date_assigned', 'status',
                       'assignment_attempts')),
            'u' : set(),
            'd' : False,
        },
        'Event': {
            'c': False,
            'r': set(('name', 'region', 'title', 'description', 'start', 'end',
                      'venue', 'url', 'organization')),
            'u': set(),
            'd': False,
        },
        'Session' : {
            'c' : False,
            'r' : set(('end', 'event', 'room', 'start', 'status')),
            'u' : set(),
            'd' : False,
        },
        'SessionUserRoleRequirement' : {
            'c' : False,
            'r' : set(('description', 'name', 'prerequisite_tasks',
                       'session', 'title', 'type')),
            'u' : set(),
            'd' : False,
        },
        ##
        # Method Privileges
        'AssignmentManager': {
            'methods': set(('email_task_assignees',))
        }
    }
    machine.add_acl_to_role('Session Participant', methods, crud)
