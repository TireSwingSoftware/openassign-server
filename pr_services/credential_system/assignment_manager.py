"""
AssignmentManager class
"""

import collections
import datetime
import logging

from operator import itemgetter
from itertools import chain

from django.conf import settings

import facade

from pr_messaging import send_message
from pr_services import exceptions
from pr_services import pr_time
from pr_services.object_manager import ObjectManager
from pr_services.rpc.service import service_method
from pr_services.utils import Utils

facade.import_models(locals(), globals())
merge_queries = Utils.merge_queries
flatten = chain.from_iterable

_logger = logging.getLogger('pr_services.credential_system.assignment_manager')

class AssignmentManager(ObjectManager):
    """
    Manage Assignments in the Power Reg system
    """

    GETTERS = {
        'achievement_awards': 'get_many_to_one',
        'assignment_attempts': 'get_many_to_one',
        'authority': 'get_general',
        'date_completed': 'get_time',
        'date_started': 'get_time',
        'due_date': 'get_time',
        'effective_date_assigned': 'get_time',
        'prerequisites_met': 'get_general',
        'serial_number': 'get_general',
        'status': 'get_general',
        'status_change_log': 'get_general',
        'task': 'get_foreign_key',
        'task_content_type': 'get_general',
        'user': 'get_foreign_key',
    }

    SETTERS = {
        'achievement_awards': 'set_many',
        'assignment_attempts': 'set_many',
        'authority': 'set_general',
        'date_completed': 'set_time',
        'date_started': 'set_time',
        'due_date': 'set_time',
        'effective_date_assigned': 'set_time',
        'serial_number': 'set_general',
        'status': 'set_general',
        'task': 'set_foreign_key',
        'user': 'set_foreign_key',
    }

    def __init__(self):
        """ constructor """

        ObjectManager.__init__(self)
        self.my_django_model = facade.models.Assignment

    @service_method
    def bulk_create(self, auth_token, task, users, optional_parameters=None):
        """
        calls the create() method once for each user specified.

        :param task:                FK for a Task
        :type task:                 int
        :param users:               FKs for Users to be assigned. If you list
                                    the same FK more than once, subsequent
                                    occurances will be ignored.
        :type users:                list
        :param optional_parameters: Optional attribute definitions, including
                                    date_started, due_date, effective_date_assigned,
                                    serial_number
        :type optional_parameters:  dict

        :return:                    dictionary of dictionaries.  Each dict will
                                    be indexed by user FK. Each sub-dict will
                                    have key 'status' which represents the
                                    assignment's status. Or, if there is an
                                    error, the 'status' value will be 'error'.
                                    Additional keys in this case will be
                                    'error_message' and 'error_code'.
        """

        self.blame = self._get_blame(auth_token)
        ret = {}
        for user in set(users):
            try:
                assignment = self.create(auth_token, task, user, optional_parameters)
                ret[user] = {'id' : assignment.id, 'status' : assignment.status}
            except exceptions.PrException, e:
                ret[user] = {'status' : 'error', 'error_message' : e.error_msg, 'error_code' : e.error_code}
                # we can't rely on a transaction rollback in this case
                new_assignments = self.my_django_model.objects.filter(user__id=user, blame=self.blame)
                if len(new_assignments) == 1:
                    new_assignments[0].delete()

        self.blame = None
        return ret

    @service_method
    def create(self, auth_token, task, user=None, optional_parameters=None):
        """Create an Assignment

        Status cannot be specified because of permission issues.  You must
        allow the system to automatically determine the enrollment status,
        and then a user with suffient permission may update that status.

        :param task:                FK for a Task
        :type task:                 int
        :param user:                FK for a User, defaults to acting user if not specified
        :type user:                 int
        :param optional_parameters: Optional attribute definitions, including
                                    date_started, due_date, effective_date_assigned,
                                    serial_number
        :type optional_parameters:  dict

        :return:                    reference to an Assignment

        """
        if optional_parameters is None:
            optional_parameters = {}

        blame = self._get_blame(auth_token)

        task_object = self._find_by_id(task, facade.models.Task).downcast_completely()
        if user is None and isinstance(auth_token, facade.models.AuthToken):
            user_object = auth_token.user
        else:
            user_object = self._find_by_id(user, facade.models.User)

        # check for duplicate assignment, but we can't raise an exception
        # until we know the user is otherwise authorized to create one
        if task_object.prevent_duplicate_assignments:
            duplicate_assignment_exists = self.my_django_model.objects.filter(user=user_object, task=task_object).count() > 0

        # handle optional attributes that are simple so we avoid the problem
        # of using update permissions
        assignment = self.my_django_model(task=task_object, user=user_object, blame=blame)
        for attribute in ['serial_number',]:
            if attribute in optional_parameters:
                setattr(assignment, attribute, optional_parameters[attribute])
        for attribute in ['date_started', 'due_date', 'effective_date_assigned']:
            if attribute in optional_parameters:
                value = pr_time.iso8601_to_datetime(optional_parameters[attribute])
                setattr(assignment, attribute, value)
        if task_object.remaining_capacity <= 0:
            assignment.status = 'wait-listed'
        # if there is a wait-list, even if capacity has opened up, continue
        # wait-listing so an admin can sort out who gets priority
        elif task_object.assignments.filter(status='wait-listed').count() > 0:
            assignment.status = 'wait-listed'
        assignment.save()

        self.authorizer.check_create_permissions(auth_token, assignment)

        if task_object.prevent_duplicate_assignments and duplicate_assignment_exists:
            raise exceptions.DuplicateAssignmentException

        return assignment

    def send_late_notices(self):
        # right now >= due date + late notice interval
        # due date + late notice interval <= right now
        # due date <= right now - late notice interval

        right_now = datetime.datetime.utcnow()
        for late_assignment in facade.models.Assignment.objects.filter(
                status='late', sent_late_notice=False,
                due_date__lte=right_now - datetime.timedelta(
                    seconds=settings.DEFAULT_ASSIGNMENT_LATE_NOTICE_INTERVAL)):
            send_message(message_type='assignment-late-notice',
                         context={'assignment': late_assignment},
                         recipient=late_assignment.user)
            late_assignment.sent_late_notice = True
            late_assignment.save()

    def send_reminders(self):
        right_now = datetime.datetime.utcnow()

        # right now >= due date - reminder interval  ==>
        # due date - reminder interval <= right now ==>
        # due date <= right now + reminder interval

        if settings.DEFAULT_ASSIGNMENT_PRE_REMINDER_INTERVAL:
            for unfinished_assignment in self.my_django_model.objects.exclude(
                status='completed').filter(
                sent_pre_reminder=False).filter(
                due_date__lte=right_now + datetime.timedelta(seconds=settings.DEFAULT_ASSIGNMENT_PRE_REMINDER_INTERVAL)):

                send_message(message_type='assignment-pre-reminder',
                             context={'assignment': unfinished_assignment},
                             recipient=unfinished_assignment.user)
                unfinished_assignment.sent_pre_reminder = True
                unfinished_assignment.save()

        for unfinished_assignment in self.my_django_model.objects.exclude(
            status='completed').filter(
            sent_reminder=False).filter(
            due_date__lte=right_now + datetime.timedelta(seconds=settings.DEFAULT_ASSIGNMENT_REMINDER_INTERVAL)):

            send_message(message_type='assignment-reminder',
                         context={'assignment': unfinished_assignment},
                         recipient=unfinished_assignment.user)
            unfinished_assignment.sent_reminder = True
            unfinished_assignment.save()

    def send_confirmations(self):
        end_of_today = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).replace(hour=0, minute=0,
            second=0, microsecond=0)
        for assignment in facade.models.Assignment.objects.filter(
                sent_confirmation=False).filter(
                effective_date_assigned__lte=end_of_today):
            send_message(message_type='assignment-confirmation',
                         context={'assignment': assignment},
                         recipient=assignment.user)
            assignment.sent_confirmation = True
            assignment.save()

    def mark_late_assignments(self):
        end_of_today = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).replace(hour=0, minute=0,
            second=0, microsecond=0)

        for late_assignment in facade.models.Assignment.objects.filter(
                due_date__lt=end_of_today).exclude(
                    status__in=['completed', 'late']):
            late_assignment.status = 'late'
            late_assignment.save()

    @service_method
    def view(self, auth_token, filters=None, fields=None,
            user_id=None, task_manager=None, task_type_name=None,
            task_fields=None):
        """
        A generic helper for returning information about a users assignments.
        Assignments are filtered by the current user id unless otherwise
        specified by `user_id`.

        Args:
            auth_token: The auth token for the current user.
            filters: django query filters to use instead of the defaults.
            fields: additional fields to include in the result.
            user_id: a user id used to filter assignments.
            task_manager: the task manager for expected resulting tasks.
            task_type_name: the final type name of the resulting tasks.
            task_fields: extra fields to return for resulting tasks.

        Returns:
            A merged queryset including fields optionally specified by `fields`
            for each assignment with information about the associated task.
            The assignments can be filtered by `filters` and additional fields
            to retrieve can be specified with `fields`.
        """
        if not filters:
            filters = {'exact': {'user': user_id or auth_token.user_id}}
            if task_type_name:
                filters['exact']['task__final_type__name'] = task_type_name

        default_fields = frozenset(('user', 'status', 'task'))
        if not fields:
            fields = set()
        elif not isinstance(fields, collections.Set):
            fields = set(fields)

        fields.update(default_fields)

        results = self.get_filtered(auth_token, filters, fields)
        if not results:
            return []

        default_task_fields = frozenset(('name', 'title', 'type',
                                         'description'))
        if not task_fields:
            task_fields = set()
        elif not isinstance(task_fields, collections.Set):
            task_fields = set(task_fields)

        task_fields.update(default_task_fields)

        if not task_manager:
            task_manager = facade.managers.TaskManager()

        return merge_queries(results, task_manager, auth_token, task_fields, 'task')

    @service_method
    def detailed_view(self, auth_token, *args, **kwargs):
        results = self.view(auth_token=auth_token, *args, **kwargs)
        user_manager = facade.managers.UserManager()
        return merge_queries(results, user_manager , auth_token,
                ('username', 'first_name', 'last_name', 'email'), 'user')

    if 'file_tasks' in settings.INSTALLED_APPS:
        @service_method
        def file_download_view(self, *args, **kwargs):
            manager = facade.managers.FileDownloadManager()
            return self.view(task_type_name='file download',
                    task_manager=manager, task_fields=('file_size', 'file_url'),
                    *args, **kwargs)

        @service_method
        def detailed_file_download_view(self, auth_token, *args, **kwargs):
            manager = facade.managers.FileDownloadManager()
            result = self.view(auth_token=auth_token,
                    task_type_name='file download',
                    task_manager=manager, *args, **kwargs)
            user_manager = facade.managers.UserManager()
            # XXX: if this is ever changed to include the username and email
            # address this routine should instead call AssignmentManager.detailed_view
            # above.
            return merge_queries(result, user_manager, auth_token,
                    ('first_name', 'last_name'), 'user')

        @service_method
        def file_upload_view(self, *args, **kwargs):
            manager = facade.managers.FileUploadManager()
            return self.view(task_type_name='file upload',
                    task_manager=manager, *args, **kwargs)

    @service_method
    def exam_view(self, *args, **kwargs):
        manager = facade.managers.ExamManager()
        return self.view(task_type_name='exam', task_manager=manager,
                *args, **kwargs)

    @service_method
    def detailed_exam_view(self, auth_token, *args, **kwargs):
        results = self.exam_view(auth_token=auth_token,
                task_fields=('passing_score',), *args, **kwargs)
        user_manager = facade.managers.UserManager()
        return merge_queries(results, user_manager, auth_token,
                ('first_name', 'last_name'), 'user')

    @service_method
    def session_view(self, auth_token, *args, **kwargs):
        manager = facade.managers.SessionUserRoleRequirementManager()
        results = self.view(auth_token, task_manager=manager,
                task_type_name='session user role requirement',
                task_fields=('session', ), *args, **kwargs)

        if results and ('task' in results[0] and
                        'session' in results[0]['task']):
            # merge in session details
            session_ids = [assignment['task']['session'] for assignment in results]
            session_query = Session.objects.filter(id__in=session_ids)
            session_manager = facade.managers.SessionManager()
            sessions = facade.subsystems.Getter(auth_token, session_manager,
                    session_query, ['start', 'end']).results
            session_dict = {}
            for session in sessions:
                session_dict[session['id']] = session
            for assignment in results:
                assignment['task']['session'] = session_dict[assignment['task']['session']]

        return results

    @service_method
    def transcript_view(self, auth_token, filters=None, fields=None,
            user_id=None, *args, **kwargs):
        """
        A convenient view over a user's transcript. The contents of which is a
        list of assignments for the user specified by `user_id` or the current
        authenticated user.

        The transcript includes general information about each task for
        'completed' assignments and details of any associated achievements and awards.

        Args:
            See arguments for AssignmentManager.view
        """
        # fields needed to complete the view
        default_fields = set(('date_started', 'date_completed', 'achievement_awards'))

        # union with any fields the user specified
        if fields:
            fields = set(fields) | default_fields
        else:
            fields = default_fields

        # default filter for completed status
        if not filters:
            filters = {
                'exact': {
                    'status': 'completed',
                    'user': user_id or auth_token.user_id
                }
            }
        # grab completed assignments and return early if there are none
        assignments = self.view(auth_token, filters=filters, fields=fields,
                task_fields=('achievements',), *args, **kwargs)

        if (assignments and
            'task' in assignments[0] and
            'achievements' in assignments[0]['task']):
            # merge in achievement details; hit the database only once
            # TODO: this could be done pretty easily in merge_queries
            manager = facade.managers.AchievementManager()
            ids = set(flatten(a['task']['achievements'] for a in assignments))
            query = Achievement.objects.filter(id__in=ids)
            results = facade.subsystems.Getter(auth_token, manager, query,
                    ('name', 'description')).results
            achievements = {}
            for row in results:
                achievements[row['id']] = row
            for task in map(itemgetter('task'), assignments):
                task['achievements'] = map(achievements.get, task['achievements'])

        return assignments

# vim:tabstop=4 shiftwidth=4 expandtab
