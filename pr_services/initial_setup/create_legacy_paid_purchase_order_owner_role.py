from decorators import authz

@authz
def setup(machine):
    methods = [
        {'name' : 'actor_owns_purchase_order', 'params' : {}},
        {'name' : 'purchase_order_has_payments', 'params' : {}},
    ]
    crud = {
        'PurchaseOrder' : {
            'c' : False,
            'r' : set(('training_units_purchased', 'training_units_price',
                       'products', 'product_offers', 'product_discounts',
                       'expiration', 'organization', 'is_paid', 'payments')),
            'u' : set(),
            'd' : False,
        },
    }
    machine.add_acl_to_role('Owner of purchase order with payments', methods, crud)
