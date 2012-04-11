"""
This module contains checks for each model type to ensure that an actor has
a specific role within an organization to which the actee belongs.

The most common entry point is the function `actor_has_role_in_actee_org`. This
function should be used in any role which needs to verify all object types. If
a role only needs a check for one specific object type, the function that checks
only that type can be used directly.

The checks themselves are straight forward but there are a few less obvious
implementation details specific to this module. The @check decorator is used for
all check functions to populate ORGROLE_CHECKS, which is a mapping from actee
type to the check function. The check decorator also attaches a hook which
runs before the function being decorated to ensure that the actor actually
has the role in question.
"""
import inspect
import types

from collections import defaultdict, Set

from django.db.models import Manager
from django.db.models.query import QuerySet

from pr_services.authorizer.checks import check as _check
from pr_services.caching import ORG_DESCENDENT_CACHE
from pr_services.exceptions import InvalidActeeTypeException

import facade

facade.import_models(locals())

# A mapping between actee_type and corresponding check functions
ORGROLE_CHECKS = defaultdict(list)

@_check
def actor_has_orgrole(auth_token, role_name, *args, **kwargs):
    return role_name in auth_token.user_roles_by_name


def ensure_actor_has_orgrole_hook(func, auth_token, actee, role_name,
        *args, **kwargs):
    """
    A pre-check hook that will ensure that the actor has the role
    in question before continuing the rest of check.
    """
    return actor_has_orgrole(auth_token, role_name)

# The following defines hooks which will run before every check in this module.
ORGROLE_CHECK_HOOKS = (ensure_actor_has_orgrole_hook, )

# XXX: The following redefines the check decorator for all subsequent uses,
# in order to populate the ORGROLE_CHECKS mapping and attach
# the pre-check hooks.
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


def check_role_in_orgs(auth_token, role_name, actee_orgs):
    """
    Check that the `auth_token` user has the `role` OrgRole for one of the
    organizations in `actee_orgs`.

    Args:
        auth_token: The user's auth token
        role_name: The name of the OrgRole to check for
        actee_orgs: A set of organization ids or a QuerySet of Organization
                    objects.
    Returns:
        True if the `auth_token` user has the OrgRole in one of the specified
        organizations or its descendent organizations. False otherwise.
    """
    actor_roles = auth_token.user_roles_by_name
    if not actor_roles:
        return False

    actor_orgs = actor_roles.get(role_name, None)
    if not actor_orgs:
        return False

    assert isinstance(actor_orgs, Set)

    if isinstance(actee_orgs, (QuerySet, Manager)):
        actee_orgs = set(actee_orgs.values_list('id', flat=True))
    elif not isinstance(actee_orgs, Set):
        actee_orgs = set(actee_orgs)

    if not actee_orgs:
        return False

    if actor_orgs & actee_orgs:
        return True

    for org in actor_orgs:
        descendents = ORG_DESCENDENT_CACHE[org]
        if descendents and actee_orgs & descendents:
            return True

    return False



def check_role_in_org(auth_token, role_name, org_id):
    """
    Check that the `auth_token` user has the OrgRole with `role_name` for the
    organization specified by `org_id` or one of its descendents.

    Args:
        auth_token - the user's auth token
        role_name - the name of the actor's OrgRole we are checking for
        org_id - the id of the organization we are checking against the actor
    """
    if not org_id:
        return False

    assert isinstance(org_id, (int, long))
    return check_role_in_orgs(auth_token, role_name, (org_id, ))


@check
def actor_has_role_for_actee(auth_token, actee, role_name,
        excluded_types=frozenset(), restricted_ops=frozenset(),
        *args, **kwargs):
    """Returns True if the actor has the specified OrgRole named `role` for an
    organization, and the actee is a member of the same organization or a
    descendent organization.

    This check supports ALL authorizable actee types for OrgRole privileges. It
    may be desirable to exclude some specific types from this broad check. In
    that case, such types can be specified in `excluded_types`.

    Arguments:
        auth_token: The user's auth token.
        actee: The object being acted on.
        role: The name of the OrgRole required for the actor.
        excluded_types: A set of types that will NOT be checked by this method.
        restricted_ops: A set of operations which will be checked by this
                        method.
    """
    t = type(actee)
    if t in excluded_types:
        # TODO(jcon): Possibly use a different exception type here
        raise InvalidActeeTypeException(actee)
    if restricted_ops:
        assert isinstance(restricted_ops, Set)
        assert restricted_ops <= frozenset('crud')
        if kwargs['op'] not in restricted_ops:
            # TODO(jcon): Possibly use a different exception type here
            raise InvalidActeeTypeException(actee)

    checks = ORGROLE_CHECKS.get(t.__name__, None)
    if not checks:
        bases = inspect.getmro(t)
        for base in bases:
            checks = ORGROLE_CHECKS.get(type(base).__name__, None)
            if checks:
                break
        else:
            # No specialized checks were found for type.
            # Actee must have an organization attribute or
            # else we dont know about it
            assert not isinstance(actee, UserOrgRole)
            try:
                org_id = actee.organization_id
            except AttributeError:
                raise InvalidActeeTypeException(actee)
            else:
                return check_role_in_org(auth_token, role_name, org_id)

    assert checks
    for func in checks:
        if not func(auth_token, actee, role_name, *args, **kwargs):
            return False

    return True


