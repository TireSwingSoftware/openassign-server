import facade
from pr_services.utils import Utils
from decorators import authz
from admin_privs import admin_privs

@authz
def setup(machine):
    group, created = facade.models.Group.objects.get_or_create(
        name="Super Administrators")

    if not machine.options['authz_only']:
        if machine.options.has_key('default_admin_password'):
            password = machine.options['default_admin_password']
        else:
            password = 'admin'
        salt = machine.user_manager._generate_password_salt()
        password_hash = Utils._hash(password + salt, 'SHA-512')

        user = facade.models.User.objects.create(first_name="admin",
            last_name="user", status='active', email='admin@admin.org')
        user.groups.add(group) # no need to save(), it's a ManyToManyField

        local_domain = facade.models.Domain.objects.get(name='local')
        da = facade.models.DomainAffiliation.objects.create(user=user,
            username='admin', domain=local_domain, default=True,
            password_hash=password_hash, password_salt=salt)

    methods = [
        {'name' : 'membership.actor_member_of_group', 'params' : {'group_id' : group.id}},
        {'name' : 'payment.refund_does_not_exceed_payment', 'params' : {}},
    ]
    arb_perm_list = [
        'access_db_settings',
        'change_password_of_other_users',
        'check_usernames',
        'exceed_enrollment_capacity',
        'export_exam_to_xml',
        'email_task_assignees',
        'import_exam_from_xml',
        'logging',
        'read_reports',
        'regenerate_payment_confirmations',
        'resend_payment_confirmations',
        'send_email',
        'upload_scorm_course',
    ]

    machine.add_acl_to_role('Admin', methods, admin_privs, arb_perm_list)

    if not machine.options['authz_only']:
        # we need to reload ACLs that were just modified before using them to login
        facade.subsystems.Authorizer.flush()

        # we log in here so that other setup methods can have an admin_token
        token_str = machine.user_manager.login('admin', password)['auth_token']
        machine.options['admin_token'] = Utils.get_auth_token_object(token_str)
