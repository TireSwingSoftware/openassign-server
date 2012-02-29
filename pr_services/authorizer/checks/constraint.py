
from django.core.exceptions import ObjectDoesNotExist
from pr_services.authorizer.checks import check
from pr_services.exceptions import InvalidActeeTypeException, AttributeNotUpdatedException

import facade

@check
def actor_is_acting_upon_themselves(auth_token, actee, *args, **kwargs):
    """
    Returns True if the actor is a valid authenticated user in
    the system who is acting upon themselves.

    @param actee  A user object that we wish to compare the actor to
    """
    if not isinstance(actee, facade.models.User):
        raise InvalidActeeTypeException()

    return auth_token.user_id == actee.id


@check
def actor_is_adding_allowed_many_ended_objects_to_user(auth_token, actee,
        attribute_name, allowed_pks, update_dict, *args, **kwargs):
    """
    This is a strange new breed of auth_check that concerns itcls with the
    update_dict. It ensures that the update_dict is only attempting to add
    items from the list of allowed primary keys to the attribute on the actee.
    It will return false if any 'remove' operation is in the dict, or if any
    primary key appears in the add list that is not in the allowed primary
    key list.

    @param auth_token       The authentication token of the acting user
    @type auth_token        auth_token
    @param actee            A user object that we are evaluation authorization for
    @type actee             user
    @param attribute_name   The attribute that we are authorizing the update
                            call based on
    @type attribute_name    string
    @param allowed_pks      A list of primary keys that we will allow the actor
                            to add to the actee's many ended attribute
    @type allowed_pks       list
    @param update_dict      The dictionary of changes that the actor is
                            attempting to apply to actee
    @type update_dict       dict
    @return                 A boolean of whether or not the actor will be
                            allowed to run the update call
    @raises                 InvalidActeeTypeException, AttributeNotInUpdateDictException
    """
    if not isinstance(actee, facade.models.User):
        raise InvalidActeeTypeException()
    if attribute_name not in update_dict:
        raise AttributeNotUpdatedException()
    allowed_pks = set(allowed_pks)
    current_pks = set()
    for current_foreign_object in getattr(actee, attribute_name).all():
        current_pks.add(current_foreign_object.id)
    added_keys = update_dict[attribute_name]
    if isinstance(added_keys, dict):
        # For now we will hate on the user if they try to remove an item.  We can change this later if we need to, but for now
        # this meets our needs.
        if 'remove' in added_keys:
            return False
        added_keys = added_keys['add']
    for key in added_keys:
        if key not in current_pks and key not in allowed_pks:
            # The user is attempting to add a key that the actee doesn't already have and it isn't in the allowed list
            return False
    # There weren't any objections, so I guess we are clear
    return True


@check
def actor_status_check(auth_token, status, *args, **kwargs):
    """
    Returns True if the actor's status is equal to the specified status.

    @param actee    Not used by this method
    @type actee     user
    @param status   The status value that we want to know if the user has or not
    @type status    string
    @return         True if the actor's status is equal to the specified status, false otherwise.
    """
    return auth_token.user.status == status


@check
def actor_is_venue_creator(auth_token, actee, *args, **kwargs):
    """
    Returns True if the actor is the user who created the venue, which is discovered by
    examining the venue's blame
    """
    if not isinstance(actee, facade.models.Venue):
        raise InvalidActeeTypeException()

    try:
        return auth_token.user_id == actee.blame.user.id
    except (ObjectDoesNotExist, AttributeError):
        return False


@check
def actees_attribute_is_set_to(actee, actee_model_name, attribute_name,
        attribute_value, *args, **kwargs):
    """
    This complicatedly name method exists to be a bit generically useful.
    It will examine actee, ensuring that it is of type actee_model_name.
    It will then ensure that attribute_name's value is equal to attribute_value.

    ** Note: This depends on the model class's (or at least its parent class)
    being in facade.models. **

    @param auth_token       The authentication token of the acting user.
                            Guests are allowed, and so this method does not
                            use the auth_token
    @type auth_token        facade.models.AuthToken
    @param actee            The object in question
    @type actee             pr_models.PRModel
    @param actee_model_name The name of the type of the model that this check
                             is supposed to be applied to
    @type actee_model_name  str
    @param attribute_name   The name of the attribute on actee that we want
                            do perform a comparison on
    @type attribute_name    str
    @param attribute_value  The value that actee's attribute should be compared to
    @type attribute_value   Many types are allowed (string, boolean, int, etc.)
    """
    try:
        if not isinstance(actee, getattr(facade.models, actee_model_name)):
            raise InvalidActeeTypeException()
        return getattr(actee, attribute_name) == attribute_value
    except (ObjectDoesNotExist, AttributeError):
        return False

