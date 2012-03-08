
import facade

from pr_services.authorizer.checks import check

@check
def actor_is_anybody(*args, **kwargs):
    return True


@check
def actor_is_guest(auth_token=None, *args, **kwargs):
    "Returns True if the actor is a guest."
    # Determine whether the actor is a guest or not, by testing to
    # see whether they are an authenticated user or not
    return not isinstance(auth_token, facade.models.AuthToken)


@check
def actor_is_authenticated(auth_token, *args, **kwargs):
    "Returns True if the actor is an authenticated user."
    return isinstance(auth_token, facade.models.AuthToken)
