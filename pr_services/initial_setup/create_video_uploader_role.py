
import settings

from decorators import authz

@authz
def setup(machine):
    if not 'vod_aws' in settings.INSTALLED_APPS:
        return

    methods = [
        {'name' : 'membership.actor_is_member_of_any_organization'},
        # the below 2 are here to prevent everyone from seeing Videos in the
        # system unless they absolutely have to in order for uploads to work
        {'name' : 'ownership.actor_owns_prmodel'},
        {'name' : 'constraint.actees_attribute_is_set_to',
            'params' : {
                'actee_model_name' : 'Video',
                'attribute_name' : 'deleted',
                'attribute_value' : False
            }
        },
    ]
    crud = {
        'Category' : {
            'c' : False,
            'r' : set(('name', 'locked')),
            'u' : set(),
            'd' : False,
        },
        'Video' : {
            'c' : True,
            'r' : set(),
            'u' : set(),
            'd' : False,
        },
    }
    machine.add_acl_to_role('Video Uploader', methods, crud)