@check(Achievement)
def actor_has_role_for_achievement(auth_token, actee, role_name,
        *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization and the actee is an `Achievement` object. False otherwise.
    """
    return True


@check(Assignment)
def actor_has_role_for_assignment(auth_token, actee, role_name,
        *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization to which the actee (an `Assignment` object) belongs.
    False otherwise.
    """
    return actor_has_role_for_user(auth_token, actee.user, role_name,
            *args, **kwargs)


@check(Credential)
def actor_has_role_for_credential(auth_token, actee, role_name,
        *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the organization
    to which the actee (a `Credential` object) belongs. False Otherwise.
    """
    orgs = actee.user.organizations.all()
    return check_role_in_orgs(auth_token, role_name, orgs)


@check(CredentialType)
def actor_has_role_for_credential_type(auth_token, actee, role_name,
        *args, **kwargs):
    """
    Returns True if the actee is a `CredentialType` object and the actor has
    the role in question. Support for differentiating Credential types by
    Organization *may* be implemented in the future.
    """
    return True


@check(CurriculumTaskAssociation)
def actor_has_role_for_curriculum_task_assoc(auth_token, actee, role_name,
        *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization to which the actee (a `CurriculumTaskAssignment`
    object) belongs. False otherwise
    """
    try:
        org_id = actee.curriculum.organization_id
    except AttributeError:
        return False

    return check_role_in_org(auth_token, role_name, org_id)


@check(CurriculumEnrollment)
def actor_has_role_for_enrollment(auth_token, actee, role_name,
        *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization to which the actee (a `CurriculumEnrollment` object)
    belongs. False otherwise.
    """
    try:
        org_id = actee.curriculum.organization_id
    except AttributeError:
        return False

    return check_role_in_org(auth_token, role_name, org_id)


@check(CurriculumEnrollmentUserAssociation)
def actor_has_role_for_enrollment_association(auth_token, actee, role_name,
        *args, **kwargs):

    # check the enrollment curriculum organization
    if not actor_has_role_for_enrollment(auth_token,
            actee.curriculum_enrollment, role_name, *args, **kwargs):
        return False

    # check the enrollment user
    return actor_has_role_for_user(auth_token, actee.user, role_name,
            *args, **kwargs)


@check(Session)
def actor_has_role_for_session(auth_token, actee, role_name, *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization to which the actee (a `Session` object) belongs. False
    otherwise.
    """
    try:
        org_id = actee.event.organization_id
    except AttributeError:
        return False

    return check_role_in_org(auth_token, role_name, org_id)


@check(User)
def actor_has_role_for_user(auth_token, actee, role_name, *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization to which the actee (a `User` object) belongs. False
    otherwise.
    """
    actee_orgs = actee.organizations.distinct()
    if not actee_orgs:
        return actee.status == u'pending'

    return check_role_in_orgs(auth_token, role_name, actee_orgs)


@check(UserOrgRole)
def actor_has_role_for_userorgrole(auth_token, actee, role_name,
        *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the same
    organization as the actee (a `UserOrgRole` object) and the actee does not
    belong to other organizations.
    """
    # Allow adding a user to an organization when the user has
    # no previous organization affiliations.
    if not actee.owner.organizations.exists():
        return actee.owner.status == u'pending'

    return check_role_in_org(auth_token, role_name, actee.organization_id)


@check(Answer)
def actor_has_role_for_exam_answer(auth_token, actee, role_name,
        *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization which owns the actee, an `Answer` object.
    False otherwise.
    """
    return actor_has_role_for_exam_question(auth_token,
            actee.question, role_name, *args, **kwargs)


@check(Question, QuestionPool)
def actor_has_role_for_exam_question(auth_token, actee, role_name,
        *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization which owns the actee (a `Question` or `QuestionPool`
    object). False otherwise.
    """
    if isinstance(actee, QuestionPool):
        exam = actee.exam
    else:
        exam = actee.question_pool.exam

    return check_role_in_org(auth_token, role_name, exam.organization_id)


@check(Resource)
def actor_has_role_for_resource(auth_token, actee, role_name, *args, **kwargs):
    """
    Returns True if the actor has the specified OrgRole for the
    organization which owns the actee (a `Resource` object). False
    otherwise.
    """
    srtr = actee.session_resource_type_requirements
    orgs = srtr.values_list('session__event__organization', flat=True)
    return check_role_in_orgs(auth_token, role_name, orgs)


@check(Organization)
def actor_has_role_for_organization(auth_token, actee, role, *args, **kwargs):
    """
    Return True if the actor has the specified OrgRole for any
    organization at all.
    """
    return True
