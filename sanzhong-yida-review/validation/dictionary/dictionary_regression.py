"""Field, evidence, amount and time-index regressions using invented data."""
import copy
from pathlib import Path
import sys
import unittest
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from validate_result import validate
from validator_regression import fixture, add_record, present_check


def value_fixture(field='agenda.title', raw='Synthetic agenda', normalized=None, qualifiers=None):
    data=fixture()
    add_record(data)
    present_check(data,'F1','S1','R1')
    item={'field':field,'raw':raw,'normalized':normalized,'qualifiers':qualifiers or {},'evidence_indexes':[0]}
    data['records'][0]['values']['items']=[item]
    data['records'][0]['evidence'][0]['quote']=raw
    return data

def amount_fixture():
    return value_fixture('financial.amount','人民币100万元','100',{
        'currency':'CNY','unit':'万元','amount_basis':'申请金额','scope_raw':'A项目一期',
        'tax_basis':'unknown','bound':'exact','stage':'requested'})

def date_fixture(raw='2025年9月10日', normalized='2025-09-10', precision='date'):
    data=value_fixture('meeting.time',raw,normalized,{'precision':precision})
    data['time_index']=[{'record_id':'R1','item_index':0,'event_type':'meeting_time',
                         'raw':raw,'normalized':normalized,'precision':precision}]
    return data

class DictionaryRegression(unittest.TestCase):
    def assert_bad(self,data,contains):
        errors=validate(data)
        self.assertTrue(any(contains in e for e in errors),errors)

    def test_valid_text_and_amount(self):
        self.assertEqual(validate(value_fixture()),[])
        self.assertEqual(validate(amount_fixture()),[])

    def test_unknown_field_is_rejected(self):
        self.assert_bad(value_fixture('actor'), 'invalid enum')

    def test_disallowed_role_is_rejected(self):
        self.assert_bad(value_fixture('approval.action'),'not allowed for role')

    def test_missing_dictionary_version_is_rejected(self):
        data=value_fixture(); del data['dictionary_version']
        self.assert_bad(data,'missing dictionary_version')

    def test_empty_items_do_not_masquerade_as_normalized(self):
        data=value_fixture(); data['records'][0]['values']['items']=[]
        self.assert_bad(data,'must contain')

    def test_evidence_pointer_and_raw_are_checked(self):
        data=value_fixture(); data['records'][0]['values']['items'][0]['evidence_indexes']=[8]
        self.assert_bad(data,'out of range')
        data=value_fixture(); data['records'][0]['values']['items'][0]['raw']='Not quoted'
        self.assert_bad(data,'continuous excerpt')

    def test_qualifiers_cannot_hide_cross_role_judgments(self):
        data=amount_fixture(); data['records'][0]['values']['items'][0]['qualifiers']['compliant']=True
        self.assert_bad(data,'qualifier keys')

    def test_unknown_unit_is_not_assumed(self):
        data=amount_fixture(); data['records'][0]['values']['items'][0]['qualifiers']['unit']='人民币'
        self.assert_bad(data,'unknown enum')

    def test_numeric_specials_and_ranges_are_rejected(self):
        for number in ('NaN','Infinity','1e6','1,000'):
            data=amount_fixture(); data['records'][0]['values']['items'][0]['normalized']=number
            self.assert_bad(data,'numeric normalization')
        data=amount_fixture(); data['records'][0]['values']['items'][0]['qualifiers']['bound']='range'
        self.assert_bad(data,'range amount')

    def test_null_and_zero_are_distinct(self):
        data=amount_fixture(); data['records'][0]['values']['items'][0]['normalized']=None
        self.assertEqual(validate(data),[])
        data=amount_fixture(); item=data['records'][0]['values']['items'][0]
        item.update(raw='人民币0万元',normalized='0'); data['records'][0]['evidence'][0]['quote']=item['raw']
        self.assertEqual(validate(data),[])

    def test_valid_date(self):
        self.assertEqual(validate(date_fixture()),[])

    def test_missing_year_must_remain_null(self):
        self.assertEqual(validate(date_fixture('9月10日',None)),[])
        self.assert_bad(date_fixture('9月10日','2025-09-10'),'year absent')

    def test_no_invented_time_or_day(self):
        self.assert_bad(date_fixture(normalized='2025-09-10T09:00'),'exceeds precision')
        self.assert_bad(date_fixture('2025年9月','2025-09-01','month'),'exceeds precision')

    def test_invalid_calendar_date(self):
        self.assert_bad(date_fixture('2025年2月30日','2025-02-30'),'invalid format')

    def test_missing_duplicate_or_changed_time_index(self):
        data=date_fixture(); data['time_index']=[]
        self.assert_bad(data,'missing date dictionary items')
        data=date_fixture(); data['time_index'].append(copy.deepcopy(data['time_index'][0]))
        self.assert_bad(data,'duplicate dictionary')
        data=date_fixture(); data['time_index'][0]['normalized']='2025-09-11'
        self.assert_bad(data,'indexed values differ')

    def test_time_index_cannot_point_to_nondate(self):
        data=value_fixture(); data['time_index']=date_fixture()['time_index']
        self.assert_bad(data,'reference must point to a date')

    def test_legacy_schema_does_not_silently_pass(self):
        data=value_fixture(); data['schema_version']='1.0'
        self.assert_bad(data,'invalid enum')

    def test_validation_does_not_mutate_input(self):
        data=amount_fixture(); before=copy.deepcopy(data)
        validate(data)
        self.assertEqual(data,before)

if __name__=='__main__': unittest.main(verbosity=2)
