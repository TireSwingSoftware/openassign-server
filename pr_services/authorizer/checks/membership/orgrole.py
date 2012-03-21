
import inspect
import logging
import types

from collections import defaultdict

from django.db.models import Q

from pr_services.authorizer.checks import check as _check
from pr_services.exceptions import InvalidActeeTypeException

import facade

facade.import_models(locals())

# A mapping between actee_type and corresponding check functions
ORGROLE_CHECKS = defaultdict(list)

def ensure_actor_has_orgrole_hook(func, auth_token, actee, role, *args, **kwargs):
    """A pre-check hook that will ensure that the actor has the role in question
    before continuing the rest of check."""
    query = Q(role__name=role, owner__id=auth_token.user_id)
    return UserOrgRole.objects.filter(query).exists()

# The following defines hooks which will run before every check in this module.
ORGROLE_CHECK_HOOKS = (ensure_actor_has_orgrole_hook, )

# Redefine the check decorator to populate the ORGROLE_CHECKS mapping
# and attach the pre-check hooks.
def check(*args):
    # decorating a function directly
    if len(args) == 1 and isinstance(args[0], types.FunctionType):
        func = _check(*args, pre_hooks=ORGROLE_CHECK_HOOKS)
        return func

    # caller passed a list of acceptable types
    def wrapper(func):
        func = _check(*args, pre_hooks=ORGROLE_CHECK_HOOKS)(func)
        for t in args:
            typename = t.__name__ if isinstance(t, type) else str(t)
            ORGROLE_CHECKS[typename].append(func)
        return func
    return wrapper


def check_orgrole_with_orgs(auth_token, role, orgs):
    """
    Check that the `auth_token` user has the `role` OrgRole for one of the
    organizations in `orgs` (a QuerySet of Organization objects).

    Args:
        auth_token - the users auth_token
        role - the name of the OrgRole to check
        orgs - a QuerySet of Organization objects

    Returns:
        True if the `auth_token` user has the OrgRole in one of the specified
        organizations. False otherwise.
    """
    return UserOrgRole.objects.filter(
            role__name=role,
            owner__id=auth_token.user_id,
            organization__in=orgs).exists()


def check_orgrole(auth_token, role, org=None, query=None):
    """
    Check that the `auth_token` user has the `role` OrgRole for `org`,
    or for one of the orgs matched by a query on the `auth_token` user's
    organizations restricted with `query` (a Django Q object).

    Args:
        auth_token - the users auth token
        role - the name of the OrgRole we are checking
        org - *optional* a specific organization to limit the check
        query - *optional* additional query to restrict organizations
    """
    base_query = Q(role__name=role, owner__id=auth_token.user_id)
    if isinstance(org, Organization):
        base_query &= Q(organization__id=org.id)
    elif org:
        base_query &= Q(organization__id=org)
    query = query & base_query if query else base_query
    return UserOrgRole.objects.filter(query).exists()


