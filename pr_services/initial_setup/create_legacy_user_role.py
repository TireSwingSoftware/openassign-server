from decorators import authz

@authz
def setup(machine):
    methods = [
        {'name' : 'auth.actor_is_authenticated'},
        {'name' : 'ownership.actor_owns_payment'},
        {'name' : 'membership.actor_related_to_domain_affiliation'},
        {'name' : 'ownership.actor_owns_training_unit_authorization'},
    ]
    crud = {
        'Answer' : {
            'c' : False,
            'r' : set(('label',)),
            'u' : set(),
            'd' : False,
        },
        'Domain' : {
            'c' : False,
            'r' : set(('name',)),
            'u' : set(),
            'd' : False,
        },
        'DomainAffiliation' : {
            'c' : True,
            'r' : set(('default', 'domain', 'may_log_me_in', 'user', 'username')),
            'u' : set(('default', 'domain', 'may_log_me_in', 'username')),
            'd' : False,
        },
        'SessionTemplate' : {
            'c' : False,
            'r' : set(('active', 'version', 'audience', 'description', 'sequence',
                      'duration', 'sessions', 'fullname', 'modality', 'product_line', 'shortname')),
            'u' : set(),
            'd' : False,
        },
        'Group' : {
            'c' : False,
            'r' : set(('managers', 'name', 'users')),
            'u' : set(),
            'd' : False,
        },
        'Organization' : {
            'c': False,
            'r': set(('name', 'parent', 'children', 'ancestors', 'descendants')),
            'u': set(),
            'd': False,
        },
        'OrgRole' : {
            'c' : False,
            'r' : set(('name',)),
            'u' : set(),
            'd' : False,
        },
        'Payment' : {
            'c' : True,
            'r' : set(('refunds', 'card_type', 'exp_date', 'amount',
                      'first_name', 'last_name', 'city', 'state', 'zip', 'country',
                      'sales_tax', 'transaction_id', 'invoice_number', 'result_message',
                      'purchase_order', 'date')),
            'u' : set(),
            'd' : False,
        },
        'PurchaseOrder' : {
            'c' : True,
            'r' : set(),
            'u' : set(),
            'd' : False,
        },
        'ProductClaim' : {
            'c' : True,
            'r' : set(('product', 'purchase_order', 'quantity')),
            'u' : set(('quantity',)),
            'd' : True,
        },
        'SessionUserRoleRequirement' : {
            'c' : False,
            'r' : set(),
            'u' : set(),
            'd' : False,
        },
        'TrainingUnitAuthorization' : {
            'c' : False,
            'r' : set(('training_unit_account', 'user', 'start',
                      'end', 'max_value', 'used_value')),
            'u' : set(),
            'd' : False,
        },
        'User' : {
            'c' : False,
            'r' : set(('default_username_and_domain',)),
            'u' : set(),
            'd' : False,
        },
        'Venue' : {
            'c' : False,
            'r' : set(('contact', 'region', 'address', 'phone', 'name')),
            'u' : set(),
            'd' : False,
        },
    }
    machine.add_acl_to_role('User', methods, crud)