@check
def actees_foreign_key_object_has_attribute_set_to(auth_token, actee,
        actee_model_name, attribute_name, foreign_object_attribute_name,
        foreign_object_attribute_value):
    """
    This complicatedly name method exists to be a bit generically useful.
    It will examine actee, ensuring that it is of type actee_model_name.
    It will then follow a foreign key relationship,
    actee.foreign_object_attribute_name, and ensure that that attribute's
    value is equal to foreign_object_attribute_value.

    ** Note: This depends on the model class's (or at least its parent class)
    being in facade.models. **

    @param auth_token                       The authentication token of the
                                            acting user.  Guests are allowed,
                                            and so this method does not use
                                            the auth_token
    @type auth_token                        facade.models.AuthToken
    @param actee                            The object in question
    @type actee                             pr_models.PRModel
    @param actee_model_name                 The name of the type of the model
                                            that this check is supposed to be
                                            applied to
    @type actee_model_name                  str
    @param attribute_name                   The name of the attribute on actee
                                            that we can use to retrieve the foreign
                                            object
    @type attribute_name                    str
    @param foreign_object_attribute_name    The name of the attribute on actee
                                            that will lead us to the foreign
                                            object we care about
    @type foreign_object_attribute_name     str
    @param foreign_object_attribute_value   The value that the foriegn
                                            object's attribute should be
                                            compared to
    @type foreign_object_attribute_value    Many types are allowed (string,
                                            boolean, int, etc.)
    """
    try:
        if not isinstance(actee, getattr(facade.models, actee_model_name)):
            raise InvalidActeeTypeException()

        foreign_object = getattr(actee, attribute_name)
        return actees_attribute_is_set_to(auth_token, foreign_object,
                foreign_object.__class__.__name__,
                foreign_object_attribute_name,
                foreign_object_attribute_value)
    except (ObjectDoesNotExist, AttributeError):
        return False


@check
def populated_exam_session_is_finished(auth_token, actee, *args, **kwargs):
    """
    Does nothing if the ExamSession does not have any answered questions
    or ratings.  That allows us to use the same ACL to allow creation of
    an ExamSession and allow reading results.  Returns True if the
    ExamSession has been finished, else False.

    @param actee      Instance of ExamSession
    """
    # This test allows us to know if this ExamSession is new or not by
    # virtue of it being populated.
    if not (isinstance(actee, facade.models.ExamSession) and
            actee.response_questions.count()):
        raise InvalidActeeTypeException()

    return bool(actee.date_completed)


@check
def actor_actee_enrolled_in_same_session(auth_token, actee, actor_sur_id,
        actee_sur_id, *args, **kwargs):
    """
    Returns True if the actor and the actee are both enrolled in the same
    session, for which actor is in the session_user_role actor_sur, and
    actee is in the session_user_role actee_sur.  Returns False otherwise.

    This method is only for use when the actee is a user.

    @param actee      A user object that we are evaluation authorization for
    @param actor_sur_id  The primary key of the session_user_role with which the
            actor should be enrolled in the session
    @param actee_sur_id  The primary key of the session_user_role with which
            the actee should be enrolled in the session
    """
    if not isinstance(actee, facade.models.User):
        raise InvalidActeeTypeException()

    actee_sessions = set(facade.models.Session.objects.filter(
        session_user_role_requirements__assignments__user__id=actee.id,
        session_user_role_requirements__session_user_role__id=actee_sur_id
        ).values_list('id', flat=True))
    actor_sessions = set(facade.models.Session.objects.filter(
        session_user_role_requirements__assignments__user__id=auth_token.user_id,
        session_user_role_requirements__session_user_role__id=actor_sur_id
        ).values_list('id', flat=True))
    # The intersection of the two sets will be the set of sessions that they
    # are both enrolled in.  If this is not the empty set, then return True
    return bool(actor_sessions & actee_sessions)


@check
def actor_is_instructor_manager_of_actee(auth_token, actee, *args, **kwargs):
    """
    Returns True if the actor is the instructor manager for a product
    line in which the actee is an instructor.

    @param actee      A user object that we are evaluation authorization for
    """
    if not isinstance(actee, facade.models.User):
        raise InvalidActeeTypeException()

    return facade.models.ProductLine.objects.filter(
            instructors__id__exact=actee.id,
            instructor_managers__id__exact=auth_token.user_id).exists()

#    actee_product_lines_instructor_in = set(
#        facade.models.ProductLine.objects.filter(
#            instructors__id__exact=actee.id).values_list('id', flat=True))
#    actor_product_lines_im_for = set(
#        facade.models.ProductLine.objects.filter(
#            instructor_managers__id__exact=auth_token.user_id
#        ).values_list('id', flat = True))
#    if actor_product_lines_im_for & actee_product_lines_instructor_in:
#        return True
#    return False

@check
def surr_is_of_a_particular_sur(actee, session_user_role_id, *args, **kwargs):
    """
    Returns True iff the session_user_role associate with the actee is the same as the
    session_user_role specified by the parameter session_user_role.
    """
    if not isinstance(actee, facade.models.SessionUserRoleRequirement):
        raise InvalidActeeTypeException()

    try:
        return actee.session_user_role.id == session_user_role_id
    except (ObjectDoesNotExist, AttributeError):
        return False
