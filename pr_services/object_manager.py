"""
This module contains an abstract base class for classes that manage persistent
objects in the Power Reg 2 system, also known as object managers.

It also includes 2 classes for building views over object manager data. These
are CensoredView and UncensoredView.
"""
__docformat__ = "restructuredtext en"

import abc
import re

from abc import abstractmethod
from operator import itemgetter
from collections import Sequence, Set

try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict


from django.db.models import Q
from django.db.models.fields import FieldDoesNotExist
from django.db.models.fields.related import RelatedField, RelatedObject
from django.db.models.query import ValuesQuerySet

import exceptions
import facade
import logging
import pr_time
import settings
import tagging.models
import pyamf
from pyamf.adapters import util

from pr_services.rpc.service import service_method
from utils import Utils

__all__ = ('ObjectManager', 'CensoredView', 'UncensoredView')

class ObjectManagerMetaclass(abc.ABCMeta):
    """
    Metaclass for ObjectManager subclasses to merge getters/setters
    from base classes.
    """
    def __new__(cls, name, bases, attrs):
        setters, getters = {}, {}
        for base in bases:
            if hasattr(base, 'SETTERS'):
                setters.update(base.SETTERS)
            if hasattr(base, 'GETTERS'):
                getters.update(base.GETTERS)

        if 'SETTERS' in attrs:
            setters.update(attrs['SETTERS'])
        if 'GETTERS' in attrs:
            getters.update(attrs['GETTERS'])

        # allow subclasses to remove accessors
        def filter_removed(d):
            for k, v in d.items():
                if not v: del d[k]

        filter_removed(setters)
        filter_removed(getters)

        # check that the getters/setters are valid
        for attribute, getter in getters.iteritems():
            if not hasattr(facade.subsystems.Getter, getter):
                raise AttributeError("Invalid getter '%s' for attribute '%s'"
                        " in %s" % (getter, attribute, name))
        for attribute, setter in setters.iteritems():
            if not hasattr(facade.subsystems.Setter, setter):
                raise AttributeError("Invalid setter '%s' for attribute '%s'"
                        " in %s" % (setter, attribute, name))

        attrs.update(GETTERS=getters, SETTERS=setters)
        return super(ObjectManagerMetaclass, cls).__new__(cls, name, bases, attrs)


