"""
This module contains the authorizer class, which is able
to answer the question of whether or not a particular
user has access to a particular attribute on a particular
model.
"""

try:
    import cPickle as pickle
except ImportError:
    import pickle

import collections
import inspect
import logging
import time

from collections import namedtuple, defaultdict
from functools import partial
from operator import itemgetter

from django.db.models import Model

from pr_services import exceptions

import facade

__all__ = ('Authorizer', )

_INVALID_ACTEE_TYPE_MSG = 'Invalid Actee Type'
_ATTR_NOT_UPDATED_MSG = 'Attributes not updated'

CREATE = 'c'
READ = 'r'
UPDATE = 'u'
DELETE = 'd'
ARBITRARY = 'a'
METHOD = 'm'

facade.import_models(locals(), globals())


_sentinel = object()
def defaultargvalue(method, argname):
    """
    Return the default value for argument `argname` in the signiture of `method`.
    If the argument does not exist an exception is raised. If there is no
    default value a sentinel object is returned to allow distinction between no
    default argument and a default argument with a None value.

    Raises:
        ValueError - if argument does not exist in method signiture
    """
    argspec = inspect.getargspec(method)
    argpos = argspec.args.index(argname) # throws the value exception
    if not argspec.defaults:
        return _sentinel
    # offset is the pos in argspec.args where default values begin
    offset = len(argspec.args) - len(argspec.defaults)
    if argpos >= offset:
        return argspec.defaults[argpos - offset]
    else:
        return _sentinel


class CheckMethodWrapper(namedtuple('_CheckMethodWrapper',
                                    'method actee_required allow_guests')):
    """
    Structure for wrapping check method objects to expose a more efficient
    interface to access the properties we need when running the checks. Provides
    a thin interface to call the method checks with the appropriate handling.
    """

    @property
    def name(self):
        return self.method.func.__name__

    def __new__(cls, name, method_kwargs):
        """
        Args:
            name - A string representing the method name
            method_kwargs - the static parameters to pass to the check method
                         (defined by the role)
        """
        # TODO: decouple check methods from the authorizer by replacing the
        # method lookup mechanism with something a bit more sophisticated.
        method = getattr(facade.subsystems.Authorizer, name)

        # check if the actee is required/used by the check method.
        # it is considered to be required if the method has an argument
        # called 'actee' and that it does not default to None
        try:
            actee_required = defaultargvalue(method, 'actee') is not None
        except ValueError:
            actee_required = False

        # check if the method requires an auth token, if not allow guests
        try:
            allow_guests = defaultargvalue(method, 'auth_token') is None
        except ValueError:
            allow_guests = True

        # apply the method keyword arguments defined by the role
        method = partial(method, **method_kwargs)

        return super(CheckMethodWrapper, cls).__new__(cls, method,
                actee_required, allow_guests)

    def __call__(self, auth_token=None, actee=None, *args, **kwargs):
        if not isinstance(auth_token, AuthToken):
            if auth_token:
                raise exceptions.NotLoggedInException
            if not self.allow_guests:
                # fast-path: user is guest and guest is not allowed
                return False
        if self.actee_required and not actee:
            raise exceptions.InvalidActeeTypeException

        return self.method(auth_token=auth_token, actee=actee, *args, **kwargs)


class ACLWrapper(namedtuple('_ACLWrapper', 'object privs methods')):
    """
    A wrapper around ACL and ACMethodCall model objects to expose a more
    efficient interface for the type of access required by the authorizer.
    """

    def check(self, auth_token=None, actee=None, *args, **kwargs):
        """
        Execute the check methods for the acl structure `self` represents using
        `auth_token` and `actee` if required. If the operation is an update, a
        keyword argument `update_dict` should be passed with a dictionary of
        changed key-value pairs.

        Args:
            auth_token - an auth token for the user performing the operation
            actee - *optional* object being acted on
            update_dict - *optional* dict of attribute updates used only for
                         update operations.

        Returns:
            The result of all check method results ANDed together
        """

        # Process each ACL method and log the entire process
        # ignore InvalidActeeTypeException but ensure that in order
        # to return True the following conditions must be met:
        #
        #   1) at least one check has a valid actee type
        #   2) all checks accepting actee type, return True (logical AND)
        log = facade.subsystems.Authorizer.logger
        valid_type = False
        log.add_row(('Actee Type:', type(actee).__name__,
            '(op=%s)' % kwargs['op']))
        for method in self.methods:
            role_name = self.object.role.name
            log_entry = [role_name, method.name]
            try:
                result = method(auth_token, actee, *args, **kwargs)
                valid_type = True
                log_entry.append(result)
                log.add_row(log_entry)
                if not result:
                    # short-circuit if method check fails
                    log.add_row(('Result:', 'DENIED', ''))
                    log.commit()
                    return False
            except exceptions.InvalidActeeTypeException:
                log_entry.append(_INVALID_ACTEE_TYPE_MSG)
                log.add_row(log_entry)
            except exceptions.AttributeNotUpdatedException:
                #XXX: is this catch still necessary?
                log_entry.append(_ATTR_NOT_UPDATED_MSG)
                log.add_row(log_entry)
        # at this point no acl check method has returned False
        # all acl check methods passed or raised an exception
        message = 'GRANTED' if valid_type else 'DENIED'
        log.add_row(('Result:', message, ''))
        log.commit()
        return valid_type


