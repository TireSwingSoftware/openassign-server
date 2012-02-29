
from django.db.models import Sum

from pr_services.authorizer.checks import check
from pr_services.exceptions import InvalidActeeTypeException

import facade


@check
def refund_does_not_exceed_payment(auth_token, actee, *args, **kwargs):
    """
    Returns true if the refund does not put the total amount of
    refunds for a particular payment over the value of the payment.

    @param actee      Instance of refund
    """
    if not isinstance(actee, facade.models.Refund):
        raise InvalidActeeTypeException()

    query = actee.payment.refunds.aggregate(total=Sum('amount'))
    return actee.amount <= actee.payment.amount - query['total']

#    total_refunds = 0
#    for r in actee.payment.refunds.values_list('amount', flat = True):
#        total_refunds += r
#    if actee.amount > actee.payment.amount - total_refunds:
#        return False
#    else:
#        return True

@check
def purchase_order_has_payments(auth_token, actee, *args, **kwargs):
    """
    Returns true if the purchase order being accessed has at least one payment.

    @param actee      Instance of a purchase_order
    """
    if not isinstance(actee, facade.models.PurchaseOrder):
        raise InvalidActeeTypeException()

    return actee.payments.count() > 0


@check
def purchase_order_has_no_payments(auth_token, actee, *args, **kwargs):
    """
    Returns true if the purchase order being accessed has no payments.

    @param actee      Instance of a purchase_order
    """
    if not isinstance(actee, facade.models.PurchaseOrder):
        raise InvalidActeeTypeException()

    return actee.payments.count() == 0
