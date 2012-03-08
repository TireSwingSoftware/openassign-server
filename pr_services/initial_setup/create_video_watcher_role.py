
import settings

from decorators import authz

@authz
def setup(machine):
    if not 'vod_aws' in settings.INSTALLED_APPS:
        return

    methods = [
        {'name' : 'membership.actor_is_member_of_actee_related_category_authorized_groups'},
        {'name' : 'ownership.actor_owns_assignment'}
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
        'Category' : {
            'c' : False,
            'r' : set(('name', 'locked', 'approved_videos')),
            'u' : set(),
            'd' : False,
        },
        'EncodedVideo' : {
            'c' : False,
            'r' : set(('video', 'bitrate', 'url')),
            'u' : set(),
            'd' : False,
        },
        'Video' : {
            'c' : False,
            'r' : set(('approved_categories', 'author', 'create_timestamp',
                       'description', 'encoded_videos', 'length', 'live',
                       'name', 'num_views', 'photo_url', 'prerequisite_tasks',
                       'public', 'src_file_size', 'tags')),
            'u' : set(),
            'd' : False,
        },
    }
    machine.add_acl_to_role('Video Watcher', methods, crud)
