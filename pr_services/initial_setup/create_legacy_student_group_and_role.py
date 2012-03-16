import facade
from decorators import authz

@authz
def setup(machine):
    group, created = facade.models.Group.objects.get_or_create(name='Students')

    methods_1 = [
        {'name' : 'membership.actor_member_of_group', 'params' : {'group_id' : group.id}},
    ]
    crud_1 = {
        'Sco' : {
            'r' : set(('course', 'description', 'name',
                   'prerequisite_tasks', 'type',
                   'version_id', 'version_label')),
        },
        'Task' : {
            'r' : set(('description', 'name', 'prerequisite_achievements',
                       'prerequisite_tasks', 'type', 'version_id',
                       'version_label')),
        },
    }
    machine.add_acl_to_role('Student', methods_1, crud_1)

    methods_2 = [
        {'name' : 'assignment.actor_has_completed_task_prerequisites', 'params' : {}},
    ]
    crud_2 = {
        'Sco' : {
            'r' : set(('url', )),
        },
    }
    machine.add_acl_to_role('Student', methods_2, crud_2)
