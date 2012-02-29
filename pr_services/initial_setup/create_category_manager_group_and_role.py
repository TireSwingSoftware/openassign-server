import facade
import settings

from decorators import authz

@authz
def setup(machine):
    if not 'vod_aws' in settings.INSTALLED_APPS:
        return

    group, created = facade.models.Group.objects.get_or_create(
        name='Category Managers')

    methods = [
        {'name' : 'membership.actor_member_of_group', 'params' : {'group_id' : group.id}},
        {'name' : 'membership.actor_is_manager_of_actee_related_category', 'params' : {}},
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
            'r' : set(('authorized_groups', 'locked', 'managers', 'name',
                'videos', 'approved_videos')),
            'u' : set(('authorized_groups',)),
            'd' : False,
        },
        'EncodedVideo' : {
            'c' : False,
            'r' : set(('video', 'bitrate', 'url')),
            'u' : set(),
            'd' : False,
        },
        'Group' : {
            'c' : False,
            'r' : set(('name',)),
            'u' : set(),
            'd' : False,
        },
        'User' : {
            'c' : False,
            'r' : set(('default_username_and_domain', 'username', 'email',
                       'first_name', 'last_name')),
            'u' : set(),
            'd' : False,
        },
        'Video' : {
            'c' : False,
            'r' : set(('approved_categories', 'author', 'categories',
                       'category_relationships', 'create_timestamp',
                       'description', 'encoded_videos', 'length', 'live',
                       'name', 'num_views', 'photo_url', 'prerequisite_tasks',
                       'public', 'src_file_size', 'status', 'tags')),
            'u' : set(('author', 'categories', 'description', 'length', 'live',
                       'name', 'photo_url', 'public', 'tags')),
            'd' : False,
        },
        'VideoCategory' : {
            'c' : True,
            'r' : set(('status', 'category', 'category_name', 'video')),
            'u' : set(('status',)),
            'd' : False,
        },
        'VideoSession' : {
            'c' : False,
            'r' : set(('assignment', 'date_started', 'date_completed', 'user',
                       'video')),
            'u' : set(),
            'd' : False,
        },
    }
    machine.add_acl_to_role('Category Manager', methods, crud)
    methods2 = [
        {'name' : 'membership.actor_member_of_group', 'params' : {'group_id' : group.id}},
        {'name' : 'constraint.actees_foreign_key_object_has_attribute_set_to',
            'params' : {
                'actee_model_name' : 'VideoCategory',
                'attribute_name' : 'video',
                'foreign_object_attribute_name' : 'deleted',
                'foreign_object_attribute_value' : False,
            }
        },
    ]
    crud2 = {
        'VideoCategory' : {
            'c' : True,
            'r' : set(('status', 'category', 'category_name', 'video')),
            'u' : set(),
            'd' : False,
        },
    }
    machine.add_acl_to_role('Category Manager', methods2, crud2)