class ACLCache(object):
    """
    A simple authorizer-specific caching mechanism for efficiently storing all
    ACL objects and related models.

    ACLs are partitioned into several dicts for each of the crud operations
    allowing more efficient lookup for ACLs given an operation and a specific
    type.
    """

    # a timestamp for when the cache was last updated
    timestamp = None

    # a two-dimensional dictionary of acls where the dimensions of the
    # mapping are [type of operation ie. CREATE] [ operation specific key ]
    _acls = None

    def __len__(self):
        return len(self.acls)

    def __init__(self):
        """Load all ACL related objects from the database."""
        def acldict():
            return defaultdict(list)

        # grab all the methods first sine we can do this in one query
        method_cols = ('acl', 'ac_check_method__name', 'ac_check_parameters')
        method_call_items = itemgetter(*method_cols)
        aclmethods = defaultdict(list)
        for method_call in ACMethodCall.objects.values(*method_cols):
            acl, method_name, kwargs = method_call_items(method_call)
            kwargs = pickle.loads(str(kwargs)) if kwargs else {}
            method = CheckMethodWrapper(method_name, kwargs)
            aclmethods[acl].append(method)

        c, r, u, d = acldict(), acldict(), acldict(), acldict()
        a, m = acldict(), acldict()

        # grab all the acl objects in one more query
        for acl in ACL.objects.select_related():
            privs = pickle.loads(str(acl.acl))
            cached_acl = ACLWrapper(acl, privs, aclmethods[acl.id])
            for actee_type, priv in privs.iteritems():
                if hasattr(facade.models, actee_type):
                    # XXX: it is critical for the integrity of the authorizer
                    # that acls *not* be added to these maps unless they
                    # are capable of granting the relevant permission
                    if priv.get(CREATE, None):
                        c[actee_type].append(cached_acl)
                    if priv.get(READ, None):
                        r[actee_type].append(cached_acl)
                    if priv.get(UPDATE, None):
                        u[actee_type].append(cached_acl)
                    if priv.get(DELETE, None):
                        d[actee_type].append(cached_acl)
                elif getattr(facade.managers, actee_type, None):
                    # handle manager method permissions
                    for method_name in priv['methods']:
                        manager_class = getattr(facade.managers, actee_type)
                        assert hasattr(manager_class, method_name)
                        # (manager name, method_name)
                        m[(actee_type, method_name)].append(cached_acl)
                else:
                    raise TypeError("unauthorizable type %s" % actee_type)

            # handle arbitrary permissions
            if acl.arbitrary_perm_list:
                serialized = str(acl.arbitrary_perm_list)
                arbitrary_perms = frozenset(pickle.loads(serialized))
                for perm in arbitrary_perms:
                    a[perm].append(cached_acl)

        self._acls = {
            CREATE: c, READ: r, UPDATE: u, DELETE: d,
            ARBITRARY: a,
            METHOD: m
        }
        self.timestamp = time.time()

    def collect(self, op, key):
        """
        Return a list of acls relevant for `op` given `key`.

        For create, read, update, or delete operations the key is the actee
        object and this method runs with worst-case O(m) complexity where m is
        the depth of the actee's type heirarchy.

        For method operations the key is a 2-tuple of
        (manager class name, method name). Access is O(1)

        For arbitrary permissions the key is a string
        representing the permission. Access is O(1).

        Args:
            op - the operation being performed, a single character in 'crud'
            key - an operation specific acl key. For crud operations this is
                  the actee. For method operations, (manager name, method name).
                  For arbitrary permissions, the permission name.

        Returns:
            A list of cached ACL objects (See `ACLWrapper` above)
        """
        if op in (METHOD, ARBITRARY):
            return self._acls[op].get(key, ())

        if op in (CREATE, READ, UPDATE, DELETE):
            acls = self._acls[op]
            typeobj = key if isinstance(key, type) else type(key) # key is actee
            name = typeobj.__name__
            if name in acls:
                return acls[name]
            else:
                for basetype in inspect.getmro(typeobj):
                    name = basetype.__name__
                    if name in acls:
                        return acls[name]
                else:
                    return ()
        else:
            assert False


