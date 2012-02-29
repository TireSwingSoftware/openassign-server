
from django.core.exceptions import ObjectDoesNotExist

from pr_services.authorizer.checks import check
from pr_services.exceptions import InvalidActeeTypeException

import facade

@check
def actor_is_product_line_manager_of_session(auth_token, actee, *args, **kwargs):
    """
    Returns true if the actor is a product line manager for the given session.

    @param actee      Instance of session
    """
    if not isinstance(actee, facade.models.Session):
        raise InvalidActeeTypeException()

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


@check
def actor_is_product_line_manager_of_session_template(auth_token, actee,
        *args, **kwargs):
    """
    Returns true if the actor is a product line manager for the given session_template

    @param actee      Instance of session_template
    """
    if not isinstance(actee, facade.models.SessionTemplate):
        raise InvalidActeeTypeException()

    try:
        uid = auth_token.user_id
        return actee.product_line.managers.filter(id=uid).exists()
    except (ObjectDoesNotExist, AttributeError):
        return False


@check
def actor_is_product_line_manager_of_product_line(auth_token, actee, *args, **kwargs):
    """
    Returns true if the actor is a product line manager for the given product line.

    @param actee      Instance of product_line
    """
    if not isinstance(actee, facade.models.ProductLine):
        raise InvalidActeeTypeException()

    return actee.managers.filter(id=auth_token.user_id).exists()


@check
def actor_is_product_line_manager_of_user(auth_token, actee, *args, **kwargs):
    """
    Returns True if the actor is the product line manager for a
    product line in which the actee is an instructor.

    @param actee      A user object that we are evaluation authorization for
    """
    if not isinstance(actee, facade.models.User):
        raise InvalidActeeTypeException()

    return facade.models.ProductLine.objects.filter(
        instructors__id=actee.id,
        managers__id=auth_token.user_id).exists()

#    actee_product_lines_instructor_in = set(
#        facade.models.ProductLine.objects.filter(
#            instructors__id__exact=actee.id).values_list('id', flat=True))
#    actor_product_lines_plm_for = set(
#        facade.models.ProductLine.objects.filter(
#            managers__id__exact=auth_token.user_id
#        ).values_list('id', flat=True))
#    if actor_product_lines_plm_for & actee_product_lines_instructor_in:
#        return True
#    return False




