"""Synthetic regression tests for identity, ownership and completion checks.

Run with Python from any directory. No customer files are read or written.
Negative tests require the targeted structural error, even when independent
dictionary validation also rejects the intentionally minimal values.items.
"""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.spec_from_file_location(
    'regression_validate_result', ROOT / 'scripts' / 'validate_result.py')
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)
SCHEMA = json.loads((ROOT / 'scripts' / 'output_schema.json').read_text(encoding='utf-8'))
SCHEMA_VERSION = SCHEMA['properties']['schema_version']['enum'][0]
DICTIONARY_VERSION = json.loads((ROOT / 'references' / 'fact_dictionary.json').read_text(
    encoding='utf-8'))['dictionary_version']
FIELDS = ('meeting_identity', 'meeting_time', 'agenda', 'notice_issued_at', 'change')
IDENTITIES = ('task_id', 'run_id', 'meeting_package_id')


def fixture():
    """A fully examined synthetic source with no identifiable business facts."""
    data = {
        'schema_version': SCHEMA_VERSION, 'dictionary_version': DICTIONARY_VERSION, 'prompt_version': '1.2',
        'task_id': 'TEST-T1', 'run_id': 'TEST-RUN1',
        'agent_name': 'meeting_schedule', 'meeting_package_id': 'TEST-P1',
        'status': 'completed', 'coverage': [], 'subjects': [], 'records': [],
        'time_index': [], 'field_checks': [], 'candidate_tags': [],
        'requests': [], 'completion_note': 'Synthetic structural regression only.'
    }
    for fid in ('F1', 'F2'):
        data['coverage'].append({
            'file_id': fid, 'assigned_scope': 'all', 'processed_scope': 'all',
            'unprocessed_scope': None, 'read_status': 'read', 'note': None})
        for field in FIELDS:
            data['field_checks'].append({
                'file_id': fid, 'subject_ref': None, 'field': field,
                'state': 'not_found', 'record_ids': [],
                'reason': 'Full authorized synthetic source searched; field absent.'})
    return data


def task_for(data):
    return {
        **{key: data[key] for key in (*IDENTITIES, 'agent_name')},
        'files': [{'file_id': c['file_id'], 'assigned_scope': c['assigned_scope']}
                  for c in data['coverage']]
    }


def add_record(data, fid='F1', sid='S1', rid='R1'):
    data['subjects'].append({
        'subject_ref': sid, 'file_id': fid, 'subject_type': 'agenda_item',
        'title_original': 'Synthetic agenda', 'number_original': '1',
        'locator': 'line 1'})
    data['records'].append({
        'record_id': rid, 'subject_ref': sid, 'tags': ['agenda_item'],
        'fact_state': 'planned', 'extracted_fact': 'The synthetic notice lists an agenda.',
        'values': {'items': [{'field':'agenda.title','raw':'Synthetic agenda','normalized':None,'qualifiers':{},'evidence_indexes':[0]}]},
        'evidence': [{'file_id': fid, 'locator': 'line 1', 'quote': 'Synthetic agenda'}],
        'related_record_ids': [], 'uncertainty': []})


def present_check(data, fid, sid, rid):
    check = next(c for c in data['field_checks']
                 if c['file_id'] == fid and c['field'] == 'agenda')
    check.update(subject_ref=sid, state='present', record_ids=[rid], reason=None)


