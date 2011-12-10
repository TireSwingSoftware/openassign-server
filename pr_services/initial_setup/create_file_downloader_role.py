from decorators import authz

@authz
def setup(machine):
    methods = [
        {'name' : 'actor_owns_assignment', 'params' : {}},
        {'name' : 'actor_owns_assignment_attempt', 'params' : {}},
        {'name' : 'actor_owns_assignment_for_task', 'params' : {}},
    ]
    crud = {
        'Assignment' : {
            'c' : True,
            'r' : ['task', 'task_content_type', 'user', 'date_started',
                   'date_completed', 'due_date', 'prerequisites_met',
                   'effective_date_assigned', 'status', 'assignment_attempts'],
            'u' : [],
            'd' : False,
        },
        'FileDownload' : {
            'c' : False,
            'r' : ['author', 'create_timestamp', 'prerequisite_tasks', 'name',
                   'description', 'file_size'],
            'u' : [],
            'd' : False,
        },
    }
    machine.add_acl_to_role('File Downloader', methods, crud)
