import settings

from decorators import authz

@authz
def setup(machine):
    if not 'file_tasks' in settings.INSTALLED_APPS:
        return

    methods = [
        {'name' : 'actor_owns_assignment', 'params' : {}},
        {'name' : 'actor_owns_assignment_attempt', 'params' : {}},
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
        'FileDownload' : {
            'c' : False,
            'r' : set(('author', 'create_timestamp', 'prerequisite_tasks',
                       'name', 'description', 'file_size')),
            'u' : set(),
            'd' : False,
        },
    }
    machine.add_acl_to_role('File Downloader', methods, crud)