class ObjectManager(object):
    """Manage Power Reg persistent objects.

    Abstract base class for classes that manage persistent objects in the
    Power Reg 2 system.

    """
    __metaclass__ = ObjectManagerMetaclass

    #: Dictionary of attribute names and the names of functions used to set them
    SETTERS = {
        'notes': 'set_many'
    }

    #: Dictionary of attribute names and the names of functions used to get them
    GETTERS = {
        'id': 'get_general',
        'notes': 'get_many_to_many',
        'content_type': 'get_content_type',
        'create_timestamp': 'get_time',
        'save_timestamp': 'get_time'
    }


    def __init__(self):
        """ constructor """
        #: Sometimes we do nested iterations, such as going through a list of users, and
        #: for each one, figuring out which groups they belong to.  It's helpful to
        #: cache the relationship data here so don't have to fetch it again for each user.
        self.cache = {}
        self.authorizer = facade.subsystems.Authorizer()
        self.logger = logging.getLogger(self.__module__)
        self.blame = None

    @service_method
    def update(self, auth_token, id, value_map):
        """
        Update a Power Reg persistent object

        :param id: Primary key for the object to update.
        :type id: int
        :param value_map: A map attributes to update and their new values.
                For a "many" end of a relationship, you may
                provide a list of foreign keys to be added, or
                you may provide a struct with two lists of keys
                indexed as 'add' and 'remove'.
        :type value_map: dict
        """

        pr_persistent_object = self._find_by_id(id)
        facade.subsystems.Setter(auth_token, self, pr_persistent_object, value_map)
        pr_persistent_object.save()

        return pr_persistent_object

    @service_method
    def delete(self, auth_token, pr_object_id):
        """
        Delete a Power Reg persistent object

        :param auth_token: The authentication token of the acting user
        :type auth_token: pr_services.models.AuthToken
        :param pr_object_id:  The primary key of the object to be deleted
        """

        object_to_be_deleted = self._find_by_id(pr_object_id)
        self.authorizer.check_delete_permissions(auth_token, object_to_be_deleted)
        object_to_be_deleted.delete()

    def _find_by_id(self, id, model_class=None):
        """
        Find a persistent object by primary key.

        :param id:  primary key of the object
        :param model_class:

               the model class of the object - None means to
               use the default Django model for this object manager class (which
               is specified in the self.my_django_model attribute)
        """

        if not model_class:
            return Utils.find_by_id(id, self.my_django_model)
        else:
            return Utils.find_by_id(id, model_class)

    @service_method
    def get_filtered(self, auth_token, filters=None, field_names=None):
        """
        Get Power Reg persistent objects filtered by various limits::

            Index values for filter structs:

              and                    Does a boolean and of a list of additional query dictionaries
              or                     Does a boolean or of a list of additional query dictionaries
              not                    Does a negation of a single query dictionary
              exact                  Exact match
              iexact                 Case-insensitive exact match
              greater_than           Greater Than
              less_than              Less Than
              greater_than_or_equal  Greater Than Or Equal
              less_than_or_equal     Less Than Or Equal
              begins                 Begins With
              ibegins                Case-insensitive begins with
              ends                   Ends With
              iends                  Case-insensitive ends with
              contains               Contains
              icontains              Case-insensitive contains
              range                  Within a range (pass beginning and ending points as an array)
              member                 Like SQL "IN", must be a member of the given list

        :param auth_token:
        :type auth_token: unicode
        :param filters:

                A struct of structs indexed by filter name. Each filter's
                struct should contain values indexed by field names.
        :type filters: dict
        :param field_names:

                Optional list of strings which specify the field names to return.
                Default is to return only the ids of the objects.  In fact, ids are
                always returned as long as the actor has permission to see them, so
                it is never necessary to ask for them, even though it also doesn't
                harm anything to ask (save a tiny bit of bandwidth).

        :type field_names: list
        """
        result = self.Filter(self)._filter_common(auth_token, filters, field_names)
        # Convert any instances of a ValuesQuerySet in the result dictionaries
        # into a normal Python list so it can be marshalled for RPC.
        for row in result:
            for key in row:
                if isinstance(row[key], ValuesQuerySet):
                    row[key] = list(row[key])
        return result

    class Filter:
        """
        The Filter Class
        """

        def __init__(self, my_manager):
            """ constructor """

            self.my_manager = my_manager
            self.handlers = {
                'exact': self._handle_endpoint,
                'greater_than' : self._handle_endpoint,
                'greater_than_or_equal' : self._handle_endpoint,
                'less_than' : self._handle_endpoint,
                'less_than_or_equal' : self._handle_endpoint,
                'range' : self._handle_range,
            }

        operators = {
            'exact' : 'exact',
            'iexact' : 'iexact',
            'greater_than' : 'gt',
            'less_than' : 'lt',
            'greater_than_or_equal' : 'gte',
            'less_than_or_equal' : 'lte',
            'begins' : 'startswith',
            'ibegins' : 'istartswith',
            'ends' : 'endswith',
            'iends' : 'iendswith',
            'contains' : 'contains',
            'icontains' : 'icontains',
            'range' : 'range',
            'member' : 'in',
        }

        boolean_operators = ('and', 'or', 'not')

        tag_operators = ('tag_union', 'tag_intersection')

        def _handle_endpoint(self, arg):
            """
            This determines if the endpoint of a 'greater_than' or 'less_than' fitler is temporal, and if so, converts the endpoint from
            ISO8601 string to a python datetime instance.

            :param arg: string value of the filter
            """
            if isinstance(arg, basestring) and pr_time.is_iso8601(arg):
                return pr_time.iso8601_to_datetime(arg).replace(tzinfo=pr_time.UTC())
            else:
                return arg

        def _handle_range(self, range_arg):
            """
            Handle_range

            This determines if a range is temporal, and if so, converts the endpoints from
            ISO8601 strings to python datetime objects

            :param range_arg: argument of the form [start, end] to give
                to the Django range filter operator
            """

            if len(range_arg) != 2 or type(range_arg[0]) != type(range_arg[1]):
                raise exceptions.RangeTakesTwoArgsException()

            if pr_time.is_iso8601(range_arg[0]) and pr_time.is_iso8601(range_arg[1]):
                ret = []
                for timestamp in range_arg:
                    ret.append(pr_time.iso8601_to_datetime(timestamp))
                return ret
            else:
                return range_arg

        def _filter_common(self, auth_token, filters=None, field_names=None):
            """
            Get objects filtered by various limits
            """

            if field_names is None:
                field_names = []

            if filters:
                query = self.construct_query(filters)
                query_set = self.my_manager.my_django_model.objects.filter(query)
            else:
                query_set = self.my_manager.my_django_model.objects.all()

            return facade.subsystems.Getter(auth_token, self.my_manager, query_set, field_names).results

        def validate_field_name_path(self, filter_dict, field_name_path):
            """
            Make sure that a path of field names is valid.  Raises an exception if not valid.

            :param filter_dict: the filter dictionary sent by the user (needed for exception handling)
            :type filter_dict: dict
            :param field_name_path: the field name path, made by splitting the field name around occurrences of '__'
            :type field_name_path: list
            """

            assert len(field_name_path) >= 2

            current_class = self.my_manager.my_django_model
            current_path = None
            for attribute_name in field_name_path[0:-1]:
                if not attribute_name:
                    raise exceptions.InvalidFilterException(filter_dict,
                        ('unrecognized attribute name [%s], path so far [%s]' %
                            (str(attribute_name), str(current_path))
                        ))
                if not current_path:
                    current_path = attribute_name
                else:
                    current_path += '__' + attribute_name

                try:
                    related_field = current_class._meta.get_field_by_name(attribute_name)
                except FieldDoesNotExist:
                    raise
                if isinstance(related_field[0], RelatedField):
                    current_class = related_field[0].rel.to
                elif isinstance(related_field[0], RelatedObject):
                    current_class = related_field[0].model
                else:
                    raise exceptions.InvalidFilterException(filter_dict,
                        'unable to resolve related object reference %s' % current_path)

            try:
                last_field = current_class._meta.get_field_by_name(field_name_path[-1])
            except FieldDoesNotExist:
                raise exceptions.InvalidFilterException("unable to resolve field name [%s]" %
                    string.join(field_path, '__'))

        def construct_query(self, filter_dict):
            """
            construct a query based on a dictionary
            """
            ## handle boolean operators first, using recursion to apply them ##

            if ('and' in filter_dict) or ('or' in filter_dict) or ('not' in filter_dict):
                if len(filter_dict) != 1:
                    raise exceptions.InvalidFilterException(filter_dict,
                        'more than one top-level key with a boolean operator')
                operator = filter_dict.keys()[0]
                operand = filter_dict[operator]
                if (operator == 'and' or operator == 'or') and not \
                    (isinstance(operand, list) or isinstance(operand, tuple)):

                    raise exceptions.InvalidFilterException(filter_dict,
                        'invalid operand -- expected a list or tuple')

                if (operator == 'and' or operator == 'or') and len(operand) < 1:
                    raise exceptions.InvalidFilterException(filter_dict,
                        "invalid operand -- boolean 'and' and 'or' require an iterable with at least one element")

                if operator == 'not' and not isinstance(operand, dict):
                    raise exceptions.InvalidFilterException(filter_dict,
                        'invalid operand -- expected a dictionary')

                if operator == 'and' or operator == 'or':
                    accumulated_query = self.construct_query(operand[0])
                    for additional_query in operand[1:]:
                        if operator == 'and':
                            accumulated_query = accumulated_query & self.construct_query(additional_query)
                        elif operator == 'or':
                            accumulated_query = accumulated_query | self.construct_query(additional_query)
                    return accumulated_query
                elif operator == 'not':
                    return ~(self.construct_query(operand))

            ## handle tag filters if present ##

            # make sure that we only have only one tag operator if we have any
            number_of_tag_operators = 0
            for op in filter_dict:
                if op in self.tag_operators:
                    number_of_tag_operators += 1
            if number_of_tag_operators > 1:
                raise exceptions.InvalidFilterException(
                    'no more than one tag operator is allowed')

            if number_of_tag_operators == 1:
                if len(filter_dict) > 1:
                    raise exceptions.InvalidFilterException(
                        'No other filters are allowed with a tag operation.  You should' +\
                        ' probably use Boolean expressions.')
                tag_union_operand = None
                tag_intersection_operand = None
                if 'tag_union' in filter_dict:
                    tag_union_operand = filter_dict['tag_union']
                elif 'tag_intersection' in filter_dict:
                    tag_intersection_operand = filter_dict['tag_intersection']
                if tag_union_operand is not None:
                    query_set = tagging.models.TaggedItem.objects.get_union_by_model(
                        self.my_manager.my_django_model,
                        tag_union_operand)
                elif tag_intersection_operand is not None:
                    query_set = tagging.models.TaggedItem.objects.get_by_model(
                        self.my_manager.my_django_model,
                        tag_intersection_operand)
                pk_list = list()
                for obj in query_set:
                    pk_list.append(obj.id)
                return Q(id__in=pk_list)

            # recursion base case -- no boolean operator present in top-level of operators

            #: Dictionary of filter arguments that will be passed to django.
            #: for example, {'start__gte' : '2008-06-12', 'end__lte' : '2008-06-13'} would
            #: be used to construct a filter call like this:
            #:    <your_model>.objects.filter(start__gte = '2008-06-12', end__lte = '2008-06-13')
            #:
            #: See django's database API docs on filtering for the specifics.
            django_filter_arguments = {}
            for operator in filter_dict:
                if (operator in self.operators) and isinstance(filter_dict[operator], dict):
                # If we support this filter operator and have at least one value on which to filter...
                    # For each field name on which we are filtering...
                    for field_name in filter_dict[operator].keys():
                        if field_name.find('__') != -1:
                            field_name_path = field_name.split('__')
                            self.validate_field_name_path(filter_dict, field_name_path)

                        new_arg = filter_dict[operator][field_name] # We will mangle this.

                        # If we have a special handler for this operator, apply it.
                        if operator in self.handlers:
                            new_arg = self.handlers[operator](new_arg)

                        # construct the name of the argument to pass to django's filter method
                        # (e.g. 'id__exact')
                        django_filter_arg_name = str(field_name) + '__' + str(self.operators[operator])

                        # construct a dictionary mapping names of arguments to pass to the
                        # django filter method with their values, like {'id__exact':'1'}.
                        # See comments a few lines above after the definition of the
                        # local django_filter_arguments variable for more details.
                        django_filter_arguments[django_filter_arg_name] = new_arg
                else:
                    # We weren't given a valid operator.
                    raise exceptions.InvalidFilterOperatorException(operator)

            # the ** operator expands a dictionary to a series of named arguments
            query = Q(**django_filter_arguments)
            return query

    def _get_blame(self, auth_token):
        """
        looks for a cached blame and returns it if one exists. If not, returns
        a new blame (but does not cache the new one!). Service methods that
        wish to cache a blame are responsible for removing it at the end of
        the call.
        """

        if self.blame is None:
            return facade.managers.BlameManager().create(auth_token)
        else:
            return self.blame

    @service_method
    def check_exists(self, auth_token, field_name, value):
        """
        Check for the existence of `value` in the model field named
        `field_name`. Returns True if a value exists (the value is not unique),
        and False otherwise.
        """

        params = {field_name: value}
        try:
            self.authorizer.check_update_permissions(auth_token,
                    self.my_django_model, params)
        except exceptions.PermissionDeniedException:
            self.authorizer.check_create_permissions(auth_token,
                    self.my_django_model)

        return self.my_django_model.objects.filter(**params).exists()

    def build_view(self, censored=True, *args, **kwargs):
        """
        Helper for subclasses to create consistent views using a
        micro view building API. This method transparently passes arguments
        to View.__init__. See the documentation for View.__init__ for more
        details.

        An example of how a subclass might implement this helper to construct
        views is as follows:

        @service_method
        def some_complicated_view(self, auth_token, *args, **kwargs):
            view = self.build_view(
                fields=('name', 'title', 'description', 'passing_score'),
                merges=(
                    ('achievements',
                        ('name', 'description')),
                    ('task_fees',
                        ('name', 'price')),
                    ('prerequisite_tasks',
                        ('name', 'description', 'title', 'type'))
                )
            )
            return view(auth_token, *args, **kwargs)

        Arguments:
            censored: True if the returned view should censor the result rows
                      using the authorizer (similar to
                      ObjectManager.get_filtered). False otherwise.
        """
        view_impl = CensoredView if censored else UncensoredView
        return view_impl(self, *args, **kwargs)


