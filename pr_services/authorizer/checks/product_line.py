
from django.core.exceptions import ObjectDoesNotExist

from pr_services.authorizer.checks import check
from pr_services.exceptions import InvalidActeeTypeException

import facade

facade.import_models(locals())


@check(Session)
def actor_is_product_line_manager_of_session(auth_token, actee, *args, **kwargs):
    """
    Returns true if the actor is a product line manager for the given session.

    @param actee      Instance of session
    """
    uid = auth_token.user_id
    try:
        return actee.product_line.managers.filter(id=uid).exists()
    except (ObjectDoesNotExist, AttributeError):
        pass
    # Now see if this session's session_template has the actor as a PLM
    try:
        return actee.session_template.product_line.managers.filter(id=uid).exists()
    except (ObjectDoesNotExist, AttributeError):
        return False


@check(SessionTemplate)
def actor_is_product_line_manager_of_session_template(auth_token, actee,
        *args, **kwargs):
    """
    Returns true if the actor is a product line manager for the given session_template

    @param actee      Instance of session_template
    """
    try:
        uid = auth_token.user_id
        return actee.product_line.managers.filter(id=uid).exists()
    except (ObjectDoesNotExist, AttributeError):
        return False


@check(ProductLine)
def actor_is_product_line_manager_of_product_line(auth_token, actee, *args, **kwargs):
    """
    Returns true if the actor is a product line manager for the given product line.

    @param actee      Instance of product_line
    """
    return actee.managers.filter(id=auth_token.user_id).exists()


@check(User)
def actor_is_product_line_manager_of_user(auth_token, actee, *args, **kwargs):
    """
    Returns True if the actor is the product line manager for a
    product line in which the actee is an instructor.

    @param actee      A user object that we are evaluation authorization for
    """
    return facade.models.ProductLine.objects.filter(
        instructors__id=actee.id,
        managers__id=auth_token.user_id).exists()
