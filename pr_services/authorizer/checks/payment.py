
from django.db.models import Sum

from pr_services.authorizer.checks import check
from pr_services.exceptions import InvalidActeeTypeException

import facade

facade.import_models(locals())

@check(Refund)
def refund_does_not_exceed_payment(auth_token, actee, *args, **kwargs):
    """
    Returns true if the refund does not put the total amount of
    refunds for a particular payment over the value of the payment.

    @param actee      Instance of refund
    """
    query = actee.payment.refunds.aggregate(total=Sum('amount'))
    return actee.amount <= actee.payment.amount - query['total']


@check(PurchaseOrder)
def purchase_order_has_payments(auth_token, actee, *args, **kwargs):
    """
    Returns true if the purchase order being accessed has at least one payment.

    @param actee      Instance of a purchase_order
    """
    return actee.payments.count() > 0


@check(PurchaseOrder)
def purchase_order_has_no_payments(auth_token, actee, *args, **kwargs):
    """
    Returns true if the purchase order being accessed has no payments.

    @param actee      Instance of a purchase_order
    """
    return actee.payments.count() == 0