class ViewTransformation(object):
    """
    Abstract class representing a view result transformation.

    This class represents the abstract form of an algorithm which applies
    some transformation to a view result such as a merge. The result is a
    list of dictionaries.

    Transformation classes work using a strategy-pattern where each
    class defines its tranformation algorithm using __call__ which accepts
    a result list as an argument.
    """
    __metaclass__ = abc.ABCMeta

    def __init__(self, view):
        self.view = view

    @abstractmethod
    def __call__(self, result):
        """
        An abstract method which is implemented by subclasses to define the
        tranformation algorithm applied to the view result.

        Arguments:
            result: The view result which is a list of dictionaries
                    as returned by `Getter`.

        Returns:
            The view result, a list of dictionaries.
        """
        pass


class Merge(ViewTransformation):
    """
    Abstract class representing a merge tranformation for view results.


    A merge replaces foreign key field values in view result row with a
    dictionary of values from the foreign object. Passing a
    `final_type_name` implies that the foreign object must
    be downcasted before accessing the object's fields.
    """
    def __init__(self, view, foreign_key, final_type_name, fields):
        """
        Base Merge Constructor

        Arguments:
            view: An instance of a View object
            foreign_key: A string for the name of the foreign key
                         field which will be used for the merge.
            final_type_name: A string of the final type for the foreign
                             object represented by foreign key.
            fields: A sequence of strings representing field names to include
                    from the foreign object.
        """
        super(Merge, self).__init__(view)
        self.foreign_key = foreign_key
        self.final_type_name = final_type_name
        self.fields = set(fields)

    def __repr__(self):
        type_name = '.%s' % self.final_type_name if self.final_type_name else ''
        fields = ','.join(self.fields)
        return '%s%s: (%s)' % (self.foreign_key, type_name, fields)

    @property
    def foreign_model(self):
        """
        Returns the Django model object that corresponds to the foreign_key
        being merged. The foreign_key is relative to the model object for the
        view's manager.
        """
        model = self._get_related_model(self.foreign_key)
        if self.final_type_name:
            model = getattr(model, self.final_type_name).related.model
        return model

    ##
    # helper methods

    def _get_foreign_objects(self, manager, ids):
        """
        Performs a query for foreign objects to be merged. The result of
        the raw query is converted into a dictionary mapping from foreign_key
        values (ids) to rows. ie. { [foreign key id] -> foreign object }

        This also helps decrease the memory footprint for huge results as the
        initial list (which is no longer used after converting to a
        dictionary) can be garbage-collected after this function.
        """
        result = self.view._query(manager, Q(id__in=ids), self.fields)
        foreign_objects = {}
        for row in result:
            foreign_objects[row['id']] = row
        return foreign_objects

    @staticmethod
    def _get_model_manager(model_object):
        # infer the manager from a model object and return the manager class
        manager_name = '%sManager' % model_object.__name__
        return getattr(facade.managers, manager_name)

    def _get_related_model(self, foreign_key):
        # takes the name of a field which exists on the
        # view manager object and returns the model object for the field.
        model = self.view.manager.my_django_model
        field = model._meta.get_field_by_name(foreign_key)[0]
        if isinstance(field, RelatedObject):
            return field.model
        if isinstance(field, RelatedField):
            return field.rel.to
        else:
            raise ValueError("merge field %s must be a relation" % foreign_key)


