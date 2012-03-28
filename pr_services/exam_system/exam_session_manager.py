"""
Exam Session Manager class.
"""

__docformat__ = "restructuredtext en"

from django.utils import timezone

from pr_services import exceptions, pr_time
from pr_services.credential_system.assignment_attempt_manager import AssignmentAttemptManager
from pr_services.rpc.service import service_method

import facade

class ExamSessionManager(AssignmentAttemptManager):
    """
    Manage exam sessions in the Power Reg system.

    **Attributes:**
     * *date_started* -- Time the exam_session started, as ISO8601 string.
     * *date_completed* -- Time the exam_session ended, as ISO8601 string.
     * *exam* -- Foreign Key for the exam being taken.
     * *passed* -- Whether the user passed the exam, None if the exam is not complete.
     * *response_questions* -- List of Foreign Keys for questions which have already been answered.
     * *score* -- Percentage of questions for which there is a correct answer which were answered correctly, to 2 decimal places.
     * *user* -- Foreign Key for the user taking the exam.
    """

    GETTERS = {
        'exam': 'get_foreign_key',
        'number_correct': 'get_general',
        'passed': 'get_general',
        'passing_score': 'get_general',
        'response_questions': 'get_many_to_many',
        'score': 'get_decimal',
        'user': 'get_foreign_key',
    }
    def __init__(self):
        """Constructor."""

        super(ExamSessionManager, self).__init__()
        self.my_django_model = facade.models.ExamSession
        self.post_exam_session_hooks = []

    @service_method
    def create(self, auth_token, assignment, fetch_all=True, resume=True):
        """
        Create a new exam_session.

        :param auth_token:  The authentication token of the acting user
        :type auth_token:   facade.models.AuthToken
        :param assignment:  Foreign Key for the assignment
        :type assignment:   int
        :param fetch_all:   If True (default=True), return all questions and
                            answers as tiered dictionaries.
        :type fetch_all:    bool
        :param resume:      If True (default=True), resume a pending exam session
                            if one is found for the given exam and user.
        :type resume:       bool
        :return:            Reference to the newly created exam_session, or
                            optionally all of the questions with answers.  This
                            result will be a dictionary similar to the following:

        ::

            {
                'id': 1,
                'title': 'Title of the Exam',
                'passing_score': 90,
                'question_pools':
                [
                    {
                        'id': 1,
                        'title': 'First Section',
                        'questions':
                        [
                            {
                                'id': 1,
                                'label: 'How confusing is this?',
                                'required': True,
                                'text_response': False,
                                'min_value': 0,
                                'max_value': 5,
                                'question_type': 'rating',
                                'widget': 'RadioSelect',
                            },
                            {
                                'id': 2,
                                'label': 'Do you like beer?',
                                'required': True,
                                'text_response': False,
                                'min_answers': 1,
                                'max_answers': 1,
                                'question_type': 'choice',
                                'widget': 'RadioSelect',
                                'answers':
                                [
                                    {
                                        'id': 1,
                                        'label': 'Yes',
                                    },
                                    {
                                        'id': 2,
                                        'label': 'A lot',
                                    },
                                    {
                                        'id': 3,
                                        'label': 'Very Much!',
                                        'text_response': True,
                                    },
                                    {
                                        'id': 4,
                                        'label': 'I am a 12-year-old girl',
                                        'end_question_pool': True,
                                    },
                                ],
                            },
                            {
                                'id': 3,
                                'label: 'What is your name?',
                                'required': True,
                                'text_response': False,
                                'min_length': 0,
                                'max_length': 127,
                                'question_type': 'char',
                                'widget': 'TextInput',
                            },
                            {
                                'id': 4,
                                'label: 'Please enter the number 42.',
                                'required': True,
                                'text_response': True,
                                'text_response_label': 'Explain why you entered 42',
                                'question_type': 'int',
                                'widget': 'TextInput',
                            },
                        ],
                    },
                ],
            }
        """

        assignment_object = self._find_by_id(assignment, facade.models.Assignment)
        if resume and isinstance(auth_token, facade.models.AuthToken):
            exam_sessions = facade.models.ExamSession.objects.filter(assignment__id=assignment_object.id,
                date_completed__isnull=True).order_by('-date_started')
            if exam_sessions:
                return self.resume(auth_token, exam_sessions[0].id, fetch_all)
        exam_session = self._create(auth_token, assignment_object, fetch_all)
        return exam_session

    def _create(self, auth_token, assignment, fetch_all=True):
        """
        Create the exam session and return the first set of questions.

        :param auth_token:  The authentication token of the acting user
        :type auth_token:   facade.models.AuthToken
        :param assignment:  Reference to the Assignment being attempted
        :type assignment:   facade.models.Assignment
        :param fetch_all:   If True (default=True), return all questions and
                            answers as tiered dictionaries.
        :type fetch_all:    bool
        :return:            Reference to the newly created exam_session, or
                            optionally a dictionary containing the first pool of
                            questions with answers.
        """
        es = self.my_django_model.objects.create(assignment=assignment)
        self.authorizer.check_create_permissions(auth_token, es)
        if fetch_all:
            return self._get_next_questions(auth_token, es)
        else:
            return es

    @service_method
    def resume(self, auth_token, exam_session, fetch_all=True):
        """
        Resume a previously started exam session.

        :param auth_token:      The authentication token of the acting user
        :type auth_token:       facade.models.AuthToken
        :param exam_session:    Primary key for the exam session.
        :type exam_session:     int
        :param fetch_all:       If True (default=True), return all questions and
                                answers as tiered dictionaries.
        :type fetch_all:        bool
        :return:                Reference to the resumed exam_session, or
                                optionally a dictionary containing all questions
                                and responses received so far and the first pool
                                of unanswered questions.
        """

        es = self._find_by_id(exam_session)

        # Make sure the exam session user is the one submitting this response.
        # XXX: should this be moved into the authorizer?
        if es.assignment.user.id != auth_token.user.id:
            raise exceptions.PermissionDeniedException()

        # Check to make sure the exam isn't already completed.
        if es.date_completed:
            raise exceptions.ExamSessionAlreadyFinishedException()

        if fetch_all:
            # Record date started if the user is actually fetching the
            # questions (in other words, starting to take the exam) and it has
            # not been previously set.
            if es.date_started is None:
                es.date_started = timezone.now()
                es.save()
            return self._get_next_questions(auth_token, es, False)
        else:
            return es

    @service_method
    def review(self, auth_token, exam_session):
        """Return all questions, answers and response for review.

        :param auth_token:      The authentication token of the acting user
        :type auth_token:       facade.models.AuthToken
        :param exam_session:    Primary key for the exam session.
        :type exam_session:     int
        :return:                A dictionary containing all questions and
                                responses.
        """

        es = self._find_by_id(exam_session)
        return self._get_next_questions(auth_token, es, True, True)

    def _get_next_questions(self, auth_token, exam_session,
                            include_responses=False, for_review=False):
        """
        Return the next set of questions.

        :param auth_token:          The authentication token of the acting user
        :type auth_token:           facade.models.AuthToken
        :param exam_session:        Reference to the exam session.
        :type exam_session:         facade.models.ExamSession
        :param include_responses:    If True (default=False), return responses
                                    submitted so far.
        :type include_responses:     bool
        :param for_review:          If True (default=False), return all
                                    questions and responses submitted.
        :type for_review:           bool
        :return:                    A hierarchical dict-representation of an exam with
                                    question pool(s), questions and answers all included.
        """
        assert isinstance(exam_session, facade.models.ExamSession)
        if for_review:
            q_iter = exam_session.iter_questions()
        else:
            q_iter = exam_session.get_next_questions(include_responses)

        qp_dicts = {} # remember question pool dicts
        for q in q_iter:
            qp = q.question_pool
            qp_dict = qp_dicts.get(qp.id, None)
            if not qp_dict:
                qp_dicts[qp.id] = qp_dict = {
                    'id': qp.id,
                    'title': qp.title,
                    'questions': []
                }
                if qp.name:
                    qp_dict['name'] = qp.name
            # add the question and answers dictionary.
            q_dict = {}
            qp_dict['questions'].append(q_dict)
            q_attrs = ['id', 'name', 'required', 'label', 'help_text',
                       'question_type', 'widget']
            if q.text_response or q.question_type == 'choice':
                q_attrs.extend(('text_response', 'text_response_label',
                                'min_length', 'max_length', 'text_regex'))
            if q.question_type in frozenset(('decimal', 'float', 'int', 'rating')):
                q_attrs.extend(('min_value', 'max_value'))
            if q.question_type == 'choice':
                q_attrs.extend(('min_answers', 'max_answers'))
            for q_attr in q_attrs:
                q_value = getattr(q, q_attr)
                if q_value is not None:
                    q_dict[q_attr] = q_value
            q_dict['answers'] = q.answers.values(
                    'id', 'name', 'label', 'text_response',
                    'end_question_pool', 'end_exam', 'value')
            try:
                response = exam_session.responses.get(question=q)
                if response.valid is None: continue
            except facade.models.Response.DoesNotExist:
                continue
            q_dict['rejoinder'] = q.rejoinder
            if include_responses:
               q_dict['response'] = r_dict = {}
               for key in ('id', 'value', 'text', 'valid'):
                   value = getattr(response, key)
                   if value is not None:
                      r_dict[key] = value
        return {
            'id': exam_session.id,
            'name': exam_session.exam.name,
            'title': exam_session.exam.title,
            'passing_score': exam_session.exam.passing_score,
            'question_pools': qp_dicts.values(),
        }

    @service_method
    def add_response(self, auth_token, exam_session, question,
                     optional_parameters=None):
        """
        Add a response to an exam session.  This is the only way to create a
        response.

        :param auth_token:          The authentication token of the acting user
        :type auth_token:           facade.models.AuthToken
        :param exam_session:        Primary Key for an exam_session.
        :type exam_session:         int
        :param question:            Foreign Key for a question.
        :type question:             int
        :param optional_parameters: Dictionary of optional parameter values
                                    indexed by the following keys:

            * value (primary response value or list of answer foreign keys)
            * text (free text response)
            * answers (list of answer foreign keys, same as value)

        :type optional_parameters:  dict or None
        :return:                    Reference to the exam_session. If the
                                    question was answered incorrectly, there
                                    may be a message for the user indexed as
                                    'rejoinder'
        """

        if optional_parameters is None:
            optional_parameters = {}

        # Get the exam session and question objects.
        es = self._find_by_id(exam_session)
        q = self._find_by_id(question, facade.models.Question)

        # Make sure the exam session user is the one submitting this response.
        if es.assignment.user.id != auth_token.user.id:
            raise exceptions.PermissionDeniedException()

        # make sure the exam session is not yet finished
        if es.date_completed:
            raise exceptions.ExamSessionAlreadyFinishedException

        # Now submit the response value and/or text.
        answers = optional_parameters.get('answers', None)
        value = optional_parameters.get('value', None)
        if value is None:
            value = answers
        text = optional_parameters.get('text', None)

        # Check to see if a response has already been submitted; if so, check
        # the update permissions for the response...
        if es.responses.filter(question=q, valid__isnull=False).count():
            r = es.submit_response(q, value, text)
            try:
                self.authorizer.check_update_permissions(auth_token, r,
                                                         {'value': value,
                                                          'text': text})
            except exceptions.PermissionDeniedException:
                raise exceptions.ExamResponseAlreadyReceivedException()
        # Otherwise just check the create permissions.
        else:
            r = es.submit_response(q, value, text)
            self.authorizer.check_create_permissions(auth_token, r)

        # Return the exam session ID and an optional error message.
        ret = {'id': es.id}
        if q.rejoinder and not r.correct:
            ret['rejoinder'] = q.rejoinder
        return ret

    @service_method
    def finish(self, auth_token, exam_session):
        """
        Finish an exam session.

        :param auth_token:      The authentication token of the acting user
        :type auth_token:       facade.models.AuthToken
        :param exam_session:    Primary Key for an exam_session.
        :type exam_session:     int
        :return:                If there are no more questions, struct with the
                                attributes 'date_completed', and optionally
                                'score' and 'passed' as appropriate.  If there
                                are more questions, a struct similar to the one
                                returned by the create method.
        """

        es = self._find_by_id(exam_session)
        return self._finish(auth_token, es)

    def _finish(self, auth_token, exam_session):
        """
        Complete the exam session, or return more questions if available.

        :param auth_token:      The authentication token of the acting user
        :type auth_token:       facade.models.AuthToken
        :param exam_session:    Reference to the exam session.
        :type exam_session:     facade.models.ExamSession
        :return:                If there are no more questions, struct with the
                                attributes 'date_completed', and optionally
                                'score' and 'passed' as appropriate.  If there
                                are more questions, a struct similar to the one
                                returned by the create method.
        """

        # Check to make sure the exam isn't already completed.
        if exam_session.date_completed:
            raise exceptions.ExamSessionAlreadyFinishedException()

        # Check to see if there are more questions available.
        next_questions = self._get_next_questions(auth_token, exam_session)
        if next_questions.get('question_pools', []):
            return next_questions

        # Update the date completed and calculate the score.
        exam_session.date_completed = timezone.now().replace(microsecond=0)
        self.authorizer.check_update_permissions(auth_token, exam_session,
                                                 {'date_completed':
                                                 exam_session.date_completed})
        if not exam_session.date_completed:
            raise exceptions.ExamSessionNotFinishedException()
        if exam_session.score is not None:
            raise exceptions.ExamSessionScoreAlreadyCalculatedException()
        exam_session.calculate_score()
        exam_session.save()

        # Call any post exam session hooks registered.
        for hook in self.post_exam_session_hooks:
            hook(auth_token, exam_session)

        if exam_session.passed:
            exam_session.assignment.mark_completed()

        # Return the date completed, score and passed flag.
        return {'date_completed': exam_session.date_completed.replace(\
                                  tzinfo=pr_time.UTC()).isoformat(),
                'score': exam_session.score, 'passed': exam_session.passed}

    @service_method
    def get_results(self, auth_token, exam_session):
        """
        For an exam_session that has been completed, return a data structure
        that indicates how the user did. This requires the actor to have read
        permission for the exam_session's "score" and "passed" attributes.

        :param auth_token:      The authentication token of the acting user
        :type auth_token:       facade.models.AuthToken
        :param exam_session:    Primary key for an exam_session
        :type exam_session:     int
        :return:                Dictionary of the form:

        ::

            {
                'score': 90,
                'passed': True,
                'missed_questions':
                    [
                        {
                            'label': 'What color is the sky?',
                            'rejoinder': 'Try looking up.'
                        },
                        {
                            'label': 'What color is the grass?',
                            'rejoinder': 'Try looking down.'
                        }
                    ],
                'invalid_questions':
                    [
                        {
                            'label': 'Please enter any word.',
                            'rejoinder': 'Any combination of letters will do.'
                        }
                    ]
            }
        """

        es = self._find_by_id(exam_session)
        self.authorizer.check_read_permissions(auth_token, es,
                                               ['score', 'passed',
                                                'response_questions'])

        missed_questions = es.response_questions.filter(
            responses__valid=True, responses__correct=False).values('label', 'rejoinder')
        invalid_questions = es.response_questions.filter(
            responses__valid=False).values('label', 'rejoinder')
        return {'score': None if es.score is None else unicode(es.score),
                'passed': es.passed, 'missed_questions': missed_questions,
                'invalid_questions': invalid_questions}

# vim:tabstop=4 shiftwidth=4 expandtab
