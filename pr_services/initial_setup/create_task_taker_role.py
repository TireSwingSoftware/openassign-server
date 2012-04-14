from decorators import authz

@authz
def setup(machine):
    methods = [
        {'name' : 'ownership.actor_owns_assignment'},
        {'name' : 'ownership.actor_owns_assignment_for_task'},
    ]
    crud = {
        'Assignment' : {
            'c' : True,
            'r' : set(('task', 'task_content_type', 'user', 'date_started',
                       'date_completed', 'due_date', 'prerequisites_met',
                       'effective_date_assigned', 'status',
                       'assignment_attempts')),
        },
        'Task' : {
            'r' : set(('description', 'name', 'prerequisite_achievements',
                       'prerequisite_tasks', 'title', 'type')),
        },
    }
    machine.add_acl_to_role('Task Taker', methods, crud)
