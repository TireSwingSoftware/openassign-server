import facade
import uuid

try:
    import cPickle as pickle
except ImportError:
    import pickle

from django.core.exceptions import ObjectDoesNotExist

facade.import_models(locals(), globals())

class ExamTestMixin:
    def _create_exam(self, name=None, title=None, opts=None, **kwargs):
        name = name or kwargs.pop('name')
        title = title or kwargs.pop('title')
        opts = opts or {}
        opts.update(kwargs)
        return self.exam_manager.create(self.admin_token, name, title, opts)

    def _create_question_pool(self, exam=None, title=None, opts=None, **kwargs):
        exam = exam or kwargs.pop('exam')
        exam = getattr(exam, 'pk', exam)
        title = title or kwargs.pop('title')
        opts = opts or {}
        opts.update(kwargs)
        return self.question_pool_manager.create(self.admin_token, exam, title,
                                                 opts)

    def _create_question(self, question_pool=None, question_type=None,
                         label=None, opts=None, **kwargs):
        question_pool = question_pool or kwargs.pop('question_pool')
        question_pool = getattr(question_pool, 'pk', question_pool)
        question_type = question_type or kwargs.pop('question_type')
        label = label or kwargs.pop('label')
        opts = opts or {}
        opts.update(kwargs)
        return self.question_manager.create(self.admin_token, question_pool,
                                            question_type, label, opts)

    def _create_answer(self, question=None, label=None, opts=None, **kwargs):
        question = question or kwargs.pop('question')
        question = getattr(question, 'pk', question)
        label = label or kwargs.pop('label', None)
        opts = opts or {}
        opts.update(kwargs)
        return self.answer_manager.create(self.admin_token, question, label,
                                          opts)


class RoleTestMixin:
    def create_role(self, privs=None, check_methods=None,
            arbitrary_perms=None, name=None):
        create_role = Role.objects.create
        create_acl = ACL.objects.create
        create_method_call = ACMethodCall.objects.create
        methods = ACCheckMethod.objects

        if not privs:
            privs = {}
        for actee_type, crud in privs.iteritems():
            if hasattr(facade.models, actee_type):
                crud.setdefault('c', False)
                crud.setdefault('r', set())
                crud.setdefault('u', set())
                crud.setdefault('d', False)

        if not name:
            name = 'Test Role %s' % uuid.uuid4()
        role = create_role(name=name)
        acl = create_acl(role=role, acl=pickle.dumps(privs))
        if arbitrary_perms:
            acl.arbitrary_perm_list = pickle.dumps(arbitrary_perms)
        if not check_methods:
            check_methods = (('auth.actor_is_anybody', None),)
        self.addCleanup(self.delete_role, role)
        for name, params in check_methods:
            try:
                method = methods.get(name=name)
            except ObjectDoesNotExist:
                method = methods.create(name=name, title=name)
                self.addCleanup(method.delete)
            method_call = create_method_call(acl=acl,
                    ac_check_method=method,
                    ac_check_parameters=pickle.dumps(params or {}))
            method_call.save()
            self.addCleanup(method_call.delete)
        acl.save()
        self.authorizer.flush()
        return role, acl

    def delete_role(self, role):
        ACMethodCall.objects.filter(acl__role__id=role.id).delete()
        ACL.objects.filter(role__id=role.id).delete()
        Role.objects.filter(id=role.id).delete()
        self.authorizer.flush()


