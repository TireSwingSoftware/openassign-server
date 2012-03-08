
import facade

from django.core.exceptions import ObjectDoesNotExist

from pr_services.authorizer.checks import check
from pr_services.exceptions import InvalidActeeTypeException

facade.import_models(locals())


@check
def actor_member_of_group(auth_token, group_id, *args, **kwargs):
    """
    Returns True if the actor is a member of the specified group, False otherwise.

    @param actee      Not used by this method, but must be passed anyway as
            per authorization system requirements
    @param group_id   The primary key of the group we wish to test membership in
    """
    return facade.models.Group.objects.filter(
            id=group_id, users__id=auth_token.user_id).exists()


@check(DomainAffiliation)
def actor_related_to_domain_affiliation(auth_token, actee, *args, **kwargs):
    """
    Returns True if the DomainAffiliation's 'user' attribute
    references the actor

    @param actee  The DomainAffiliation object in question
    """
    return bool(auth_token.user_id == actee.user.id)


@check(Group)
def actor_is_group_manager(auth_token, actee, *args, **kwargs):
    """
    Returns True if the actor is the manager of the group.

    @param actee  Instance of a group
    """
    try:
        return actee.managers.filter(id=auth_token.user_id).exists()
    except ObjectDoesNotExist:
        pass


@check(User)
def actee_is_in_group_and_domain(auth_token, actee, group_id, domain_id,
        *args, **kwargs):
    """
    If the actee is in the group, the method returns True iff they are also
    of the domain.  If they are not in the group, it will return False.

    This is useful for making sure that participants who register themselves are
    in a particular domain, such as 'constantcontact.com' for the Constant
    Contact variant.

    Note that returning False instead of True if the user is not a part of
    the specified group is a different behavior from what the Constant
    Contact variant does!

    @param actee    The user object in question
    @type actee     user
    @param group_id The primary key of the group that the actee must be a member of
    @param domain_id the primary key of the domain
    """
    in_group = actee.groups.filter(id=group_id).exists()
    in_domain = actee.domain_affiliations.filter(domain_id=domain_id).exists()
    return in_group and in_domain


@check(Group)
def actor_is_in_actee_which_is_a_group(auth_token, actee, *args, **kwargs):
    """Returns true if the actee is a group and the actor is a member thereof."""
    try:
        return actee.users.filter(id=auth_token.user_id).exists()
    except (ObjectDoesNotExist, AttributeError):
        return False


@check(Organization)
def actor_is_in_actee_which_is_an_organization(auth_token, actee, *args, **kwargs):
    """
    Returns True if the actee is an Organization and the actor belongs to that
    organization.
    """
    return auth_token.user.organizations.filter(id=actee.id).exists()
