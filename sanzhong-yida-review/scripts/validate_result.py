"""Validate this prompt pack's JSON structure and cross-references (stdlib only)."""
import argparse
import json
from pathlib import Path
import re
import sys
from dictionary_checks import validate_dictionary

TASK_OMITTED = object()


def nonblank(value):
    return isinstance(value, str) and bool(value.strip())


def unique_object(pairs):
    """Reject duplicate keys before a JSON parser can silently discard them."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON object key: {key!r}')
        result[key] = value
    return result


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=unique_object)


def task_check(task):
    """Validate the consumed task fields before building any source index."""
    if not isinstance(task, dict):
        return ['task: invalid object; expected an input object']
    errors = []
    for key in ('task_id', 'run_id', 'agent_name', 'meeting_package_id'):
        if not nonblank(task.get(key)):
            errors.append(f'task: invalid {key}; nonblank string required')
    files = task.get('files')
    if not isinstance(files, list):
        errors.append('task.files: expected an array')
        return errors
    seen = set()
    for position, source in enumerate(files):
        at = f'task.files[{position}]'
        if not isinstance(source, dict):
            errors.append(f'{at}: expected an object')
            continue
        for key in ('file_id', 'assigned_scope'):
            if not nonblank(source.get(key)):
                errors.append(f'{at}: invalid {key}; nonblank string required')
        fid = source.get('file_id')
        if nonblank(fid):
            if fid in seen:
                errors.append(f'{at}: duplicate file_id: {fid!r}')
            seen.add(fid)
    return errors


def schema_check(value, schema, at, errors):
    types = schema.get('type')
    types = [types] if isinstance(types, str) else types
    matches = {
        'object': isinstance(value, dict), 'array': isinstance(value, list),
        'string': isinstance(value, str), 'null': value is None,
        'number': isinstance(value, (int, float)) and not isinstance(value, bool),
        'integer': isinstance(value, int) and not isinstance(value, bool),
        'boolean': isinstance(value, bool)
    }
    if types and not any(matches.get(t, False) for t in types):
        errors.append(f'{at}: invalid type; expected {types}')
        return
    if 'enum' in schema and value not in schema['enum']:
        errors.append(f'{at}: invalid enum {value!r}')
    if isinstance(value, str) and 'pattern' in schema and not re.search(schema['pattern'], value):
        errors.append(f'{at}: nonblank string required')
    if isinstance(value, dict):
        props = schema.get('properties', {})
        for name in schema.get('required', []):
            if name not in value:
                errors.append(f'{at}: missing {name}')
        for key, val in value.items():
            if key in props:
                schema_check(val, props[key], f'{at}.{key}', errors)
            elif schema.get('additionalProperties') is False:
                errors.append(f'{at}: unexpected key {key}')
    if isinstance(value, list) and 'items' in schema:
        for i, val in enumerate(value):
            schema_check(val, schema['items'], f'{at}[{i}]', errors)


def validate(data, task=TASK_OMITTED):
    base = Path(__file__).resolve().parent
    schema = load_json(base/'output_schema.json')
    contracts = load_json(base/'role_contracts.json')
    dictionary = load_json(base.parent/'references/fact_dictionary.json')
    # The installed dictionary is authoritative; never silently accept an older
    # meaning merely because the extraction envelope keeps the same version.
    schema['properties']['dictionary_version']['enum'] = [dictionary['dictionary_version']]
    errors = []
    schema_check(data, schema, '$', errors)
    if task is not TASK_OMITTED:
        errors.extend(task_check(task))
    if errors:
        return errors
    role = contracts[data['agent_name']]

    def index(rows, field, name):
        result = {}
        for row in rows:
            key = row[field]
            if not nonblank(key) or key in result:
                errors.append(f'{name}: empty or duplicate {field}: {key!r}')
            result[key] = row
        return result

    coverage = index(data['coverage'], 'file_id', 'coverage')
    subjects = index(data['subjects'], 'subject_ref', 'subjects')
    records = index(data['records'], 'record_id', 'records')
    if data['status'] in ('completed', 'partial'):
        for key in ('task_id', 'run_id', 'meeting_package_id'):
            if not isinstance(data[key], str) or not data[key].strip():
                errors.append(f'{key}: required for completed/partial')
    else:
        for key in ('task_id', 'run_id', 'meeting_package_id'):
            if data[key] is not None and not nonblank(data[key]):
                errors.append(f'{key}: use a nonblank identity or null when unavailable')
    if task is not TASK_OMITTED:
        for key in ('task_id', 'run_id', 'agent_name', 'meeting_package_id'):
            if data[key] != task.get(key):
                errors.append(f'identity mismatch: {key}')
        files = {f['file_id']: f for f in task.get('files', [])}
        if set(coverage) != set(files):
            errors.append('coverage does not match assigned file_ids')
        for fid in set(coverage) & set(files):
            if coverage[fid]['assigned_scope'] != files[fid]['assigned_scope']:
                errors.append(f'{fid}: assigned_scope differs from task')
    for fid, c in coverage.items():
        if c['read_status'] in ('read','partial') and not nonblank(c['processed_scope']):
            errors.append(f'{fid}: processed_scope required')
        if c['read_status'] != 'read' and not (nonblank(c['note']) or nonblank(c['unprocessed_scope'])):
            errors.append(f'{fid}: explain incomplete processing')
        if data['status'] == 'completed' and (c['read_status'] != 'read' or c['unprocessed_scope']):
            errors.append(f'{fid}: incomplete scope cannot be completed')
    if data['status'] == 'completed' and not coverage:
        errors.append('completed requires nonempty coverage')
    for sid, s in subjects.items():
        if s['file_id'] not in coverage or not nonblank(s['locator']):
            errors.append(f'{sid}: unknown source or missing locator')
    for rid, r in records.items():
        subject = subjects.get(r['subject_ref'])
        if r['subject_ref'] not in subjects:
            errors.append(f'{rid}: unknown subject_ref')
        if not r['tags'] or not set(r['tags']) <= set(role['tags']):
            errors.append(f'{rid}: invalid role tags')
        if not r['extracted_fact'].strip() or not r['evidence']:
            errors.append(f'{rid}: fact and evidence are required')
        for e in r['evidence']:
            if subject is not None and e['file_id'] != subject['file_id']:
                errors.append(f'{rid}: evidence does not belong to subject file')
            if e['file_id'] not in coverage or not e['locator'].strip() or not e['quote'].strip():
                errors.append(f'{rid}: invalid evidence')
            elif coverage[e['file_id']]['read_status'] not in ('read','partial'):
                errors.append(f'{rid}: evidence from an unread or excluded file')
        for rel in r['related_record_ids']:
            if rel not in records or rel == rid:
                errors.append(f'{rid}: invalid related_record_id {rel}')
    for ti in data['time_index']:
        if ti['record_id'] not in records or not ti['raw'].strip():
            errors.append('time_index: missing fact or raw time')
    checked = {fid:set() for fid in coverage}
    check_states = {}
    for check in data['field_checks']:
        fid = check['file_id']
        if fid not in coverage:
            errors.append('field_checks: unknown file_id')
            continue
        if check['field'] not in role['fields']:
            errors.append(f'{fid}: unknown mandatory field {check["field"]}')
        checked[fid].add(check['field'])
        # Scope strings are identifiers supplied by the producer. This tests
        # equality only; it does not prove range containment or actual reading.
        scope = check.get('search_scope', coverage[fid]['processed_scope'] or coverage[fid]['assigned_scope'])
        key = (fid, check['subject_ref'], check['field'], scope.strip())
        if key in check_states and check_states[key] != check['state']:
            errors.append(f'{fid}: conflicting field_checks for the same subject, field and search_scope')
        check_states[key] = check['state']
        if check['subject_ref'] is not None:
            subject = subjects.get(check['subject_ref'])
            if subject is None:
                errors.append(f'{fid}: field_check subject not found')
            elif subject['file_id'] != fid:
                errors.append(f'{fid}: field_check subject belongs to another file')
        for rid in check['record_ids']:
            record = records.get(rid)
            if record is None:
                errors.append(f'{fid}: field_check record not found')
                continue
            record_subject = subjects.get(record['subject_ref'])
            if (record_subject is not None and record_subject['file_id'] != fid) or not any(
                    e['file_id'] == fid for e in record['evidence']):
                errors.append(f'{fid}: field_check record belongs to another file: {rid}')
            if check['subject_ref'] is not None and record['subject_ref'] != check['subject_ref']:
                errors.append(f'{fid}: field_check record belongs to another subject: {rid}')
        if data['status'] == 'completed' and check['state'] in ('not_read', 'unreadable', 'not_provided'):
            errors.append(f'{fid}: incomplete field cannot be completed: {check["field"]}')
        if check['state'] == 'present' and not check['record_ids']:
            errors.append(f'{fid}: present requires record_ids')
        if check['state'] != 'present' and not nonblank(check['reason']):
            errors.append(f'{fid}: non-present requires reason')
        if check['state'] == 'not_found' and coverage[fid]['read_status'] != 'read' and not nonblank(check['reason']):
            errors.append(f'{fid}: not_found requires a stated completed search scope')
    if data['status'] in ('completed','partial'):
        for fid, seen in checked.items():
            missing = set(role['fields']) - seen
            if missing:
                errors.append(f'{fid}: missing field checks {sorted(missing)}')
    for c in data['candidate_tags']:
        if not nonblank(c['name']) or not nonblank(c['definition']) or any(r not in records for r in c['record_ids']):
            errors.append('candidate_tags: invalid suggestion or reference')
    for request in data['requests']:
        refs = request.get('record_ids', [])
        if any(rid not in records for rid in refs):
            errors.append('requests.record_ids: unknown record reference')
        if len(refs) != len(set(refs)):
            errors.append('requests.record_ids: duplicate record reference')
        if request.get('request_type') == 'dictionary_extension' and not refs:
            errors.append('requests.record_ids: dictionary_extension requires record references')
    if data['status'] in ('blocked','failed') and not (data['requests'] or data['completion_note']):
        errors.append('blocked/failed must explain what is needed')
    errors.extend(validate_dictionary(data, dictionary))
    return errors

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('result')
    p.add_argument('--task')
    args = p.parse_args()
    try:
        data = load_json(args.result)
        task = load_json(args.task) if args.task else TASK_OMITTED
        errors = validate(data, task)
    except (ValueError, OSError, TypeError) as exc:
        errors = [str(exc)]
    print(json.dumps({'ok':not errors, 'errors':errors,
                      'scope':'structure and references only; factual accuracy and isolation not proven'},
                     ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == '__main__':
    sys.exit(main())
