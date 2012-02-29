
from datetime import datetime

from django.core.exceptions import ObjectDoesNotExist

import facade

from pr_services.authorizer.checks import check
from pr_services.exceptions import InvalidActeeTypeException


@check
def actor_assigned_to_curriculum_enrollment(auth_token, actee, *args, **kwargs):
    """
    Returns True iff the actor is assigned to the CurriculumEnrollment
    """
    if not isinstance(actee, facade.models.CurriculumEnrollment):
        raise InvalidActeeTypeException()

    try:
        return actee.users.filter(id=auth_token.user_id).exists()
    except (ObjectDoesNotExist, AttributeError):
        return False


@check
def actor_assigned_to_event_session(auth_token, actee, *args, **kwargs):
    """
    Returns True if the actor is assigned to a session for the
    actee (an `Event` object).
    """
    if not isinstance(actee, facade.models.Event):
        raise InvalidActeeTypeException(actee)

    uid = auth_token.user_id
    session_filter = {
        'event': actee,
        'session_user_role_requirements__assignments__user__id': uid,
    }
    return facade.models.Session.objects.filter(**session_filter).exists()


@check
def actor_assigned_to_session(auth_token, actee, *args, **kwargs):
    """
    Returns True iff the actor has an assignment for this session
    """
    if not isinstance(actee, facade.models.Session):
        raise InvalidActeeTypeException()

    return actee.session_user_role_requirements.filter(
            assignments__user__id=auth_token.user_id).exists()


@check
def actor_has_completed_assignment_prerequisites(auth_token, actee,
        *args, **kwargs):
    """
    Returns True iff the actor has completed all of the prerequisite tasks
    for the task being queried.
    """
    if not isinstance(actee, facade.models.Assignment):
        raise InvalidActeeTypeException()

    try:
        return actor_has_completed_task_prerequisites(auth_token, actee.task)
    except (ObjectDoesNotExist, AttributeError):
        return False


@check
def actor_has_completed_task_prerequisites(auth_token, actee, *args, **kwargs):
    """
    Returns True iff the actor has completed all of the prerequisite tasks for the task being queried.
    """
    if not isinstance(actee, facade.models.Task):
        raise InvalidActeeTypeException()

    try:
        return actee.prerequisites_met(auth_token.user)
    except (ObjectDoesNotExist, AttributeError):
        return False


@check
def assignment_prerequisites_met(auth_token, actee, *args, **kwargs):
    """
    Returns True iff the assignment's prerequisites have been met
    """
    if not isinstance(actee, facade.models.Assignment):
        raise InvalidActeeTypeException()

    return actee.prerequisites_met


@check
def assignment_attempt_prerequisites_met(auth_token, actee, *args, **kwargs):
    """
    Returns True iff the assignment_attempt's prerequisites have been met
    """
    if not isinstance(actee, facade.models.AssignmentAttempt):
        raise InvalidActeeTypeException()

    return assignment_prerequisites_met(auth_token, actee.assignment)


@check
def assignment_attempt_meets_date_restrictions(auth_token, actee, *args, **kwargs):
    """
    Returns True iff the assignment_attempt's dates meet the restrictions
    @check
defined on the Assignment
    """
    if not isinstance(actee, facade.models.AssignmentAttempt):
        raise InvalidActeeTypeException()

    return not (isinstance(actee.date_started, datetime) and
        isinstance(actee.assignment.effective_date_assigned, datetime) and
        actee.date_started < actee.assignment.effective_date_assigned)


@check
def assignment_venue_matches_actor_preferred_venue(auth_token, actee, *args, **kwargs):
    """
    Returns true if the assignment is at a venue that matches the actor's
    preferred venue

    @param actee      Instance of Assignment
    """
    if not isinstance(actee, facade.models.Assignment):
        raise InvalidActeeTypeException()

    surr = actee.task.downcast_completely()
    if not isinstance(surr, facade.models.SessionUserRoleRequirement):
        raise InvalidActeeTypeException()

    try:
        actor_venues = auth_token.user.preferred_venues
    except (ObjectDoesNotExist, AttributeError):
        return False

    try:
        return actor_venues.filter(id=surr.session.room.venue.id).exists()
    except (ObjectDoesNotExist, AttributeError):
        pass

    try:
        return actor_venues.filter(id=surr.session.event.venue.id).exists()
    except (ObjectDoesNotExist, AttributeError):
        return False
