from decorators import authz

@authz
def setup(machine):
    methods = [
        {'name' : 'actor_owns_assignment', 'params' : {}},
        {'name' : 'actor_owns_assignment_attempt', 'params' : {}},
        {'name' : 'actor_owns_assignment_for_task', 'params' : {}},
        {'name' : 'actor_assigned_to_session', 'params' : {}},
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
        'Session' : {
            'c' : False,
            'r' : set(('end', 'event', 'room', 'start', 'status')),
            'u' : set(),
            'd' : False,
        },
        'SessionUserRoleRequirement' : {
            'c' : False,
            'r' : set(('author', 'create_timestamp', 'prerequisite_tasks',
                       'name', 'session', 'title', 'type', 'description')),
            'u' : set(),
            'd' : False,
        },
    }
    machine.add_acl_to_role('Session Participant', methods, crud)
