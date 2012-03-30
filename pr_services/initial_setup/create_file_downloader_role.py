
from django.conf import settings

from decorators import authz

@authz
def setup(machine):
    if not 'file_tasks' in settings.INSTALLED_APPS:
        return

    methods = [
        {'name': 'ownership.actor_owns_assignment'},
        {'name': 'ownership.actor_owns_assignment_attempt'},
        {'name': 'ownership.actor_owns_assignment_for_task'},
    ]
    crud = {
        'Assignment' : {
            'c' : True,
            'r' : set(('assignment_attempts', 'date_completed', 'date_started',
                       'due_date', 'effective_date_assigned',
                       'prerequisites_met', 'status', 'task',
                       'task_content_type', 'user')),
        },
        'FileDownload' : {
            'r' : set(('description', 'file_size', 'name',
                       'prerequisite_tasks')),
        },
    }
    machine.add_acl_to_role('File Downloader', methods, crud)