class Authorizer(object):
    """
    The default authorizer for the PR system. It determines based on an
    auth_token and access controls defined as part of a role, whether or not
    the user represented by the auth_token has the privileges to perform an
    operation.

    Currently supported authorization types:

        - create, read, update, and delete for any PRModel object.

        - method invokation for ObjectManager methods wrapped with
          the @service_method decorator.

        - arbitrary permissions
    """

    acls = ACLCache()
    logger = facade.subsystems.Logger('pr_services.authorizer', logging.getLevelName('TRACE'))

    @classmethod
    def flush(cls):
        """Flush all cached ACLs and reload them from the database."""
        # XXX: this assignment is atomic so other threads reading from the
        # current cache (if there is one) will continue doing so until they
        # request a new reference. This will allow for uninterupted iteration
        # of the acl dict and/or sub-dicts.
        cls.acls = ACLCache()

    @classmethod
    def check_method_call(cls, auth_token, manager, method,
            call_args=(), call_kwargs=None):
        """
        Check if the `auth_token` user has access to call `method` on
        `manager`, an instance of ObjectManager.

        Args:
            auth_token - the auth token of the user performing the operation
            manager - an instance of ObjectManager or subclass
            method - the method which will be called (a python function object)
            args - a tuple of arguments passed to `method`
            kwargs - a dict of keyword arguments passed to `method`

        Raises:
            PermissionDeniedException - For insufficient privileges
        """
        # cant use the facade for this import and it has to happen here
        # since Authorizer is used in ObjectManager
        from pr_services.object_manager import ObjectManager

        if not (isinstance(manager, type) and
                issubclass(manager, ObjectManager)):
            if isinstance(manager, ObjectManager):
                manager = manager.__class__
            elif isinstance(manager, basestring):
                manager = getattr(facade.managers, manager)
            else:
                raise TypeError("invalid manager type '%s'" % type(manager).__name__)

        if isinstance(method, basestring):
            method = getattr(manager, method)
        if not callable(method):
            raise TypeError("invalid method type '%s'" % type(method).__name__)

        key = (manager.__name__, method.__name__)
        acls = cls.acls.collect(METHOD, key)
        # XXX: For backwards compatibility method checks will be permissive by
        # default unless there exists one ACL which checks the method
        if not acls: # fast-path: many methods wont have ACLs
            return

        # the underscores are to prevent name collisions with the method
        # 'parameters' defined as part of the role
        context = dict(
            __manager=manager,
            __method=method,
            __args=call_args,
            __kwargs=call_kwargs or {})

        if not any(acl.check(auth_token, op=METHOD, **context) for acl in acls):
            raise exceptions.PermissionDeniedException()

    @classmethod
    def check_arbitrary_permissions(cls, auth_token, permission):
        """
        Check if the `auth_token` user has access to an arbitrary `permission`.
        If not, an exception is raised.

        Args:
            permission - A string representing the arbitrary permission

        Raises:
            PermissionDeniedException - For insufficient privileges
        """
        assert isinstance(permission, str)

        acls = cls.acls.collect(ARBITRARY, permission)
        if not any(acl.check(auth_token, None, op=ARBITRARY) for acl in acls):
            raise exceptions.PermissionDeniedException()

    @classmethod
    def check_create_permissions(cls, auth_token, actee):
        """
        Check if the `auth_token` user has create permissions for `actee`.
        An exception is raised if not.

        Args:
            actee - the object being created

        Raises:
            PermissionDeniedException - For insufficient privileges
        """
        assert isinstance(actee, Model) or issubclass(actee, Model)

        acls = cls.acls.collect(CREATE, actee)
        if not any(acl.check(auth_token, actee, op=CREATE) for acl in acls):
            raise exceptions.PermissionDeniedException()

    @classmethod
    def _check_attributes(cls, op, auth_token, actee, attributes):
        """
        Check that the `auth_token` user is authorized to perform `op` on the
        specified `attributes` of `actee`.
        """
        assert attributes and op in 'crud'
        assert isinstance(actee, Model) or issubclass(actee, Model)

        if not isinstance(attributes, collections.Set):
            attributes = frozenset(attributes)

        authorized = cls.get_authorized_attributes(op, auth_token, actee, attributes)
        if not authorized:
            raise exceptions.PermissionDeniedException()

        denied = attributes - authorized
        if denied:
            raise exceptions.PermissionDeniedException(denied, actee._meta.object_name)

    @classmethod
    def check_read_permissions(cls, auth_token, actee, attributes):
        """
        Check that the `auth_token` user has permission to read `attributes`
        of `actee`. An exception is raised if not.

        For a comprehensive list of all authorized fields,
        use the `get_authorized_attributes` method instead.

        Args:
            actee - the object being acted upon
            attributes - a set of attributes to read

        Raises:
            PermissionDeniedException - For insufficient privileges
        """
        cls._check_attributes(READ, auth_token, actee, attributes)

    @classmethod
    def check_update_permissions(cls, auth_token, actee, update_dict):
        """
        Checks that the `auth_token` user has permission to update `actee` using
        key-value pairs from `update_dict` as the object's attributes.

        An exception is raised if the user does not have sufficient privileges.

        For a comprehensive list of all authorized fields,
        use the `get_authorized_attributes` method instead.

        Args:
            actee - the object being acted upon
            update_dict - a dict of attributes (name-value pairs) to update

        Raises:
            PermissionDeniedException - For insufficient privileges
        """
        cls._check_attributes(UPDATE, auth_token, actee, update_dict)

    @classmethod
    def check_delete_permissions(cls, auth_token, actee):
        """
        Checks if the `auth_token` user has permission to delete `actee`. An
        exception is raised if not.

        Args:
            actee - the object being deleted

        Raises:
            PermissionDeniedException - For insufficient privileges
        """
        assert isinstance(actee, Model) or issubclass(actee, Model)

        acls = cls.acls.collect(DELETE, actee)
        if not any(acl.check(auth_token, actee, op=DELETE) for acl in acls):
            raise exceptions.PermissionDeniedException()

    @classmethod
    def get_authorized_attributes(cls, op, auth_token, actee, requested, update_dict=None):
        """
        Returns a list of fields for which the `auth_token` user has permission
        to perform the operation `op` on the actee.

        Args:
            op - the operation being performed, 'r' (read) or 'u' (update)
            actee - the object being acted on
            requested - a subset of attributes to verify
            update_dict - a dict of attributes (name-value pairs) to update

        Returns:
            A list of fields that the user is authorized to access.
        """
        assert op in 'ru'
        assert isinstance(actee, Model) or issubclass(actee, Model)

        actee_type = actee._meta.object_name
        authorized = set()
        if not isinstance(requested, collections.Set):
            requested = frozenset(requested)

        acls = cls.acls.collect(op, actee)
        for acl in acls:
            crud = acl.privs.get(actee_type)
            if not crud:
                for basetype in inspect.getmro(type(actee)):
                    crud = acl.privs.get(basetype.__name__, None)
                    if crud:
                        break
                else:
                    continue
            attributes = crud[op]
            if requested and not any(f in attributes
                    for f in requested if f not in authorized):
                # short-circuit: skip the methods if there are no attributes
                continue
            if not acl.check(auth_token, actee, update_dict=update_dict, op=op):
                # method checks failed
                continue
            authorized.update(attributes)
            if requested and authorized >= requested:
                # all requested attributes are authorized
                return requested
        # return the intersection of authorized and requested attributes
        return authorized & requested if requested else authorized


    #################################################################
    #
    # Below this block are where the methods that we use for the
    # authorization checks are found.  These methods are available to
    # be used through the ACL manager to define ACLs, and each one
    # must take an actor object and an actee object as its first
    # two parameters.
    #
    #################################################################

    #################################################################
    #
    # Methods for which actee is any PRModel.
    #
    #################################################################
    @classmethod
    def actor_owns_prmodel(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True if the actor is the same User object as is listed in the PRModel's owner field, or if the PRModel has None in its owner field.
        """
        if not isinstance(actee, pr_models.OwnedPRModel):
            raise exceptions.InvalidActeeTypeException()
        try:
            if actee.owner is None:
                return True
            elif auth_token.user_id == actee.owner.id:
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    #################################################################
    #
    # Methods for which actee is an address.
    #
    #################################################################
    @classmethod
    def actor_owns_address(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True if the address object is either the user's
        shipping or billing address, False otherwise.

        @param actee  The address object in question
        """

        if not isinstance(actee, facade.models.Address):
            raise exceptions.InvalidActeeTypeException()
        if auth_token.user.billing_address and auth_token.user.billing_address.id == actee.id:
            return True
        if auth_token.user.shipping_address and auth_token.user.shipping_address.id == actee.id:
            return True
        return False

    #################################################################################
    #
    # Methods for which actee is an Achievement
    #
    #################################################################################

    @classmethod
    def actor_owns_achievement_award_for_achievement(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True iff the actor is the owner of an AchievementAward for the Achievement
        """

        if not isinstance(actee, facade.models.Achievement):
            raise exceptions.InvalidActeeTypeException()
        try:
            return actee.achievement_awards.filter(user__id=auth_token.user_id).exists()
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    #################################################################################
    #
    # Methods for which actee is an AchievementAward
    #
    #################################################################################

    @classmethod
    def actor_owns_achievement_award(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True iff the actor is the owner of the AchievementAward
        """

        if not isinstance(actee, facade.models.AchievementAward):
            raise exceptions.InvalidActeeTypeException()
        try:
            if auth_token.user_id == actee.user.id:
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    #################################################################################
    #
    # Methods for which actee is an Assignment
    #
    #################################################################################
    @classmethod
    def actor_has_completed_assignment_prerequisites(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True iff the actor has completed all of the prerequisite tasks for the task being queried.
        """
        if not isinstance(actee, facade.models.Assignment):
            raise exceptions.InvalidActeeTypeException()
        try:
            if cls.actor_has_completed_task_prerequisites(auth_token, actee.task):
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    @classmethod
    def actor_owns_assignment(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True iff the actor is the owner of the Assignment
        """

        if not isinstance(actee, facade.models.Assignment):
            raise exceptions.InvalidActeeTypeException()
        try:
            if auth_token.user_id == actee.user.id:
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    @classmethod
    def actor_owns_assignment_or_is_guest(cls, actee, auth_token=None, *args, **kwargs):
        """
        Returns True if the actor is the owner of the Assignment, or if the actor is a guest and the Assignment doesn't have a user defined.
        """
        if not isinstance(actee, facade.models.Assignment):
            raise exceptions.InvalidActeeTypeException()
        try:
            if actee.user is None and not isinstance(auth_token, facade.models.AuthToken):
                return True
            else:
                return cls.actor_owns_assignment(auth_token, actee)
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    @classmethod
    def assignment_prerequisites_met(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True iff the assignment's prerequisites have been met
        """

        if not isinstance(actee, facade.models.Assignment):
            raise exceptions.InvalidActeeTypeException()
        return actee.prerequisites_met

    #################################################################################
    #
    # Methods for which actee is an AssignmentAttempt
    #
    #################################################################################

    @classmethod
    def assignment_venue_matches_actor_preferred_venue(cls, auth_token, actee, *args, **kwargs):
        """
        Returns true if the assignment is at a venue that matches the actor's
        preferred venue

        @param actee      Instance of Assignment
        """

        if not isinstance(actee, facade.models.Assignment):
            raise exceptions.InvalidActeeTypeException()

        surr = actee.task.downcast_completely()

        if not isinstance(surr, facade.models.SessionUserRoleRequirement):
            raise exceptions.InvalidActeeTypeException()

        try:
            actor_venues = set(auth_token.user.preferred_venues.values_list('id', flat = True))

            try:
                if surr.session.room.venue.id in actor_venues:
                    return True
            except ObjectDoesNotExist:
                pass
            except AttributeError:
                pass

            try:
                if surr.session.event.venue.id in actor_venues:
                    return True
            except ObjectDoesNotExist:
                pass
            except AttributeError:
                pass

        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    @classmethod
    def actor_owns_assignment_attempt(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True iff the actor is the owner of the Assignment
        """

        if not isinstance(actee, facade.models.AssignmentAttempt):
            raise exceptions.InvalidActeeTypeException()

        return cls.actor_owns_assignment(auth_token, actee.assignment)

    @classmethod
    def assignment_attempt_prerequisites_met(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True iff the assignment_attempt's prerequisites have been met
        """

        if not isinstance(actee, facade.models.AssignmentAttempt):
            raise exceptions.InvalidActeeTypeException()

        return cls.assignment_prerequisites_met(auth_token, actee.assignment)

    @classmethod
    def assignment_attempt_meets_date_restrictions(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True iff the assignment_attempt's dates meet the restrictions
        @classmethod
    defined on the Assignment
        """

        if not isinstance(actee, facade.models.AssignmentAttempt):
            raise exceptions.InvalidActeeTypeException()

        if isinstance(actee.date_started, datetime) and isinstance(actee.assignment.effective_date_assigned, datetime) and actee.date_started < actee.assignment.effective_date_assigned:
            return False

        return True

    #################################################################################
    #
    # Methods for which actee is a credential
    #
    #################################################################################
    @classmethod
    def actor_owns_credential(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True iff the actor is the owner of the Credential
        """
        if not isinstance(actee, facade.models.Credential):
            raise exceptions.InvalidActeeTypeException()
        try:
            if auth_token.user_id == actee.user.id:
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    #################################################################################
    #
    # Methods for which actee is a CurriculumEnrollment
    #
    #################################################################################
    @classmethod
    def actor_assigned_to_curriculum_enrollment(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True iff the actor is assigned to the CurriculumEnrollment
        """
        if not isinstance(actee, facade.models.CurriculumEnrollment):
            raise exceptions.InvalidActeeTypeException()
        try:
            return actee.users.filter(id=auth_token.user_id).exists()
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    #################################################################
    #
    # Methods for which actee is a DomainAffiliation
    #
    #################################################################
    @classmethod
    def actor_related_to_domain_affiliation(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True if the DomainAffiliation's 'user' attribute
        references the actor

        @param actee  The DomainAffiliation object in question
        """

        if not isinstance(actee, facade.models.DomainAffiliation):
            raise exceptions.InvalidActeeTypeException()

        return bool(auth_token.user_id == actee.user.id)

    #################################################################################
    #
    # Methods for which actee is an event
    #
    #################################################################################

    @classmethod
    def actor_owns_event(cls, auth_token, actee, *args, **kwargs):
        """
        Returns true if the actor is the owner of an event.
        """
        if not isinstance(actee, facade.models.Event):
            raise exceptions.InvalidActeeTypeException()

        try:
            if auth_token.user_id == actee.owner.id:
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    @classmethod
    def actor_assigned_to_event_session(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True if the actor is assigned to a session for the
        actee (an `Event` object).
        """
        if not isinstance(actee, Event):
            raise exceptions.InvalidActeeTypeException(actee)

        uid = auth_token.user_id
        session_filter = {
            'event': actee,
            'session_user_role_requirements__assignments__user__id': uid,
        }
        return Session.objects.filter(**session_filter).exists()

    #################################################################################
    #
    # Methods for which actee is an ExamSession
    #
    #################################################################################
    @classmethod
    def populated_exam_session_is_finished(cls, auth_token, actee, *args, **kwargs):
        """
        Does nothing if the ExamSession does not have any answered questions
        or ratings.  That allows us to use the same ACL to allow creation of
        an ExamSession and allow reading results.  Returns True if the
        ExamSession has been finished, else False.

        @param actee      Instance of ExamSession
        """
        # This test allows us to know if this ExamSession is new or not by virtue of it being populated.
        if not (isinstance(actee, facade.models.ExamSession) and (
                actee.response_questions.count())):
            raise exceptions.InvalidActeeTypeException()
        return bool(actee.date_completed)

    #################################################################################
    #
    # Methods for which actee is a refund
    #
    #################################################################################

    @classmethod
    def refund_does_not_exceed_payment(cls, auth_token, actee, *args, **kwargs):
        """
        Returns true if the refund does not put the total amount of
        refunds for a particular payment over the value of the payment.

        @param actee      Instance of refund
        """

        if not isinstance(actee, facade.models.Refund):
            raise exceptions.InvalidActeeTypeException()
        total_refunds = 0
        for r in actee.payment.refunds.values_list('amount', flat = True):
            total_refunds += r
        if actee.amount > actee.payment.amount - total_refunds:
            return False
        else:
            return True

    #################################################################################
    #
    # Methods for which actee is a session
    #
    #################################################################################

    @classmethod
    def actor_assigned_to_session(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True iff the actor has an assignment for this session
        """
        if not isinstance(actee, facade.models.Session):
            raise exceptions.InvalidActeeTypeException()
        if actee.session_user_role_requirements.filter(assignments__user=auth_token.user).exists():
            return True

        return False

    @classmethod
    def actor_owns_session(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True if the actor owns the event associated with this session.
        """
        if not isinstance(actee, facade.models.Session):
            raise exceptions.InvalidActeeTypeException()

        try:
            the_event = actee.event
            if cls.actor_owns_event(auth_token, the_event):
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    @classmethod
    def actor_is_product_line_manager_of_session(cls, auth_token, actee, *args, **kwargs):
        """
        Returns true if the actor is a product line manager for the given session.

        @param actee      Instance of session
        """
        if not isinstance(actee, facade.models.Session):
            raise exceptions.InvalidActeeTypeException()

        try:
            if auth_token.user_id in actee.product_line.managers.values_list('id', flat=True):
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass

        # Now see if this session's session_template has the actor as a PLM
        try:
            if auth_token.user_id in actee.session_template.product_line.managers.values_list('id', flat = True):
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    #################################################################################
    #
    # Methods for which actee is a session_template
    #
    #################################################################################

    @classmethod
    def actor_is_product_line_manager_of_session_template(cls, auth_token, actee, *args, **kwargs):
        """
        Returns true if the actor is a product line manager for the given session_template

        @param actee      Instance of session_template
        """

        if not isinstance(actee, facade.models.SessionTemplate):
            raise exceptions.InvalidActeeTypeException()
        try:
            if auth_token.user_id in actee.product_line.managers.values_list('id',
                    flat = True):
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    #################################################################################
    #
    # Methods for which actee is a session_user_role_requirement
    #
    #################################################################################

    @classmethod
    def surr_is_of_a_particular_sur(cls, actee, session_user_role_id, *args, **kwargs):
        """
        Returns True iff the session_user_role associate with the actee is the same as the
        session_user_role specified by the parameter session_user_role.
        """
        if not isinstance(actee, facade.models.SessionUserRoleRequirement):
            raise exceptions.InvalidActeeTypeException()
        try:
            if int(actee.session_user_role.id) == int(session_user_role_id):
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    @classmethod
    def actor_owns_session_user_role_requirement(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True if the session associated with the session_user_role_requirement is owned
        by the actor
        """

        if not isinstance(actee, facade.models.SessionUserRoleRequirement):
            raise exceptions.InvalidActeeTypeException()

        try:
            the_session = actee.session
            if cls.actor_owns_session(auth_token, the_session):
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    #################################################################################
    #
    # Methods for which actee is a group
    #
    #################################################################################

    @classmethod
    def actor_is_group_manager(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True if the actor is the manager of the group.

        @param actee  Instance of a group
        """

        if not isinstance(actee, facade.models.Group):
            raise exceptions.InvalidActeeTypeException()
        try:
            if auth_token.user_id in actee.managers.values_list('id', flat=True):
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    @classmethod
    def actor_is_in_actee_which_is_a_group(cls, auth_token, actee, *args, **kwargs):
        """Returns true if the actee is a group and the actor is a member thereof."""

        if not isinstance(actee, facade.models.Group):
            raise exceptions.InvalidActeeTypeException()
        try:
            if actee.users.filter(id=auth_token.user_id).exists():
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False


    #################################################################################
    #
    # Methods for which actee is an organization
    #
    #################################################################################

    @classmethod
    def actor_is_in_actee_which_is_an_organization(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True if the actee is an Organization and the actor belongs to that
        organization.
        """

        if not isinstance(actee, facade.models.Organization):
            raise exceptions.InvalidActeeTypeException()
        if not isinstance(auth_token, facade.models.AuthToken):
            return False
        if actee.id in (x.id for x in auth_token.user.organizations):
            return True
        return False

    #################################################################################
    #
    # Methods for which actee is a payment
    #
    #################################################################################

    @classmethod
    def actor_owns_payment(cls, auth_token, actee, *args, **kwargs):
        """
        Returns true if the actor owns the payment.

        @param actee      Instance of a purchase_order
        """

        if not isinstance(actee, facade.models.Payment):
            raise exceptions.InvalidActeeTypeException()

        try:
            if auth_token.user_id == actee.purchase_order.user_id:
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    #################################################################################
    #
    # Methods for which actee is a product_line
    #
    #################################################################################

    @classmethod
    def actor_is_product_line_manager_of_product_line(cls, auth_token, actee, *args, **kwargs):
        """
        Returns true if the actor is a product line manager for the given product line.

        @param actee      Instance of product_line
        """

        if not isinstance(actee, facade.models.ProductLine):
            raise exceptions.InvalidActeeTypeException()

        if auth_token.user_id in actee.managers.values_list('id', flat = True):
            return True
        else:
            return False

    #################################################################################
    #
    # Methods for which actee is a purchase_order
    #
    #################################################################################

    @classmethod
    def purchase_order_has_payments(cls, auth_token, actee, *args, **kwargs):
        """
        Returns true if the purchase order being accessed has at least one payment.

        @param actee      Instance of a purchase_order
        """

        if not isinstance(actee, facade.models.PurchaseOrder):
            raise exceptions.InvalidActeeTypeException()

        return True if actee.payments.count() else False

    @classmethod
    def purchase_order_has_no_payments(cls, auth_token, actee, *args, **kwargs):
        """
        Returns true if the purchase order being accessed has no payments.

        @param actee      Instance of a purchase_order
        """

        if not isinstance(actee, facade.models.PurchaseOrder):
            raise exceptions.InvalidActeeTypeException()

        return False if actee.payments.count() else True

    @classmethod
    def actor_owns_purchase_order(cls, auth_token, actee, *args, **kwargs):
        """
        Returns true if the actor owns the purchase order being accessed.

        @param actee      Instance of a purchase_order
        """

        if not isinstance(actee, facade.models.PurchaseOrder):
            raise exceptions.InvalidActeeTypeException()

        try:
            if auth_token.user_id == actee.user_id:
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    #################################################################################
    #
    # Methods for which actee is a QuestionResponse
    #
    #################################################################################
    @classmethod
    def actor_owns_question_response(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True iff the QuestionResponse is for an ExamSession owned by the actor.
        """
        if not isinstance(actee, facade.models.Response):
            raise exceptions.InvalidActeeTypeException()
        try:
            return cls.actor_owns_assignment(auth_token, actee.exam_session)
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    #################################################################################
    #
    # Methods for which actee is a Task
    #
    #################################################################################
    @classmethod
    def actor_has_completed_task_prerequisites(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True iff the actor has completed all of the prerequisite tasks for the task being queried.
        """
        if not isinstance(actee, facade.models.Task):
            raise exceptions.InvalidActeeTypeException()
        try:
            if actee.prerequisites_met(auth_token.user):
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    @classmethod
    def actor_owns_assignment_for_task(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True iff actor owns an assignment for the given task.
        """

        if not isinstance(actee, facade.models.Task):
            raise exceptions.InvalidActeeTypeException()
        return facade.models.Assignment.objects.filter(\
            task__id=actee.id, user__id=auth_token.user_id).exists()

    #################################################################################
    #
    # Methods for which actee is a training_unit_authorization
    #
    #################################################################################

    @classmethod
    def actor_owns_training_unit_authorization(cls, auth_token, actee, *args, **kwargs):
        """
        Returns true if the actor owns the purchase order being accessed.

        @param actee      Instance of a purchase_order
        """

        if not isinstance(actee, facade.models.TrainingUnitAuthorization):
            raise exceptions.InvalidActeeTypeException()

        try:
            if auth_token.user_id == actee.user_id:
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    #################################################################################
    #
    # Methods for which actee is a User
    #
    #################################################################################

    @classmethod
    def actee_is_in_group_and_domain(cls, auth_token, actee, group_id, domain_id, *args, **kwargs):
        """
        If the actee is in the group, the method returns True iff they are also of the domain.
        If they are not in the group, it will return False.

        This is useful for making sure that participants who register themselves are
        in a particular domain, such as 'constantcontact.com' for the Constant Contact variant.

        Note that returning False instead of True if the user is not a part of
        the specified group is a different behavior from what the Constant
        Contact variant does!

        @param actee    The user object in question
        @type actee     user
        @param group_id The primary key of the group that the actee must be a member of
        @param domain_id the primary key of the domain
        """

        if not isinstance(actee, facade.models.User):
            raise exceptions.InvalidActeeTypeException()

        if group_id in actee.groups.all().values_list('id', flat=True):
            if actee.domain_affiliations.filter(domain__id=domain_id).count() == 0:
                return False # The user is in the group, but not the domain
            else:
                return True # The user is in the group and the domain, so let's allow

        return False

    @classmethod
    def actor_is_adding_allowed_many_ended_objects_to_user(cls, auth_token, actee, attribute_name, allowed_pks, update_dict, *args, **kwargs):
        """
        This is a strange new breed of auth_check that concerns itcls with the update_dict.  It ensures that the update_dict is only
        attempting to add items from the list of allowed primary keys to the attribute on the actee.  It will return false if any
        'remove' operation is in the dict, or if any primary key appears in the add list that is not in the allowed primary key list.

        @param auth_token       The authentication token of the acting user
        @type auth_token        auth_token
        @param actee            A user object that we are evaluation authorization for
        @type actee             user
        @param attribute_name   The attribute that we are authorizing the update call based on
        @type attribute_name    string
        @param allowed_pks      A list of primary keys that we will allow the actor to add to the actee's many ended attribute
        @type allowed_pks       list
        @param update_dict      The dictionary of changes that the actor is attempting to apply
                                to actee
        @type update_dict       dict
        @return                 A boolean of whether or not the actor will be allowed to run
                                the update call
        @raises                 InvalidActeeTypeException, AttributeNotInUpdateDictException
        """
        if not isinstance(actee, facade.models.User):
            raise exceptions.InvalidActeeTypeException()
        if attribute_name not in update_dict:
            raise exceptions.AttributeNotUpdatedException()
        current_pks = []
        for current_foreign_object in getattr(actee, attribute_name).all():
            current_pks.append(current_foreign_object.id)
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

    @classmethod
    def actor_actee_enrolled_in_same_session(cls, auth_token, actee, actor_sur_id, actee_sur_id, *args, **kwargs):
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
            raise exceptions.InvalidActeeTypeException()
        actee_sessions = set(facade.models.Session.objects.filter(
            session_user_role_requirements__assignments__user__id=actee.id,
            session_user_role_requirements__session_user_role__id=actee_sur_id
            ).values_list('id', flat=True))
        actor_sessions = set(facade.models.Session.objects.filter(
            session_user_role_requirements__assignments__user__id=auth_token.user_id,
            session_user_role_requirements__session_user_role__id=actor_sur_id
            ).values_list('id', flat = True))
        # The union of the two sets will be the set of sessions that they
        # are both enrolled in.  If this is not the empty set, then return True
        if actor_sessions & actee_sessions:
            return True
        return False

    @classmethod
    def actor_is_acting_upon_themselves(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True if the actor is a valid authenticated user in
        the system who is acting upon themselves.

        @param actee  A user object that we wish to compare the actor to
        """

        if not isinstance(actee, facade.models.User):
            raise exceptions.InvalidActeeTypeException()
        if auth_token.user_id == actee.id:
            return True
        return False

    @classmethod
    def actor_is_instructor_manager_of_actee(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True if the actor is the instructor manager for a product
        line in which the actee is an instructor.

        @param actee      A user object that we are evaluation authorization for
        """

        if not isinstance(actee, facade.models.User):
            raise exceptions.InvalidActeeTypeException()
        actee_product_lines_instructor_in = set(
            facade.models.ProductLine.objects.filter(
                instructors__id__exact=actee.id).values_list('id', flat=True))
        actor_product_lines_im_for = set(
            facade.models.ProductLine.objects.filter(
                instructor_managers__id__exact=auth_token.user_id
            ).values_list('id', flat = True))
        if actor_product_lines_im_for & actee_product_lines_instructor_in:
            return True
        return False

    @classmethod
    def actor_is_product_line_manager_of_user(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True if the actor is the product line manager for a
        product line in which the actee is an instructor.

        @param actee      A user object that we are evaluation authorization for
        """

        if not isinstance(actee, facade.models.User):
            raise exceptions.InvalidActeeTypeException()
        actee_product_lines_instructor_in = set(
            facade.models.ProductLine.objects.filter(
                instructors__id__exact=actee.id).values_list('id', flat=True))
        actor_product_lines_plm_for = set(
            facade.models.ProductLine.objects.filter(
                managers__id__exact=auth_token.user_id
            ).values_list('id', flat=True))
        if actor_product_lines_plm_for & actee_product_lines_instructor_in:
            return True
        return False

    #################################################################################
    #
    # Methods for which actee is a venue
    #
    #################################################################################

    @classmethod
    def actor_is_venue_creator(cls, auth_token, actee, *args, **kwargs):
        """
        Returns True if the actor is the user who created the venue, which is discovered by
        examining the venue's blame
        """
        if not isinstance(actee, facade.models.Venue):
            raise exceptions.InvalidActeeTypeException()
        try:
            if auth_token.user_id == actee.blame.user.id:
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    #################################################################################
    #
    # Methods for which actee is None
    #
    #################################################################################

    @classmethod
    def actor_is_authenticated(cls, auth_token, *args, **kwargs):
        """
        Returns True if the actor is an authenticated user in our system.

        @param actee  Not used by this method, and defaults to None
        """
        return not cls.actor_is_guest(auth_token)

    @classmethod
    def actor_is_guest(cls, auth_token=None, *args, **kwargs):
        """
        Returns True if the actor is a guest.

        @param actee  Not used by this method, and defaults to None
        """
        # Determine whether the actor is a guest or not, by testing to
        # see whether they are an authenticated user or not
        return not isinstance(auth_token, facade.models.AuthToken)

    @classmethod
    def actor_member_of_group(cls, auth_token, group_id, *args, **kwargs):
        """
        Returns True if the actor is a member of the specified group, False otherwise.

        @param actee      Not used by this method, but must be passed anyway as
                per authorization system requirements
        @param group_id   The primary key of the group we wish to test membership in
        """
        return facade.models.Group.objects.filter(id=group_id, users__id=auth_token.user_id).exists()

    @classmethod
    def actor_status_check(cls, auth_token, status, *args, **kwargs):
        """
        Returns True if the actor's status is equal to the specified status.

        @param actee    Not used by this method
        @type actee     user
        @param status   The status value that we want to know if the user has or not
        @type status    string
        @return         True if the actor's status is equal to the specified status, false otherwise.
        """
        return auth_token.user.status == status

    @classmethod
    def actor_is_anybody(cls, *args, **kwargs):
        """
        Returns True no matter what, which will work for both guests and authenticated users.
        """
        return True

    #################################################################################
    #
    # Methods for which actee is of a configurable type
    #
    #################################################################################
    @classmethod
    def actees_attribute_is_set_to(cls, actee, actee_model_name, attribute_name, attribute_value, *args, **kwargs):
        """
        This complicatedly name method exists to be a bit generically useful.  It will examine actee,
        ensuring that it is of type actee_model_name.  It will then ensure that attribute_name's value is
        equal to attribute_value.

        ** Note: This depends on the model class's (or at least its parent class) being in facade.models. **

        @param auth_token       The authentication token of the acting user.  Guests are allowed, and so this method does not use the auth_token
        @type auth_token        facade.models.AuthToken
        @param actee            The object in question
        @type actee             pr_models.PRModel
        @param actee_model_name The name of the type of the model that this check is supposed to be applied to
        @type actee_model_name  str
        @param attribute_name   The name of the attribute on actee that we want do perform a comparison on
        @type attribute_name    str
        @param attribute_value  The value that actee's attribute should be compared to
        @type attribute_value   Many types are allowed (string, boolean, int, etc.)
        """
        try:
            if not isinstance(actee, getattr(facade.models, actee_model_name)):
                raise exceptions.InvalidActeeTypeException()
            if getattr(actee, attribute_name) == attribute_value:
                return True
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

    @classmethod
    def actees_foreign_key_object_has_attribute_set_to(cls, auth_token, actee, actee_model_name, attribute_name, foreign_object_attribute_name,
            foreign_object_attribute_value):
        """
        This complicatedly name method exists to be a bit generically useful.  It will examine actee,
        ensuring that it is of type actee_model_name.  It will then follow a foreign key relationship,
        actee.foreign_object_attribute_name, and ensure that that attribute's value is equal to
        foreign_object_attribute_value.

        ** Note: This depends on the model class's (or at least its parent class) being in facade.models. **

        @param auth_token                       The authentication token of the acting user.  Guests are allowed, and so this method does not use the auth_token
        @type auth_token                        facade.models.AuthToken
        @param actee                            The object in question
        @type actee                             pr_models.PRModel
        @param actee_model_name                 The name of the type of the model that this check is supposed to be applied to
        @type actee_model_name                  str
        @param attribute_name                   The name of the attribute on actee that we can use to retrieve the foreign object
        @type attribute_name                    str
        @param foreign_object_attribute_name    The name of the attribute on actee that will lead us to the foreign object we care about
        @type foreign_object_attribute_name     str
        @param foreign_object_attribute_value   The value that the foriegn object's attribute should be compared to
        @type foreign_object_attribute_value    Many types are allowed (string, boolean, int, etc.)
        """
        try:
            if not isinstance(actee, getattr(facade.models, actee_model_name)):
                raise exceptions.InvalidActeeTypeException()
            foreign_object = getattr(actee, attribute_name)
            return cls.actees_attribute_is_set_to(auth_token, foreign_object, foreign_object.__class__.__name__, foreign_object_attribute_name,
                foreign_object_attribute_value)
        except ObjectDoesNotExist:
            pass
        except AttributeError:
            pass
        return False

# vim:tabstop=4 shiftwidth=4 expandtab
