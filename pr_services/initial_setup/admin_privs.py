
import facade
import settings

from pr_services.object_manager import ObjectManager

__all__ = ['admin_privs']

def _make_admin_privs():
    # use the following imports to initialize the facade managers
    if 'file_tasks' in settings.INSTALLED_APPS:
        import file_tasks
    if 'vod_aws' in settings.INSTALLED_APPS:
        import vod_aws
    if 'forum' in settings.INSTALLED_APPS:
        import forum

    admin_privs = {}
    manager_classes = map(lambda n: getattr(facade.managers, n), facade.managers)
    for manager_class in manager_classes:
        manager = manager_class()
        if isinstance(manager, ObjectManager):
            crud = {
                'c': True,
                'r': set(manager_class.GETTERS),
                'u': set(manager_class.SETTERS),
                'd': True
            }
            model_name = manager.my_django_model._meta.object_name
            admin_privs[model_name] = crud

    admin_privs.update({
        # objects not explicitly owned by a manager
        'CSVData': {
            'c': True,
            'r': set(),
            'u': set(),
            'd': True
        },
        'CurriculumEnrollmentUserAssociation': {
            'c': True,
            'r': set(),
            'u': set(),
            'd': True
        },
        'TaskBundleTaskAssociation': {
            'c': True,
            'r': set(['continue_automatically', 'presentation_order', 'task',
                      'task_bundle']),
            'u': set(['continue_automatically', 'presentation_order', 'task',
                      'task_bundle']),
            'd': True
        },

        # special case limitations
        'Payment': {
            'c' : True,
            'r' : set(('refunds', 'card_type', 'exp_date', 'amount',
                       'first_name', 'last_name', 'city', 'state', 'zip',
                       'country', 'sales_tax', 'transaction_id',
                       'purchase_order', 'invoice_number', 'notes',
                       'result_message', 'date')),
            'u' : set(),
            'd' : False,
            },
        'Refund': {
            'c' : True,
            'r' : set(),
            'u' : set(),
            'd' : False,
            },

        ##
        # Method Privileges
        'AssignmentManager': {
            'methods': set(('email_task_assignees', ))
        }
    })
    return admin_privs

admin_privs = _make_admin_privs()
