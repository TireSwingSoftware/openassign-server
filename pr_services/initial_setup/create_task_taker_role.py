from decorators import authz

@authz
def setup(machine):
    methods = [
        {'name' : 'actor_owns_assignment', 'params' : {}},
        {'name' : 'actor_owns_assignment_for_task', 'params' : {}},
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
        'Task' : {
            'c' : False,
            'r' : set(('create_timestamp', 'prerequisite_tasks',
                       'name', 'description', 'title', 'type')),
            'u' : set(),
            'd' : False,
        },
    }
    machine.add_acl_to_role('Task Taker', methods, crud)