class StructuralRegression(unittest.TestCase):
    def assert_error(self, data, fragment, task=None):
        errors = VALIDATOR.validate(data) if task is None else VALIDATOR.validate(data, task)
        self.assertTrue(any(fragment in error for error in errors),
                        f'Expected {fragment!r}; actual errors: {errors!r}')

    def test_valid_completed_not_found_is_allowed(self):
        data = fixture()
        self.assertEqual(VALIDATOR.validate(data, task_for(data)), [])

    def test_cross_file_subject_cannot_support_a_field_check(self):
        data = fixture()
        add_record(data)
        present_check(data, 'F2', 'S1', 'R1')
        self.assert_error(data, 'field_check subject belongs to another file')

    def test_cross_file_record_cannot_support_file_level_check(self):
        data = fixture()
        add_record(data)
        present_check(data, 'F2', None, 'R1')
        self.assert_error(data, 'field_check record belongs to another file')

    def test_same_file_record_must_belong_to_checked_subject(self):
        data = fixture()
        add_record(data)
        data['subjects'].append({
            **data['subjects'][0], 'subject_ref': 'S2', 'title_original': 'Another agenda'})
        present_check(data, 'F1', 'S2', 'R1')
        self.assert_error(data, 'field_check record belongs to another subject')

    def test_record_evidence_must_belong_to_its_source_local_subject(self):
        data = fixture()
        add_record(data)
        data['records'][0]['evidence'][0]['file_id'] = 'F2'
        self.assert_error(data, 'evidence does not belong to subject file')

    def test_matching_record_is_not_rejected_by_ownership_checks(self):
        data = fixture()
        add_record(data)
        present_check(data, 'F1', 'S1', 'R1')
        errors = VALIDATOR.validate(data, task_for(data))
        # The independent dictionary layer can reject the empty items fixture.
        # This test does not claim that dictionary validation passed.
        ownership_errors = [e for e in errors if
                            'field_check' in e or 'subject file' in e or e.startswith('$')]
        self.assertEqual(ownership_errors, [])

    def test_completed_rejects_unprocessed_mandatory_fields(self):
        for state in ('not_read', 'unreadable', 'not_provided'):
            with self.subTest(state=state):
                data = fixture()
                data['field_checks'][0].update(state=state, reason='Synthetic unfinished field.')
                self.assert_error(data, 'incomplete field cannot be completed')

    def test_partial_can_report_unprocessed_fields(self):
        data = fixture()
        data['status'] = 'partial'
        data['coverage'][0].update(read_status='partial', processed_scope='line 1',
                                   unprocessed_scope='line 2', note='Synthetic unread part.')
        data['field_checks'][0].update(state='not_read', reason='Synthetic unread field.')
        self.assertEqual(VALIDATOR.validate(data, task_for(data)), [])

    def test_completed_allows_examined_uncertainty_and_out_of_scope_fields(self):
        for state in ('not_found', 'ambiguous', 'not_in_scope'):
            with self.subTest(state=state):
                data = fixture()
                data['field_checks'][0].update(state=state, reason='Synthetic documented limit.')
                self.assertEqual(VALIDATOR.validate(data), [])

    def test_usable_results_require_nonblank_identities(self):
        for status in ('completed', 'partial'):
            for key in IDENTITIES:
                for missing in (None, '', '   '):
                    with self.subTest(status=status, key=key, missing=missing):
                        data = fixture()
                        data['status'] = status
                        data[key] = missing
                        self.assert_error(data, f'{key}: required for completed/partial')

    def test_empty_task_is_not_silently_treated_as_omitted(self):
        self.assert_error(fixture(), 'task: invalid', task={})

    def test_provided_task_requires_valid_identities(self):
        for key in (*IDENTITIES, 'agent_name'):
            for missing in (None, '', '   '):
                with self.subTest(key=key, missing=missing):
                    data = fixture()
                    task = task_for(data)
                    task[key] = missing
                    self.assert_error(data, f'task: invalid {key}', task=task)

    def test_nonobject_task_returns_an_error_instead_of_crashing(self):
        for task in ([], ['invalid'], 'invalid', 0):
            with self.subTest(task=task):
                self.assert_error(fixture(), 'task: invalid object', task=task)

    def test_valid_but_mismatched_task_identity_remains_rejected(self):
        data = fixture()
        task = task_for(data)
        task['run_id'] = 'OTHER-RUN'
        self.assert_error(data, 'identity mismatch: run_id', task=task)

    def test_blocked_can_report_missing_identity_without_a_task(self):
        data = fixture()
        data.update(status='blocked', task_id=None, run_id=None, meeting_package_id=None,
                    coverage=[], subjects=[], records=[], field_checks=[],
                    requests=[{'file_id': None, 'reason': 'Missing task identity.',
                               'needed_input': 'Controller must supply the missing IDs.'}])
        self.assertEqual(VALIDATOR.validate(data), [])

    def test_invalid_task_does_not_relabel_blocked_result(self):
        data = fixture()
        data.update(status='blocked', task_id=None, run_id=None, meeting_package_id=None,
                    coverage=[], field_checks=[])
        before = copy.deepcopy(data)
        self.assert_error(data, 'task: invalid', task={})
        self.assertEqual(data, before)


if __name__ == '__main__':
    print(f'Synthetic structure regressions; schema {SCHEMA_VERSION}; no customer material.',
          flush=True)
    unittest.main(verbosity=2)