class FlatMerge(Merge):
    """
    A basic merge algorithm which operates on every row of a view result by
    replacing an integer or list of integers (representing foreign key values)
    with a dictionary of key-value pairs of the foreign object's fields.

    See Utils.merge_queries for similar functionality.
    """
    def _get_foreign_key_values(self, result):
        # Collect a set of values (ids) for the foreign key
        # from the current result
        values = set()
        for row in result:
            value = row.get(self.foreign_key, None)
            if not value:
                continue
            if isinstance(value, (int, long)):
                values.add(value)
            else:
                values.update(value)
        return values

    def _process_merge(self, result, foreign_objects):
        """
        Internal routine which completes the merge by iterating through the
        current result replacing foreign key values with a dictionary of
        fields from the foreign object.
        """
        for row in result:
            value = row.get(self.foreign_key, None)
            if not value:
                continue

            if isinstance(value, (Sequence, ValuesQuerySet)):
                row[self.foreign_key] = []
                for id in value:
                    d = foreign_objects.get(id, None)
                    if not d:
                        d = {'id': id}
                    row[self.foreign_key].append(d)
            elif not isinstance(value, dict):
                # XXX: it is possible for a result set to contain duplicate
                # dicts when two rows reference the same foreign key in
                # which case we may have already substituted the value with a
                # dictionary.
                # (see github issue #94)
                d = foreign_objects.get(value, None)
                if not d:
                    d = {'id': value}
                row[self.foreign_key] = d
        return result


    def __call__(self, result):
        # grab a list of ids for the foreign objects
        ids = self._get_foreign_key_values(result)

        # get the manager for the foreign object
        manager = self._get_model_manager(self.foreign_model)()
        foreign_objects = self._get_foreign_objects(manager, ids)

        return self._process_merge(result, foreign_objects)


