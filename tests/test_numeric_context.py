"""Synthetic numeric-context regressions proposed before changing parser behavior."""
from pathlib import Path
import sys
import unittest

SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE/'scripts'))
from career.numeric import occurrences,numeric_review


def review_pair(original,rendered):
    claim=dict(id='claim_example',assertion=original,meaning=original)
    return numeric_review([dict(slot='resume',text=rendered)],[claim],
        dict(claim_spans=[dict(claim_id=claim['id'],text=rendered)]))[0]


class NumericContextRegressions(unittest.TestCase):
    def test_year_range_stops_before_a_new_education_record(self):
        original='2011 - 2017'
        text=original+'\nNetwork Operations Certificate · 2014'
        entries=occurrences(text)
        self.assertIsNone(entries[1]['unit'])
        issues=numeric_review([dict(slot='resume',text=text)],
            [dict(id='claim_years',assertion=original,meaning=original)],
            dict(claim_spans=[dict(claim_id='claim_years',text=original)]))[0]
        self.assertEqual(['2014'],[issue['token'] for issue in issues])

    def test_ratio_and_duration_phrases_are_not_measurement_nouns(self):
        text='5.5 to 7.5 out of 10 over\napproximately 7-8 months.'
        entries=occurrences(text)
        self.assertEqual(['5.5','7.5','10','7','8'],[entry['text'] for entry in entries])
        self.assertEqual([None,None,'scale:point',None,'time:month'],[entry['unit'] for entry in entries])
        self.assertTrue(review_pair(text,text.replace('7.5','8.5')))
        self.assertTrue(review_pair(text,text.replace('10','100')))
        self.assertTrue(review_pair(text,text+' Another 999%.'))

    def test_explicit_point_scale_and_ratio_denominator_share_the_scale_identity(self):
        original='Introduced a 10-point rating scale. Score moved from 5.5 to 7.5 over approximately 7-8 months.'
        rendered='Score moved from 5.5 to 7.5 out of 10 over approximately 7-8 months.'
        self.assertFalse(review_pair(original,rendered))
        self.assertTrue(review_pair(original,rendered.replace('out of 10','out of 100')))

    def test_grammar_recognition_does_not_erase_unknown_measurements(self):
        self.assertEqual('opaque:over',occurrences('Measured 25 over.')[0]['unit'])
        self.assertEqual('opaque:out',occurrences('Measured 25 out.')[0]['unit'])
        self.assertTrue(review_pair('Measured 25 over.','Measured 25 out.'))

    def test_same_calendar_months_match_across_russian_and_english(self):
        for original,translated in (
            ('март2017—август2018.','Mar 2017 - Aug 2018.'),
            ('ноябрь2021—декабрь2023.','Nov 2021 - Dec 2023.'),
            ('с августа2024.','since Aug 2024.'),
        ):
            with self.subTest(original=original):
                self.assertFalse(review_pair(original,translated))

    def test_calendar_normalization_preserves_month_precision_and_year_values(self):
        original='март2017—август2018.'
        for changed in ('Apr 2017 - Aug 2018.','Mar 2017 - Sep 2018.','Mar 2017 - Aug 2019.'):
            with self.subTest(changed=changed):self.assertTrue(review_pair(original,changed))

    def test_calendar_year_annotation_is_not_a_duration(self):
        self.assertFalse(review_pair('Опыт с 2017 года.','Experience since 2017.'))
        self.assertTrue(review_pair('Worked 2017 years.','Worked 2017.'))
        self.assertTrue(review_pair('Measured 2017 kg.','Measured 2017.'))

    def test_real_wrapped_units_remain_checked_including_unseen_units(self):
        for unit in ('KB','USD','%','ms','quux'):
            with self.subTest(unit=unit):
                original='Measured 400 '+unit+'.'
                self.assertFalse(review_pair(original,'Measured 400\n'+unit+'.'))
                self.assertTrue(review_pair(original,'Measured 400\notherunit.'))
                self.assertTrue(review_pair(original,'Measured 401\n'+unit+'.'))
        self.assertEqual('opaque:quux',occurrences('2011 - 2017\nquux.')[1]['unit'])
        self.assertEqual('mass:kg',occurrences('2011 - 2017\nkg.')[1]['unit'])
        self.assertTrue(review_pair('Quantity 2011 - 2017 kg.','Quantity 2011 - 2017\ng.'))

    def test_all_month_aliases_keep_identity_without_losing_changed_months(self):
        russian=('января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря')
        english=('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec')
        for index,month in enumerate(russian):
            with self.subTest(month=month):
                original=month+'2022.'
                self.assertFalse(review_pair(original,english[index]+' 2022.'))
                self.assertTrue(review_pair(original,english[(index+1)%12]+' 2022.'))

    def test_explicit_measurement_markers_near_months_take_precedence(self):
        for unit in ('kg','quux','%','USD'):
            with self.subTest(unit=unit):
                original='Mar2017 '+unit+'.'
                self.assertEqual(occurrences('2017 '+unit+'.')[0]['unit'],occurrences(original)[0]['unit'])
                self.assertTrue(review_pair(original,'Mar2017 otherunit.'))
        self.assertEqual('mass:kg',occurrences('since 2017 kg.')[0]['unit'])

    def test_record_boundary_does_not_erase_unit_or_partial_date_tails(self):
        for tail,expected in (('quux per second.','opaque:quux'),('kg · 2014','mass:kg'),('quux · 2014kg','opaque:quux')):
            with self.subTest(tail=tail):
                self.assertEqual(expected,occurrences('2011 - 2017\n'+tail)[1]['unit'])

    def test_coverage_preserves_boundaries_between_separate_date_and_prose_spans(self):
        from career.policy import mechanical_review
        original='март2017—август2018.'
        spans=['Mar 2017 - Aug 2018','Developed an interface.']
        claim=dict(id='claim_dates',assertion=original,meaning=original,confirmation='confirmed',disclosure='allowed',contradicted=False)
        review=dict(findings='Compared synthetic dates.',limitations='No semantic truth guarantee.',tone_findings='Fixture.',
            claim_spans=[dict(claim_id=claim['id'],text=text) for text in spans],coverage=[dict(claim_id=claim['id'],disposition='included')])
        self.assertFalse(mechanical_review([dict(slot='resume',text='\n- '.join(spans))],[claim],review))

    def test_calendar_year_coverage_retains_start_year_with_supported_month_detail(self):
        from career.policy import mechanical_review
        original='Опыт с 2017 года.'
        text='Aug 2017 - Mar 2018.'
        claim=dict(id='claim_dates',assertion=original,meaning='Original period: '+text,confirmation='confirmed',disclosure='allowed',contradicted=False)
        review=dict(findings='Compared synthetic original month detail.',limitations='No semantic truth guarantee.',tone_findings='Fixture.',
            claim_spans=[dict(claim_id=claim['id'],text=text)],coverage=[dict(claim_id=claim['id'],disposition='included')])
        self.assertFalse(mechanical_review([dict(slot='resume',text=text)],[claim],review))
        claim['meaning']=original
        self.assertTrue(mechanical_review([dict(slot='resume',text=text)],[claim],review))

    def test_calendar_clause_punctuation_does_not_attach_following_department_names(self):
        self.assertFalse(review_pair('с мая2022,frontend/backend group.','since May 2022.'))

    def test_scoped_names_and_big_o_do_not_authorize_unrelated_counts(self):
        self.assertFalse(review_pair('Complexity O(1).','Complexity O(1).'))
        self.assertTrue(review_pair('Complexity O(1).','Complexity O(2).'))
        self.assertTrue(review_pair('At 1inch.','At 1inch. Managed 1 engineer.'))


if __name__=='__main__':unittest.main(verbosity=2)