@check
def actor_role_in_actee_org(auth_token, actee, role, *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole named `role` for an
    organization, and the actee is a member of the same organization.

    This check supports ALL authorizable actee types for OrgRole privileges.
    """
    t = type(actee)
    typename = t.__name__
    checks = ORGROLE_CHECKS.get(typename, None)
    if not checks:
        bases = inspect.getmro(t)
        for base in bases:
            typename = type(base).__name__
            checks = ORGROLE_CHECKS.get(typename, None)
            if checks:
                break
        else:
            # XXX: No specialized checks found for type.
            # Actee must have an organization attribute or
            # else we dont know about it
            assert not isinstance(actee, UserOrgRole)
            try:
                return check_orgrole(auth_token, role, actee.organization)
            except AttributeError:
                raise InvalidActeeTypeException(actee)

    assert checks
    return all(func(auth_token, actee, role, *args, **kwargs) for func in checks)


@check(Assignment)
def actor_orgrole_for_assignment(auth_token, actee, role, *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization to which the actee (an `Assignment` object) belongs.
    False otherwise.
    """
    if (actor_orgrole_for_user(auth_token, actee.user, role, *args, **kwargs)):
        return True


@check(Credential)
def actor_orgrole_for_credential(auth_token, actee, role, *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the organization to
    which the actee (a `Credential` object) belongs. False Otherwise.
    """
    actee_orgs = actee.user.organizations.all()
    if not actee_orgs:
        return False

    return check_orgrole_with_orgs(auth_token, role, actee_orgs)


@check(CredentialType)
def actor_orgrole_for_credential_type(auth_token, actee, role, *args, **kwargs):
    """
    Returns True if the actor is a `CredentialType` object. Currently this is a
    tautology because it always returns True. Support for differentiating
    Credential types by Organization *may* be implemented in the future.
    """
    return True


@check(CurriculumTaskAssociation)
def actor_orgrole_for_curriculum_task_assoc(auth_token, actee, role, *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization to which the actee (a `CurriculumTaskAssignment`
    object) belongs. False otherwise
    """
    try:
        organization = actee.curriculum.organization
    except AttributeError:
        return False
    else:
        return check_orgrole(auth_token, role, organization)


@check(Task)
def actor_orgrole_for_task(auth_token, actee, role, *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization to which the actee (a `Task` object or instance)
    belongs. False otherwise.
    """
    return check_orgrole(auth_token, role, actee.organization)


@check(CurriculumEnrollment)
def actor_orgrole_for_enrollment(auth_token, actee, role, *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization to which the actee (a `CurriculumEnrollment` object)
    belongs. False otherwise.
    """
    try:
        organization = actee.curriculum.organization
    except AttributeError:
        return False
    else:
        return check_orgrole(auth_token, role, organization)


@check(Session)
def actor_orgrole_for_session(auth_token, actee, role, *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization to which the actee (a `Session` object) belongs. False
    otherwise.
    """
    try:
        organization = actee.event.organization
    except AttributeError:
        return False
    else:
        return check_orgrole(auth_token, role, organization)


@check(SessionUserRoleRequirement)
def actor_orgrole_for_surr(auth_token, actee, role, *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization to which the actee (as `SessionUserRoleRequirement` object)
    belongs. False otherwise.
    """
    return actor_orgrole_for_task(auth_token, actee, role, *args, **kwargs)


@check(User)
def actor_orgrole_for_user(auth_token, actee, role, *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization to which the actee (a `User` object) belongs. False
    otherwise.
    """
    actee_orgs = actee.organizations.distinct()
    if not actee_orgs:
        return True

    return check_orgrole_with_orgs(auth_token, role, actee_orgs)


@check(UserOrgRole)
def actor_orgrole_for_userorgrole(auth_token, actee, role, *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the same
    organization as the actee (a `UserOrgRole` object) and the actee does not
    belong to other organizations.
    """
    # XXX: Allow adding a user to an organization when the user has
    # no previous organization affiliations.
    if not actee.owner.organizations.exists():
        return True

    return check_orgrole(auth_token, role, actee.organization_id)


@check(Answer)
def actor_orgrole_for_exam_answer(auth_token, actee, role, *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization which owns the actee, an `Answer` object.
    False otherwise.
    """
    return actor_orgrole_for_exam_question(auth_token, actee.question, role, *args, **kwargs)


@check(Question, QuestionPool)
def actor_orgrole_for_exam_question(auth_token, actee, role, *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization which owns the actee (a `Question` or `QuestionPool`
    object). False otherwise.
    """
    if isinstance(actee, QuestionPool):
        exam = actee.exam
    else:
        exam = actee.question_pool.exam

    return actor_orgrole_for_task(auth_token, exam, role, *args, **kwargs)


@check(Resource)
def actor_orgrole_for_resource(auth_token, actee, role, *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization which owns the actee (a `Resource` object). False
    otherwise.
    """
    query = Q(organization__events__sessions__session_resource_type_requirements=actee)
    return check_orgrole(auth_token, role, query=query)
