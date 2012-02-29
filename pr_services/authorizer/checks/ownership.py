
from django.core.exceptions import ObjectDoesNotExist

from pr_services import pr_models
from pr_services.authorizer.checks import check
from pr_services.exceptions import InvalidActeeTypeException

import facade

@check
def actor_owns_session_user_role_requirement(auth_token, actee, *args, **kwargs):
    """
    Returns True if the session associated with the session_user_role_requirement is owned
    by the actor
    """
    if not isinstance(actee, facade.models.SessionUserRoleRequirement):
        raise InvalidActeeTypeException()

    try:
        return actor_owns_session(auth_token, actee.session)
    except (ObjectDoesNotExist, AttributeError):
        return False


@check
def actor_owns_payment(auth_token, actee, *args, **kwargs):
    """
    Returns true if the actor owns the payment.

    @param actee      Instance of a purchase_order
    """
    if not isinstance(actee, facade.models.Payment):
        raise InvalidActeeTypeException()

    try:
        return auth_token.user_id == actee.purchase_order.user_id
    except (ObjectDoesNotExist, AttributeError):
        return False


@check
def actor_owns_purchase_order(auth_token, actee, *args, **kwargs):
    """
    Returns true if the actor owns the purchase order being accessed.

    @param actee      Instance of a purchase_order
    """
    if not isinstance(actee, facade.models.PurchaseOrder):
        raise InvalidActeeTypeException()

    try:
        return auth_token.user_id == actee.user_id
    except (ObjectDoesNotExist, AttributeError):
        return False


@check
def actor_owns_question_response(auth_token, actee, *args, **kwargs):
    """
    Returns True iff the QuestionResponse is for an ExamSession owned by the
    actor.
    """
    if not isinstance(actee, facade.models.Response):
        raise InvalidActeeTypeException()

    try:
        return actor_owns_assignment(auth_token, actee.exam_session)
    except (ObjectDoesNotExist, AttributeError):
        return False


@check
def actor_owns_assignment_for_task(auth_token, actee, *args, **kwargs):
    "Returns True iff actor owns an assignment for the given task."
    if not isinstance(actee, facade.models.Task):
        raise InvalidActeeTypeException()

    return facade.models.Assignment.objects.filter(task__id=actee.id,
            user__id=auth_token.user_id).exists()


@check
def actor_owns_training_unit_authorization(auth_token, actee, *args, **kwargs):
    """
    Returns true if the actor owns the purchase order being accessed.

    @param actee      Instance of a purchase_order
    """
    if not isinstance(actee, facade.models.TrainingUnitAuthorization):
        raise InvalidActeeTypeException()

    try:
        return auth_token.user_id == actee.user_id
    except (ObjectDoesNotExist, AttributeError):
        return False


@check
def actor_owns_prmodel(auth_token, actee, *args, **kwargs):
    """
    Returns True if the actor is the same User object as is listed in the
    PRModel's owner field, or if the PRModel has None in its owner field.
    """
    if not isinstance(actee, pr_models.OwnedPRModel):
        raise InvalidActeeTypeException()

    try:
        return actee.owner is None or auth_token.user_id == actee.owner.id
    except (ObjectDoesNotExist, AttributeError):
        return False


@check
def actor_owns_address(auth_token, actee, *args, **kwargs):
    """
    Returns True if the address object is either the user's
    shipping or billing address, False otherwise.

    @param actee  The address object in question
    """
    if not isinstance(actee, facade.models.Address):
        raise InvalidActeeTypeException()

    billing = auth_token.user.billing_address
    shipping = auth_token.user.shipping_address
    return ((billing and billing.id == actee.id) or
            (shipping and shipping.id == actee.id))


@check
def actor_owns_achievement_award_for_achievement(auth_token, actee, *args, **kwargs):
    """
    Returns True iff the actor is the owner of an AchievementAward for the
    Achievement.
    """
    if not isinstance(actee, facade.models.Achievement):
        raise InvalidActeeTypeException()

    try:
        return actee.achievement_awards.filter(user__id=auth_token.user_id).exists()
    except (ObjectDoesNotExist, AttributeError):
        return False


@check
def actor_owns_achievement_award(auth_token, actee, *args, **kwargs):
    "Returns True iff the actor is the owner of the AchievementAward"
    if not isinstance(actee, facade.models.AchievementAward):
        raise InvalidActeeTypeException()

    try:
        return auth_token.user_id == actee.user.id
    except (ObjectDoesNotExist, AttributeError):
        return False


@check
def actor_owns_assignment(auth_token, actee, *args, **kwargs):
    """Returns True iff the actor is the owner of the Assignment."""
    if not isinstance(actee, facade.models.Assignment):
        raise InvalidActeeTypeException()

    try:
        return auth_token.user_id == actee.user.id
    except (ObjectDoesNotExist, AttributeError):
        return False


@check
def actor_owns_assignment_or_is_guest(actee, auth_token=None, *args, **kwargs):
    """
    Returns True if the actor is the owner of the Assignment, or if the
    actor is a guest and the Assignment doesn't have a user @check
defined.
    """
    if not isinstance(actee, facade.models.Assignment):
        raise InvalidActeeTypeException()

    try:
        if not (actee.user or isinstance(auth_token, facade.models.AuthToken)):
            return True
        else:
            return actor_owns_assignment(auth_token, actee)
    except (ObjectDoesNotExist, AttributeError):
        return False


@check
def actor_owns_assignment_attempt(auth_token, actee, *args, **kwargs):
    """
    Returns True iff the actor is the owner of the Assignment
    """
    if not isinstance(actee, facade.models.AssignmentAttempt):
        raise InvalidActeeTypeException()

    return actor_owns_assignment(auth_token, actee.assignment)


@check
def actor_owns_credential(auth_token, actee, *args, **kwargs):
    """
    Returns True iff the actor is the owner of the Credential
    """
    if not isinstance(actee, facade.models.Credential):
        raise InvalidActeeTypeException()

    try:
        return auth_token.user_id == actee.user.id
    except (ObjectDoesNotExist, AttributeError):
        return False


@check
def actor_owns_event(auth_token, actee, *args, **kwargs):
    """
    Returns true if the actor is the owner of an event.
    """
    if not isinstance(actee, facade.models.Event):
        raise InvalidActeeTypeException()

    try:
        return auth_token.user_id == actee.owner.id
    except (ObjectDoesNotExist, AttributeError):
        return False


@check
def actor_owns_session(auth_token, actee, *args, **kwargs):
    """
    Returns True if the actor owns the event associated with this session.
    """
    if not isinstance(actee, facade.models.Session):
        raise InvalidActeeTypeException()

    try:
        return actor_owns_event(auth_token, actee.event)
    except (ObjectDoesNotExist, AttributeError):
        return False
