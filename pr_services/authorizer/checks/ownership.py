
from django.core.exceptions import ObjectDoesNotExist

from pr_services import pr_models
from pr_services.authorizer.checks import check
from pr_services.exceptions import InvalidActeeTypeException

import facade

facade.import_models(locals())

@check(SessionUserRoleRequirement)
def actor_owns_session_user_role_requirement(auth_token, actee, *args, **kwargs):
    """
    Returns True if the session associated with the session_user_role_requirement is owned
    by the actor
    """
    try:
        return actor_owns_session(auth_token, actee.session)
    except (ObjectDoesNotExist, AttributeError):
        return False


@check(Payment)
def actor_owns_payment(auth_token, actee, *args, **kwargs):
    """
    Returns true if the actor owns the payment.

    @param actee      Instance of a purchase_order
    """
    try:
        return auth_token.user_id == actee.purchase_order.user_id
    except (ObjectDoesNotExist, AttributeError):
        return False


@check(PurchaseOrder)
def actor_owns_purchase_order(auth_token, actee, *args, **kwargs):
    """
    Returns true if the actor owns the purchase order being accessed.

    @param actee      Instance of a purchase_order
    """
    try:
        return auth_token.user_id == actee.user_id
    except (ObjectDoesNotExist, AttributeError):
        return False


@check(Response)
def actor_owns_question_response(auth_token, actee, *args, **kwargs):
    """
    Returns True iff the QuestionResponse is for an ExamSession owned by the
    actor.
    """
    try:
        return actor_owns_assignment(auth_token, actee.exam_session)
    except (ObjectDoesNotExist, AttributeError):
        return False


@check(Task)
def actor_owns_assignment_for_task(auth_token, actee, *args, **kwargs):
    "Returns True iff actor owns an assignment for the given task."
    return facade.models.Assignment.objects.filter(task__id=actee.id,
            user__id=auth_token.user_id).exists()


@check(TrainingUnitAuthorization)
def actor_owns_training_unit_authorization(auth_token, actee, *args, **kwargs):
    """
    Returns true if the actor owns the purchase order being accessed.

    @param actee      Instance of a purchase_order
    """
    try:
        return auth_token.user_id == actee.user_id
    except (ObjectDoesNotExist, AttributeError):
        return False


@check(pr_models.OwnedPRModel)
def actor_owns_prmodel(auth_token, actee, *args, **kwargs):
    """
    Returns True if the actor is the same User object as is listed in the
    PRModel's owner field, or if the PRModel has None in its owner field.
    """
    try:
        return actee.owner is None or auth_token.user_id == actee.owner.id
    except (ObjectDoesNotExist, AttributeError):
        return False


@check(Address)
def actor_owns_address(auth_token, actee, *args, **kwargs):
    """
    Returns True if the address object is either the user's
    shipping or billing address, False otherwise.

    @param actee  The address object in question
    """
    billing = auth_token.user.billing_address
    shipping = auth_token.user.shipping_address
    return ((billing and billing.id == actee.id) or
            (shipping and shipping.id == actee.id))


@check(Achievement)
def actor_owns_achievement_award_for_achievement(auth_token, actee, *args, **kwargs):
    """
    Returns True iff the actor is the owner of an AchievementAward for the
    Achievement.
    """
    try:
        return actee.achievement_awards.filter(user__id=auth_token.user_id).exists()
    except (ObjectDoesNotExist, AttributeError):
        return False


@check(AchievementAward)
def actor_owns_achievement_award(auth_token, actee, *args, **kwargs):
    "Returns True iff the actor is the owner of the AchievementAward"
    try:
        return auth_token.user_id == actee.user.id
    except (ObjectDoesNotExist, AttributeError):
        return False


@check(Assignment)
def actor_owns_assignment(auth_token, actee, *args, **kwargs):
    """Returns True iff the actor is the owner of the Assignment."""
    try:
        return auth_token.user_id == actee.user.id
    except (ObjectDoesNotExist, AttributeError):
        return False


@check(Assignment)
def actor_owns_assignment_or_is_guest(actee, auth_token=None, *args, **kwargs):
    """
    Returns True if the actor is the owner of the Assignment, or if the
    actor is a guest and the Assignment doesn't have a user @check
defined.
    """
    try:
        if not (actee.user or isinstance(auth_token, facade.models.AuthToken)):
            return True
        else:
            return actor_owns_assignment(auth_token, actee)
    except (ObjectDoesNotExist, AttributeError):
        return False


@check(AssignmentAttempt)
def actor_owns_assignment_attempt(auth_token, actee, *args, **kwargs):
    """
    Returns True iff the actor is the owner of the Assignment
    """
    return actor_owns_assignment(auth_token, actee.assignment)


@check(Credential)
def actor_owns_credential(auth_token, actee, *args, **kwargs):
    """
    Returns True iff the actor is the owner of the Credential
    """
    try:
        return auth_token.user_id == actee.user_id
    except (ObjectDoesNotExist, AttributeError):
        return False

@check(CredentialType)
def actor_owns_credential_for_credential_type(auth_token, actee, *args, **kwargs):
    """
    Returns True iff the actor is the owner of a Credential for the
    CredentialType.
    """
    try:
        return actee.credentials.filter(user__id=auth_token.user_id).exists()
    except (ObjectDoesNotExist, AttributeError):
        return False

@check(Event)
def actor_owns_event(auth_token, actee, *args, **kwargs):
    """
    Returns true if the actor is the owner of an event.
    """
    try:
        return auth_token.user_id == actee.owner.id
    except (ObjectDoesNotExist, AttributeError):
        return False


@check(Session)
def actor_owns_session(auth_token, actee, *args, **kwargs):
    """
    Returns True if the actor owns the event associated with this session.
    """
    try:
        return actor_owns_event(auth_token, actee.event)
    except (ObjectDoesNotExist, AttributeError):
        return False