class NestedMerge(Merge):
    """
    A nested merge algorithm which works similarly to FlatMerge but operates
    within a dictionary created by a FlatMerge. This means that a FlatMerge
    must be performed first on the foreign_key after which the nested merge
    can happen on the inner key.

    A nested merge is useful for efficiently getting fields from an object when
    two levels of indirection are invovled.
    """
    def __init__(self, view, foreign_key, final_type_name, inner_key, fields):
        """
        NestedMerge Constructor

        Arguments:
            view: An instance of a View object
            foreign_key: A string for the name of the foreign key
                         field which will be used for the merge.
            final_type_name: A string of the final type for the foreign
                             object represented by foreign key.
            inner_key: A string name of the foreign key which exists on
                       the foreign object pointed to by `foreign_key`.
            fields: A sequence of strings representing field names to include
                    from the foreign object.
        """
        super(NestedMerge, self).__init__(view, foreign_key,
                final_type_name, fields)
        self.inner_key = inner_key

    def _get_foreign_key_values(self, result):
        """
        Collect a set of id values for the inner foreign key
        from the current result.
        """
        values = set()
        for row in result:
            outer = row.get(self.foreign_key, None)
            if not outer:
                continue
            value = outer.get(self.inner_key, None)
            if not value:
                continue
            if isinstance(value, (int, long)):
                values.add(value)
            else:
                values.update(value)
        return values

    def _process_merge(self, result, foreign_objects):
        """
        Internal routine which completes the merge by iterating over the
        view result which at this point has been processed by the requisite
        FlatMerge. Each foreign object is merged into the existing dictionary
        (created by the FlatMerge).
        """
        for row in result:
            outer = row.get(self.foreign_key, None)
            if not outer:
                continue
            value = outer.get(self.inner_key, None)
            if not value:
                continue
            if isinstance(value, (Sequence, ValuesQuerySet)):
                outer[self.inner_key] = []
                for id in value:
                    d = foreign_objects.get(id, None)
                    if not d:
                        d = {'id': id}
                    outer[self.inner_key].append(d)
            elif not isinstance(value, dict):
                # XXX: it is possible for a result set to contain duplicate
                # dicts when two rows reference the same foreign key in
                # which case we may have already substituted the value with a
                # dictionary.
                # (see github issue #94)
                d = foreign_objects.get(value, None)
                if not d:
                    d = {'id': value}
                outer[self.inner_key] = d
        return result

    def __call__(self, result):
        # determine the model for the nested foreign key
        inner_field = self.foreign_model._meta.get_field_by_name(self.inner_key)[0]
        assert isinstance(inner_field, RelatedField)

        # get the manager for the nested foreign object model
        manager = self._get_model_manager(inner_field.rel.to)()

        # get a list of foreign object ids and query for the objects
        ids = self._get_foreign_key_values(result)
        foreign_objects = self._get_foreign_objects(manager, ids)

        return self._process_merge(result, foreign_objects)


