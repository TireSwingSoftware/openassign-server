
import codecs

import facade
import mixins

class CommonExamTests(mixins.ExamTestMixin):

    def test_exam_creation_managers(self):
        e = self._create_exam('mother_exam', 'The Mother of All Exams',
                              passing_score=90)
        qp = self._create_question_pool(e, "Mama's Question Pool")
        q = self._create_question(qp, 'bool', 'Is mama always right?')
        a = self._create_answer(q, 'Yes', correct=True)
        a = self._create_answer(q, 'No')

    def test_exam_manager_xml(self):
        # import a new exam
        xml_data = codecs.open('pr_services/test_data/complex_exam.xml', 'r',
                               encoding='utf-8').read()
        exam = self.exam_manager.create_from_xml(self.admin_token, xml_data)
        qs = facade.models.Answer.objects.all()
        qs = qs.filter(question__question_pool__exam=exam)
        qs = qs.filter(next_question_pool__isnull=False)
        self.assertTrue(qs.count() > 0)
        for a in qs:
            qs2 = facade.models.QuestionPool.objects.all()
            self.assertEquals(qs2.filter(randomize_questions=True).count(), 1)
            qs2 = qs2.filter(exam=exam)
            qs2 = qs2.filter(pk=a.next_question_pool.pk)
            self.assertEquals(qs2.count(), 1)
        new_xml_data = self.exam_manager.export_to_xml(self.admin_token, exam.id)

        # Now rename the original exam, import the xml and export again, then
        # check to see if the XML matches.
        exam.name = 'renamed_exam'
        exam.save()
        new_exam = self.exam_manager.create_from_xml(self.admin_token, new_xml_data)
        new_xml_data2 = self.exam_manager.export_to_xml(self.admin_token, new_exam.id)
        self.assertEquals(new_xml_data, new_xml_data2)

        # Try one other exam with correct answers listed.
        xml_data = codecs.open('pr_services/test_data/instructor_exam.xml', 'r',
                               encoding='utf-8').read()
        exam = self.exam_manager.create_from_xml(self.admin_token, xml_data)
        new_xml_data = self.exam_manager.export_to_xml(self.admin_token, exam.id)

