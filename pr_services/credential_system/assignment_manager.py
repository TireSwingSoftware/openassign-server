"""
AssignmentManager class
"""

import collections
import logging

from operator import itemgetter
from itertools import chain
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

import facade

from pr_messaging import send_message
from pr_services import exceptions
from pr_services import pr_time
from pr_services.exceptions import PermissionDeniedException
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

        right_now = timezone.now()
        for late_assignment in facade.models.Assignment.objects.filter(
                status='late', sent_late_notice=False,
                due_date__lte=right_now - timedelta(
                    seconds=settings.DEFAULT_ASSIGNMENT_LATE_NOTICE_INTERVAL)):
            send_message(message_type='assignment-late-notice',
                         context={'assignment': late_assignment},
                         recipient=late_assignment.user)
            late_assignment.sent_late_notice = True
            late_assignment.save()

    def send_reminders(self):
        right_now = timezone.now()

        # right now >= due date - reminder interval  ==>
        # due date - reminder interval <= right now ==>
        # due date <= right now + reminder interval

        if settings.DEFAULT_ASSIGNMENT_PRE_REMINDER_INTERVAL:
            for unfinished_assignment in self.my_django_model.objects.exclude(
                status='completed').filter(
                sent_pre_reminder=False).filter(
                due_date__lte=right_now + timedelta(seconds=settings.DEFAULT_ASSIGNMENT_PRE_REMINDER_INTERVAL)):

                send_message(message_type='assignment-pre-reminder',
                             context={'assignment': unfinished_assignment},
                             recipient=unfinished_assignment.user)
                unfinished_assignment.sent_pre_reminder = True
                unfinished_assignment.save()

        for unfinished_assignment in self.my_django_model.objects.exclude(
            status='completed').filter(
            sent_reminder=False).filter(
            due_date__lte=right_now + timedelta(seconds=settings.DEFAULT_ASSIGNMENT_REMINDER_INTERVAL)):

            send_message(message_type='assignment-reminder',
                         context={'assignment': unfinished_assignment},
                         recipient=unfinished_assignment.user)
            unfinished_assignment.sent_reminder = True
            unfinished_assignment.save()

    def send_confirmations(self):
        end_of_today = (timezone.now() + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0)
        for assignment in facade.models.Assignment.objects.filter(
                sent_confirmation=False).filter(
                effective_date_assigned__lte=end_of_today):
            send_message(message_type='assignment-confirmation',
                         context={'assignment': assignment},
                         recipient=assignment.user)
            assignment.sent_confirmation = True
            assignment.save()

    @service_method
    def email_task_assignees(self, auth_token, task_id, message, subject=None,
            status_filter=(u'assigned', u'pending')):
        """
        Send an arbitrary email message to users currently assigned to a Task if
        their Assignment status is 'assigned' or 'pending'. The status filters
        can be overriden by passing `status_filters` containing a list of
        required statuses. If `subject` is not specified the default is used in
        the template.

        See pr_services/templates/pr_messaging/email/assignment-task-message
        """
        task = Task.objects.get(id=task_id)
        assignments = Assignment.objects.filter(task__id=task_id,
                status__in=status_filter).select_related('user__email')
        for assignment in assignments:
            send_message(message_type='assignment-task-message',
                    context={
                        'task': task,
                        'assignment': assignment,
                        'subject': subject,
                        'body': message,
                        'sender': auth_token.user
                    },
                    recipient=assignment.user.email)

    def mark_late_assignments(self):
        end_of_today = (timezone.now() + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0)

        for late_assignment in facade.models.Assignment.objects.filter(
                due_date__lt=end_of_today).exclude(
                    status__in=['completed', 'late']):
            late_assignment.status = 'late'
            late_assignment.save()

    @service_method
    def view(self, auth_token, *args, **kwargs):
        view = self.build_view(
                filters={'exact': {'user': auth_token.user_id}},
                fields=('user', 'status'),
                merges=(
                    ('task',
                        ('name', 'title', 'type', 'description')),
                ))
        return view(auth_token, *args, **kwargs)

    @service_method
    def detailed_view(self, auth_token, *args, **kwargs):
        return self.view(auth_token, *args, **kwargs).merge(
            'user', ('first_name', 'last_name', 'email'))

    if 'file_tasks' in settings.INSTALLED_APPS:
        @service_method
        def file_download_view(self, auth_token, *args, **kwargs):
            view = self.build_view(
                filters={
                    'exact': {
                        'user': auth_token.user_id,
                        'task__final_type__name': 'file download'
                }},
                fields=('due_date', 'user', 'status'),
                merges=(
                    ('task:file download',
                        ('name', 'title', 'type', 'description',
                         'file_size', 'file_url')),
                ))
            return view(auth_token, *args, **kwargs)

        @service_method
        def detailed_file_download_view(self, auth_token, *args, **kwargs):
            view = self.build_view(
                filters={
                    'exact': {
                        'user': auth_token.user_id,
                        'task__final_type__name': 'file download'
                }},
                fields=('user', 'status'),
                merges=(
                    # XXX: this should probably expose at least as much
                    # information as file_download_view.
                    # ie. file_size and file_url
                    ('task:file download',
                        ('name', 'title', 'type', 'description')),
                    ('user',
                        ('first_name', 'last_name'))
                ))
            return view(auth_token, *args, **kwargs)

        @service_method
        def file_upload_view(self, auth_token, *args, **kwargs):
            view = self.build_view(
                filters={
                    'exact': {
                        'user': auth_token.user_id,
                        'task__final_type__name': 'file upload'
                }},
                fields=('user', 'status'),
                merges=(
                    ('task:file upload',
                        ('name', 'title', 'type', 'description')),
                ))
            return view(auth_token, *args, **kwargs)

    @service_method
    def exam_view(self, auth_token, *args, **kwargs):
        view = self.build_view(
            filters={
                'exact': {
                    'user': auth_token.user_id,
                    'task__final_type__name': 'exam'
            }},
            fields=('due_date', 'user', 'status', 'task'),
            merges=(
                ('task:exam',
                    ('name', 'title', 'type', 'description', 'passing_score')),
            ))
        return view(auth_token, *args, **kwargs)

    @service_method
    def detailed_exam_view(self, auth_token, *args, **kwargs):
        return self.exam_view(auth_token, *args, **kwargs).merge(
                'user', ('first_name', 'last_name'))

    @service_method
    def session_view(self, auth_token, *args, **kwargs):
        view = self.build_view(
            filters={
                'exact': {
                    'user': auth_token.user_id,
                    'task__final_type__name': 'session user role requirement'
            }},
            fields=('user', 'status', 'task'),
            merges=(
                ('task:sessionuserrolerequirement',
                    ('name', 'title', 'type', 'description', 'session')),
                ('task:sessionuserrolerequirement.session',
                    ('start', 'end'))
            ))
        return view(auth_token, *args, **kwargs)

    @service_method
    def transcript_view(self, auth_token, *args, **kwargs):
        """
        A convenient view over a user's transcript.

        By default, the transcript includes general information about each
        task for 'completed' assignments and details of any associated
        achievements and awards.
        """
        view = self.build_view(
                filters={'exact': {
                    'user': auth_token.user_id
                    }},
                fields=('user', 'status', 'date_started', 'date_completed',
                        'achievement_awards'),
                merges=(
                    ('task',
                        ('name', 'title', 'type', 'description',
                         'achievements')),
                    ('task.achievements',
                        ('name', 'description')),
                ))
        return view(auth_token, *args, **kwargs)

# vim:tabstop=4 shiftwidth=4 expandtab