def limit_slice(limit):
    """
    Create a Python slice object from an integer or tuple representing the
    bound of a query result. If `limit` is an integer, it represents the maximum
    number of results to return. If `limit` is a tuple, it represents a page
    number and the number of results per page respectively.
    """
    if isinstance(limit, slice):
        return limit

    if not limit or isinstance(limit, (int, long)):
        page, results_per_page = 1, limit or settings.MAX_QUERY_RESULTS
    else:
        page, results_per_page = limit

    if results_per_page > settings.MAX_QUERY_RESULTS:
        results_per_page = settings.MAX_QUERY_RESULTS

    page -= 1
    if page < 0:
        raise ValueError("page number must be greater than 0")
    if results_per_page < 1:
        raise ValueError("number of results per page must be greater than 0")

    pos = page * results_per_page
    return slice(pos, pos + results_per_page)


class View(Sequence):
    """Abstract Base class for creating PR object views.

    Views can automatically perform flat or nested merges. Merges are specified
    by passing a foreign key, using a special format, along with fields that
    should be present in merged dictionary representing the foreign object.

    When creating a merge, the foreign key is specified as a string. It
    represents the attribute name for a foreign key field on the model object
    for the view. For downcasting a foreign object due to inheritence, a
    `final_type_name` can be specified by adding a colon ':' character, followed
    by the model object's final type name. This is useful for merging fields
    when the fields are only present on a subclass.

    Example:
    v = CensoredView(assignment_manager,
        merges=(
            ('task:filedownload', # cast to file download to access file_size
                ('file_size', 'name')),
        ))

    For a nested merge, the foreign key can be followed by a period and the
    name of an attribute on the foreign object which represents a second
    foreign key (the inner or nested key).

    The following example will merge in the name and description for task
    achievements for assignments with file download task objects.

    v = CensoredView(assignment_manager,
        merges=(
            ('task:filedownload.achievements',
                ('name', 'description')),
        ))
    """
    __metaclass__ = abc.ABCMeta

    _merge_key_info = itemgetter('foreign_key', 'final_type_name', 'inner_key')
    _merge_key_pattern = re.compile('''
    ^(?P<foreign_key>[a-z_]+)
    (:(?P<final_type_name>[a-z _-]+))?
    (\.(?P<inner_key>[a-z_]+))?
    $''', re.IGNORECASE | re.VERBOSE)

    @classmethod
    def _parse_merge_key(cls, key):
        # This is a helper which parses the custom string format used when
        # specifying a foreign key to merge. It returns a 3-tuple of strings for
        # the foreign_key, final_type and inner_key
        key = key.strip().lower()
        m = cls._merge_key_pattern.match(key)
        if not m:
            raise ValueError("invalid merge key '%s'" % key)
        d = m.groupdict()
        final_type_name = d['final_type_name']
        if final_type_name:
            d['final_type_name'] = final_type_name.translate(None, ' -_')
        return cls._merge_key_info(d)

    def __init__(self, manager, filters=None, fields=(), merges=(),
            order=None, limit=None):
        """
        Base View Constructor

        Arguments:
            manager: An ObjectManager instance
            filters: A mapping of filters which may be overridden by
                     caller filters. See ObjectManager.Filter
            fields: A sequence or set of field to include in the view by default
            merges: an optional sequence of 2-tuples indicating the merges to
                    perform. Each 2-tuple should contain the name of the
                    foreign key field, and a tuple of additional fields
                    respectively.
            order: A tuple of strings for field names to order by. For more
                   details See Django QuerySet.order_by.
            limit: A 2-tuple containing the page number and number of results
                   per page respectively.
        """
        self.manager = manager
        self.fields = set(fields)
        self.filters = filters or {}
        self.merges = list(merges)
        self.order = order
        self.limit = limit_slice(limit)

        self._result = None # cached result
        self._merges = None # compiled merge strategy

    ##
    # Sequence API
    def __iter__(self):
        return iter(self.result)

    def __len__(self):
        return len(self.result)

    def __getitem__(self, index):
        return self.result[index]

    def __repr__(self):
        return repr(self.result)

    def __call__(self, filters=None, fields=(), order=None, limit=None):
        """
        Create a new view with caller parameters bound to the original view.

        Arguments:
            filters: A mapping of filters which may override the default filters
                    of the view. See ObjectManager.Filter.construct_query for
                    the semantics of the mapping.
            fields: A sequence or set of fields to include in the view in
                    addition to the view defaults.
            order: A tuple of strings for field names to order by. For more
                   details See Django QuerySet.order_by.
            limit: An integer representing the maximum number of rows to return
                   or a 2-tuple containing the page number and number of results
                   per page respectively.

        Returns:
            A new view with caller parameters bound to the original view.
        """
        assert not filters or isinstance(filters, dict)
        assert not fields or isinstance(fields, (list, tuple, set, frozenset))

        if not (filters or fields or order or limit):
            return self

        if not fields:
            fields = set(self.fields)
        elif not isinstance(fields, Set):
            fields = self.fields | set(fields)
        else:
            fields = self.fields | fields

        filters = filters or self.filters
        order = order or self.order
        limit = limit or self.limit
        view = self.__class__(
                manager=self.manager,
                filters=filters,
                fields=fields,
                merges=self.merges,
                order=order,
                limit=limit)
        # dont recompile the merges
        if self._merges:
            view._merges = self._merges
        return view

    def _build_and_optimize_merges(self):
        # this method basically combines merges with the same foreign key
        # and ensures that the proper requisite merges and fields
        # exist in the view
        if self._merges:
            return self._merges

        merges = OrderedDict()
        for key, fields in self.merges:
            foreign_key, final_type_name, inner_key = self._parse_merge_key(key)
            # check if we already have an equivalent merge
            key = (foreign_key, inner_key)
            merge = merges.get(key, None)
            if merge:
                if (not merge.final_type_name or
                        merge.final_type_name == final_type_name):
                    # upgrade final type and add more fields
                    merge.final_type_name = final_type_name
                    merge.fields.update(fields)
                    continue
                else:
                    raise ValueError("type '%s' inconsistent with "
                            "previous type '%s' for foreign key '%s'" % (
                                final_type,
                                merge.final_type_name,
                                foreign_key))

            # make sure the foreign key exists in the initial result
            self.fields.add(foreign_key)
            if not inner_key:
                merges[key] = FlatMerge(self,
                        foreign_key, final_type_name, fields)
                continue

            # the presence of an inner_key denotes a nested merge
            # make sure an outer merge exists to support the nested merge
            outer_key = (foreign_key, None)
            merge = merges.get(outer_key, None)
            if merge:
                # outer merge exists, upgrade the type and add the inner_key
                if (not merge.final_type_name or
                        merge.final_type_name == final_type_name):
                    merge.final_type_name = final_type_name
                    merge.fields.add(inner_key)
                else:
                    raise ValueError("type '%s' inconsistent with "
                            "previous type '%s' for foreign key '%s'" % (
                                final_type_name,
                                merge.final_type_name,
                                foreign_key))
            else:
                # create the requisite outer merge
                merges[outer_key] = FlatMerge(self,
                        foreign_key, final_type_name, (inner_key,))

            # create the nested merge
            merges[key] = NestedMerge(self,
                    foreign_key, final_type_name, inner_key, fields)

        self._merges = merges
        return self._merges

    def _reset(self):
        # clears cached results and compiled merges
        self._merges = None
        self._result = None

    @property
    def result(self):
        """
        Evaluates the result of the view with all filtering and
        transformations performed.

        Returns:
            A list of dictionaries representing the objects in the view.
        """
        if self._result:
            return self._result

        qfilter = ObjectManager.Filter(self.manager)
        query = qfilter.construct_query(self.filters)
        merges = self._build_and_optimize_merges().values()
        # this is an a bit of a hack//optimization
        # to filter the initial result set when subsequent merges
        # require a foreign key to be downcasted
        for merge in merges:
            if merge.final_type_name and isinstance(merge, FlatMerge):
                final_type_name = merge.foreign_model._meta.verbose_name
                lvalue = '%s__final_type__name' % merge.foreign_key
                query &= Q(**{lvalue: final_type_name})

        result = self._query(self.manager, query, self.fields,
                self.order, self.limit)

        # perform merge transformations
        for merge in merges:
            result = merge(result)
            if not result:
                break

        self._result = result
        return result

    def merge(self, *args):
        """
        Merge fields from an object referenced by a foreign key.

        A typical query will return foreign key values as integers.
        When additional fields from a foreign object are required, this method
        can help perform the merge as part of the view.

        As an example, say you want to create a view over users and their
        organizations with additional information about the organization.

        view = CensoredView(user_manager,
            fields=('first_name', 'last_name'))
        view.merge('organizations', ('name', 'email'))

        This can also be done in the constructor:

        view = CensoredView(user_manager,
            fields=('first_name', 'last_name'),
            merges=(('organizations', ('name', 'email')),))
        """
        assert args
        if isinstance(args[0], basestring):
            self.merges.append(args)
        else:
            for item in args:
                self.merges.append(item)
        self._reset()
        return self

    @abstractmethod
    def _query(self, manager, query, fields, order=None, limit=None):
        """
        Defines how the view will perform a query. It can be overriden
        in subclasses to modify the results which are returned.

        All tranformations perform queries through the view so this applies
        not only the the initial view query, but all queries performed in the
        process of building the view.

        Arguments:
            manager: A manager object for the type of object being queried.
            query: A Django QuerySet object or a dictionary of filters which can
                   be converted into a Django QuerySet by ObjectManager.Filter.
            fields: A sequence of fields which will be read from the resulting
                    objects in each row.
            order: A tuple of fields which specify the query result ordering.
            limit: A python slice object representing the upper/lower bound of
                   the query result.

        Returns:
            A Django QuerySet object, however this may be different in
            subclasses.
        """
        if isinstance(query, dict):
            qfilter = ObjectManager.Filter(manager)
            query = qfilter.construct_query(query)
        if not isinstance(limit, slice):
            limit = limit_slice(limit)
        model = manager.my_django_model
        result = model.objects.all()
        if query:
            result = result.filter(query)
        if order:
            result = result.order_by(*order)
        if limit:
            result = result[limit]
        return result


