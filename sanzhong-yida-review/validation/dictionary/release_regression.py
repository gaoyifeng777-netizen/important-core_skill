"""Release boundary regressions using invented data (Python 3.10+, stdlib).

Run from any directory. --skill-root may point to a read-only older package to
verify that the negative cases expose the original defects. Temporary inputs
are removed automatically; reports contain no machine-specific source paths.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
OMITTED = object()


def fixture(dictionary_version):
    fields = ('meeting_identity', 'meeting_time', 'agenda', 'notice_issued_at', 'change')
    return {
        'schema_version': '1.1', 'dictionary_version': dictionary_version,
        'prompt_version': '1.2', 'task_id': 'TEST-T1', 'run_id': 'TEST-RUN1',
        'agent_name': 'meeting_schedule', 'meeting_package_id': 'TEST-P1',
        'status': 'completed',
        'coverage': [{'file_id': 'F1', 'assigned_scope': 'all', 'processed_scope': 'all',
                      'unprocessed_scope': None, 'read_status': 'read', 'note': None}],
        'subjects': [{'subject_ref': 'S1', 'file_id': 'F1', 'subject_type': 'agenda_item',
                      'title_original': 'Synthetic agenda', 'number_original': '1',
                      'locator': 'line 1'}],
        'records': [{'record_id': 'R1', 'subject_ref': 'S1', 'tags': ['agenda_item'],
                     'fact_state': 'planned', 'extracted_fact': 'Synthetic agenda',
                     'values': {'items': [{'field': 'agenda.title', 'raw': 'Synthetic agenda',
                                          'normalized': None, 'qualifiers': {},
                                          'evidence_indexes': [0]}]},
                     'evidence': [{'file_id': 'F1', 'locator': 'line 1',
                                   'quote': 'Synthetic agenda'}],
                     'related_record_ids': [], 'uncertainty': []}],
        'time_index': [],
        'field_checks': [
            {'file_id': 'F1', 'subject_ref': 'S1' if field == 'agenda' else None,
             'field': field, 'state': 'present' if field == 'agenda' else 'not_found',
             'record_ids': ['R1'] if field == 'agenda' else [],
             'reason': None if field == 'agenda' else 'The authorized source was searched.'}
            for field in fields],
        'candidate_tags': [], 'requests': [], 'completion_note': 'Synthetic regression.'}


def task_for(data):
    return {**{key: data[key] for key in ('task_id', 'run_id', 'agent_name', 'meeting_package_id')},
            'files': [{'file_id': 'F1', 'assigned_scope': 'all'}]}


def cases(version):
    """Literal expectations test public validation behavior, not source text."""
    result = []

    def add(name, edit=None, task=OMITTED, ok=False, error=None, raw_result=None, raw_task=None):
        data = fixture(version)
        if edit:
            edit(data)
        result.append({'name': name, 'data': data, 'task': task, 'ok': ok,
                       'error': error, 'raw_result': raw_result, 'raw_task': raw_task})

    add('valid_existing_payload', task=task_for(fixture(version)), ok=True)
    add('other_tag_remains_legal', lambda d: d['records'][0].update(tags=['other']), ok=True)
    for name, value in [('null', None), ('list', []), ('string', 'invalid'),
                        ('number', 0), ('boolean', True)]:
        add('task_top_' + name, task=value, error='task: invalid object')
    for name, value in [('null', None), ('string', 'invalid'), ('object', {}), ('number', 3)]:
        task = task_for(fixture(version)); task['files'] = value
        add('task_files_' + name, task=task, error='task.files')
    task = task_for(fixture(version)); del task['files']
    add('task_files_missing', task=task, error='task.files')
    for name, value in [('null', None), ('string', 'F1'), ('list', []), ('number', 1)]:
        task = task_for(fixture(version)); task['files'] = [value]
        add('task_file_' + name, task=task, error='task.files[0]')
    for field in ('file_id', 'assigned_scope'):
        task = task_for(fixture(version)); del task['files'][0][field]
        add('task_file_missing_' + field, task=task, error=field)
        for name, value in [('whitespace', ' \t\n'), ('empty', ''), ('list', [])]:
            task = task_for(fixture(version)); task['files'][0][field] = value
            add('task_file_' + field + '_' + name, task=task, error=field)
    task = task_for(fixture(version)); task['files'].append(dict(task['files'][0], path='second.txt'))
    add('duplicate_task_file_id', task=task, error='duplicate file_id')

    def duplicate_check(data, first_scope=OMITTED, second_scope=OMITTED, state='not_found'):
        first = data['field_checks'][2]
        if first_scope is not OMITTED:
            first['search_scope'] = first_scope
        other = copy.deepcopy(first)
        other.update(state=state, record_ids=[], reason='The stated local range was searched.')
        if second_scope is not OMITTED:
            other['search_scope'] = second_scope
        data['field_checks'].append(other)

    add('conflicting_same_check', duplicate_check, error='conflicting field_checks')
    add('conflicting_same_explicit_scope', lambda d: duplicate_check(d, 'line 1', 'line 1'),
        error='conflicting field_checks')
    add('conflicting_default_and_explicit_scope', lambda d: duplicate_check(d, OMITTED, 'all'),
        error='conflicting field_checks')
    add('different_local_scopes_are_allowed', lambda d: duplicate_check(d, 'line 1', 'line 2'), ok=True)

    def partial_scopes(data):
        data['status'] = 'partial'
        data['coverage'][0].update(read_status='partial', processed_scope='line 1',
                                   unprocessed_scope='line 2', note='Second local range not read.')
        duplicate_check(data, 'line 1', 'line 2', 'not_read')

    add('partial_different_local_scopes_are_allowed', partial_scopes, ok=True)

    def different_subject(data):
        data['subjects'].append(dict(data['subjects'][0], subject_ref='S2', locator='line 2'))
        duplicate_check(data)
        data['field_checks'][-1]['subject_ref'] = 'S2'

    add('different_subject_checks_are_allowed', different_subject, ok=True)
    add('blank_search_scope', lambda d: d['field_checks'][2].update(search_scope=' \t'), error='search_scope')
    add('blank_record_id', lambda d: (d['records'][0].update(record_id=' \t'),
                                    d['field_checks'][2].update(record_ids=[' \t'])), error='record_id')
    add('blank_subject_id', lambda d: (d['subjects'][0].update(subject_ref=' \t'),
                                     d['records'][0].update(subject_ref=' \t'),
                                     d['field_checks'][2].update(subject_ref=' \t')), error='subject_ref')
    add('blank_coverage_file_id', lambda d: d['coverage'][0].update(file_id=' \t'), error='file_id')
    add('blank_assigned_scope', lambda d: d['coverage'][0].update(assigned_scope=' \t'), error='assigned_scope')
    add('blank_processed_scope', lambda d: d['coverage'][0].update(processed_scope=' \t'), error='processed_scope')
    add('blank_unprocessed_scope', lambda d: d['coverage'][0].update(unprocessed_scope=' \t'), error='unprocessed_scope')
    add('blank_subject_locator', lambda d: d['subjects'][0].update(locator=' \t'), error='locator')
    add('blank_nonpresent_reason', lambda d: d['field_checks'][0].update(reason=' \t'), error='reason')
    add('blank_request_file_id', lambda d: d['requests'].append(
        {'file_id': ' \t', 'reason': 'Additional record needed.', 'needed_input': 'A synthetic attachment.'}),
        error='file_id')
    add('blank_blocked_identity', lambda d: d.update(status='blocked', run_id=' \t'), error='run_id')

    def other_fact(data, request=None):
        data['records'][0]['values']['items'][0]['field'] = 'fact.other'
        if request is not None:
            data['requests'].append(request)

    extension = {'file_id': 'F1', 'reason': 'The fact type is not in the dictionary.',
                 'needed_input': 'Review a dictionary extension for this source fact.',
                 'request_type': 'dictionary_extension', 'record_ids': ['R1']}
    add('fact_other_requires_extension', other_fact, error='dictionary_extension')
    add('fact_other_with_extension_is_allowed', lambda d: other_fact(d, copy.deepcopy(extension)), ok=True)
    add('fact_other_unrelated_request_not_sufficient', lambda d: other_fact(d, {
        'file_id': 'F1', 'reason': 'Missing attachment.', 'needed_input': 'Provide the attachment.'}),
        error='dictionary_extension')
    add('fact_other_unreferenced_extension_not_sufficient',
        lambda d: other_fact(d, dict(extension, record_ids=[])), error='record_ids')
    add('fact_other_foreign_record_reference_rejected',
        lambda d: other_fact(d, dict(extension, record_ids=['R999'])), error='record_ids')
    add('fact_other_missing_request_record_ids',
        lambda d: other_fact(d, {k: v for k, v in extension.items() if k != 'record_ids'}), error='record_ids')
    add('fact_other_extension_file_must_match_record',
        lambda d: other_fact(d, dict(extension, file_id='F2')), error='dictionary_extension')
    add('fact_other_global_extension_is_allowed',
        lambda d: other_fact(d, dict(extension, file_id=None)), ok=True)
    add('legacy_material_request_is_allowed', lambda d: d['requests'].append({
        'file_id': None, 'reason': 'Missing attachment.', 'needed_input': 'Provide the attachment.'}), ok=True)
    add('wrong_dictionary_version', lambda d: d.update(dictionary_version='unsupported'), error='dictionary_version')

    raw = json.dumps(fixture(version), ensure_ascii=False)
    add('duplicate_result_top_key', raw_result=raw[:-1] + ',"status":"completed"}', error='duplicate JSON')
    add('duplicate_result_nested_key', raw_result=raw.replace('"file_id": "F1"',
        '"file_id": "F0", "file_id": "F1"', 1), error='duplicate JSON')
    raw = json.dumps(task_for(fixture(version)), ensure_ascii=False)
    add('duplicate_task_key', task=task_for(fixture(version)),
        raw_task=raw[:-1] + ',"task_id":"TEST-T1"}', error='duplicate JSON')
    return result


def matches(errors, case):
    return (not errors) if case['ok'] else bool(errors) and (
        case['error'] is None or any(case['error'] in error for error in errors))


def run(root):
    sys.path.insert(0, str(root / 'scripts'))
    spec = importlib.util.spec_from_file_location('release_target_validator', root / 'scripts/validate_result.py')
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    dictionary = json.loads((root / 'references/fact_dictionary.json').read_text(encoding='utf-8'))
    version = dictionary['dictionary_version']
    rows = []
    temporary_parent = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='skill-release-regression-', dir=temporary_parent) as temporary:
        if Path(temporary).resolve().parent != temporary_parent.resolve():
            raise RuntimeError('Temporary directory is outside the regression directory')
        result_path, task_path = Path(temporary) / 'result.json', Path(temporary) / 'task.json'
        for case in cases(version):
            row = {'name': case['name'], 'expected_ok': case['ok']}
            if case['raw_result'] is None and case['raw_task'] is None:
                try:
                    errors = validator.validate(case['data']) if case['task'] is OMITTED else validator.validate(
                        case['data'], case['task'])
                    row['function_passed'] = isinstance(errors, list) and matches(errors, case)
                    if not row['function_passed']:
                        row['function_errors'] = errors
                except Exception as exc:  # A test observation, not production exception suppression.
                    row['function_passed'] = False
                    row['function_exception'] = type(exc).__name__
            else:
                row['function_passed'] = None  # A dict cannot retain duplicate JSON object keys.
            result_path.write_text(case['raw_result'] or json.dumps(case['data'], ensure_ascii=False), encoding='utf-8')
            command = [sys.executable, '-B', '-X', 'utf8', str(root / 'scripts/validate_result.py'), str(result_path)]
            if case['task'] is not OMITTED:
                task_path.write_text(case['raw_task'] or json.dumps(case['task'], ensure_ascii=False), encoding='utf-8')
                command += ['--task', str(task_path)]
            completed = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=30)
            try:
                output = json.loads(completed.stdout)
                row['cli_passed'] = (completed.returncode == (0 if case['ok'] else 1)
                                     and not completed.stderr
                                     and isinstance(output, dict)
                                     and output.get('ok') is case['ok']
                                     and isinstance(output.get('errors'), list)
                                     and isinstance(output.get('scope'), str)
                                     and matches(output['errors'], case))
                if not row['cli_passed']:
                    row['cli_errors'] = output.get('errors') if isinstance(output, dict) else ['not an object']
            except (ValueError, TypeError):
                row['cli_passed'] = False
                row['cli_error'] = 'stdout is not the expected error JSON'
            row['cli_traceback'] = 'Traceback' in completed.stderr
            row['passed'] = row['cli_passed'] and row['function_passed'] is not False
            rows.append(row)
    legacy_suites = []
    for filename, expected_count in (('validator_regression.py', 16), ('dictionary_regression.py', 18)):
        completed = subprocess.run(
            [sys.executable, '-B', '-X', 'utf8', str(root / 'validation/dictionary' / filename)],
            capture_output=True, text=True, encoding='utf-8', timeout=30)
        count = re.search(r'Ran (\d+) tests?', completed.stdout + '\n' + completed.stderr)
        count = int(count.group(1)) if count else None
        legacy_suites.append({'suite': filename, 'test_count': count,
                              'passed': completed.returncode == 0 and count == expected_count})
    return {'verified_at_utc': datetime.now(timezone.utc).isoformat(),
            'case_count': len(rows), 'passed_count': sum(row['passed'] for row in rows),
            'failed_count': sum(not row['passed'] for row in rows),
            'function_case_count': sum(row['function_passed'] is not None for row in rows),
            'cli_case_count': len(rows), 'dictionary_version': version,
            'legacy_suites': legacy_suites,
            'overall_ok': all(row['passed'] for row in rows) and all(suite['passed'] for suite in legacy_suites),
            'validator_sha256': hashlib.sha256((root / 'scripts/validate_result.py').read_bytes()).hexdigest(),
            'cases': rows,
            'limits': 'Synthetic structure/reference tests only; no factual accuracy, OCR, source authenticity or access isolation claim.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skill-root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--report', type=Path)
    parser.add_argument('--phase', choices=('before', 'after'), default='after')
    args = parser.parse_args()
    report = run(args.skill_root.resolve())
    if args.report:
        previous = json.loads(args.report.read_text(encoding='utf-8')) if args.report.exists() else {}
        previous[args.phase] = report
        args.report.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'cases'}, ensure_ascii=False, indent=2))
    for row in report['cases']:
        if not row['passed']:
            print('FAIL ' + row['name'])
    return 0 if report['overall_ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
