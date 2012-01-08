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