class UncensoredView(View):
    """
    Facilitates creating more complex uncensored views which completely
    bypass the authorizer for cases where the proper access has already been
    authorized and no result filtering is required.
    """

    def _query(self, manager, query, fields, order=None, limit=None):
        """
        Performs an uncensored query required to build the view result or
        perform associated transformations. The authorizer is not used to
        filter results from the raw Django query. It is assumed that all
        required authorization has occured by this point.

        Arguments:
            manager: A manager object for the type of object being queried.
            query: A Django QuerySet object or a dictionary of filters which can
                   be converted into a Django QuerySet by ObjectManager.Filter.
            fields: A sequence of fields which will be read from the resulting
                    objects.
            order: A tuple of fields which specify the query result ordering.
            limit: A python slice object representing the upper/lower bound of
                   the query result.

        Returns:
            A list of dictionaries representing the objects returned.
        """
        result = super(UncensoredView, self)._query(manager,
                query, fields, order, limit)
        getter = facade.subsystems.Getter(None,
                manager, result, fields, censored=False)
        return getter.results


class CensoredView(View):
    """
    Facilitates creating more complex censored views for ObjectManager
    view methods. Particularly those that would otherwise call
    ObjectManager.get_filtered and require multiple subsequent, optionally
    nested, merges to complete the result.

    All queries performed as part of the view are verified by the authorizer.
    This includes queries performed as part of a result transformation.

    If no authorization is required and the caller is *sure* that the result
    will not contain any unautuhorized results (ie. for the Administrator)
    it may be a better choice to use `UncensoredView`.
    """
    def __call__(self, auth_token, filters=None, fields=(),
            order=None, limit=None):
        # override signiture to bind an auth token to the view
        view = super(CensoredView, self).__call__(filters, fields, order, limit)
        view.auth_token = auth_token
        return view

    def _query(self, manager, query, fields, order=None, limit=None):
        """
        Performs a censored query required to build the view result or
        perform associated transformations. The authorizer is used to
        filter all results from the raw Django query.

        Arguments:
            manager: A manager object for the type of object being queried.
            query: A Django QuerySet object or a dictionary of filters which can
                   be converted into a Django QuerySet by ObjectManager.Filter.
            fields: A sequence of fields which will be read from the resulting
                    objects.
            order: A tuple of fields which specify the query result ordering.
            limit: A python slice object representing the upper/lower bound of
                   the query result.

        Returns:
            A list of dictionaries representing the objects returned.
        """
        result = super(CensoredView, self)._query(manager,
                query, fields, order, limit)
        getter = facade.subsystems.Getter(self.auth_token,
                manager, result, fields, censored=True)
        return getter.results


# Ensure that pyamf knows how to marshall a View object
pyamf.add_type(View, util.to_list)

# vim:tabstop=5 shiftwidth=4 expandtab
