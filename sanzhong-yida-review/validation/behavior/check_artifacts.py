"""Recheck saved synthetic artifacts; this command does not call a language model."""
import json
import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_result import validate


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf-8'))


def check(stage='all'):
    errors, runs = [], {}
    count = items = quotes = 0
    roles = ('meeting_schedule', 'proposal_extract', 'meeting_record', 'meeting_minutes')
    for role in roles:
        task = read(f'validation/behavior/tasks/{role}.json')
        result = read(f'validation/behavior/results/{role}.json')
        errors.extend(f'{role}: {error}' for error in validate(result, task))
        sources = {x['file_id']: (ROOT / x['path']).read_text(encoding='utf-8') for x in task['files']}
        runs[result['run_id']] = {x['record_id']: x for x in result['records']}
        for record in result['records']:
            count += 1
            items += len(record['values']['items'])
            for evidence in record['evidence']:
                quotes += 1
                if evidence['quote'] not in sources[evidence['file_id']]:
                    errors.append(f'{role}: noncontinuous evidence {record["record_id"]}')
    p = read('validation/behavior/results/proposal_extract.json')
    p_items = [i for record in p['records'] for i in record['values']['items']]
    caps = [i for i in p_items if i['field'] == 'financial.amount' and i['normalized'] == '120']
    if len(caps) != 1 or not all((caps[0]['qualifiers']['amount_basis'] == '投资上限',
            'QL-A1' in (caps[0]['qualifiers']['scope_raw'] or ''),
            caps[0]['qualifiers']['stage'] == 'requested', caps[0]['qualifiers']['bound'] == 'cap')):
        errors.append('requested investment cap qualifiers not retained')
    if any(i['field'] == 'condition.content' for i in p_items):
        errors.append('ordinary agenda opinion or analysis caveat promoted to condition')
    if stage == 'extraction':
        report = {'ok': not errors, 'stage': 'extraction_only', 'errors': errors,
                  'extraction_roles': 4, 'extraction_records': count, 'extraction_items': items,
                  'checked_quote_occurrences': quotes, 'judge_validation': 'not_run',
                  'independent_review': 'not_run',
                  'limits': 'Saved synthetic extraction artifacts only; no live replay, full judgment or independent review.'}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['ok'] else 1
    judge = read('validation/behavior/results/rule_judge.json')
    jt = read('validation/behavior/tasks/rule_judge.json')
    sources = {x['source_key']: (ROOT / x['path']).read_text(encoding='utf-8') for x in jt['source_files']}
    decisions = {x['decision_id']: x for x in judge['decisions']}
    leads = {x['lead_id']: x for x in judge['leads']}
    if (len(judge['matters']), len(decisions), len(judge['lead_scan'])) != (2, 4, 6):
        errors.append('synthetic scope coverage count mismatch')

    def walk(value):
        nonlocal quotes
        if isinstance(value, dict):
            if 'run_id' in value and 'record_id' in value:
                record = runs.get(value['run_id'], {}).get(value['record_id'])
                if record is None:
                    errors.append('unresolved extraction reference')
                elif 'item_index' in value and (not isinstance(value['item_index'], int) or
                        not 0 <= value['item_index'] < len(record['values']['items'])):
                    errors.append('invalid item reference')
            if value.get('read_state') == 'verified' and 'source_key' in value and 'quote' in value:
                quotes += 1
                if not value['quote'] or value['quote'] not in sources.get(value['source_key'], ''):
                    errors.append('noncontinuous judgment source quote')
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(judge)
    seen = set()
    for scan in judge['lead_scan']:
        unit = (scan['matter_id'], scan['rule_id'])
        if unit in seen:
            errors.append('duplicate scan unit')
        seen.add(unit)
        if 'linked_decision_ids' not in scan:
            errors.append('missing linked_decision_ids')
        linked = scan.get('linked_decision_ids', [])
        targets = scan.get('lead_ids', [])
        if scan['state'] == 'lead_found' and not (linked or targets):
            errors.append('found scan without disposition')
        if scan['state'] != 'lead_found' and (linked or targets):
            errors.append('non-triggered scan with disposition')
        for did in linked:
            if did not in decisions or decisions[did]['matter_id'] != scan['matter_id']:
                errors.append('scan linked decision missing or wrong matter')
        for lid in targets:
            if lid not in leads or leads[lid]['matter_id'] != scan['matter_id']:
                errors.append('scan linked lead missing or wrong matter')
    report = {'ok': not errors, 'errors': errors, 'extraction_records': count, 'extraction_items': items,
              'checked_quote_occurrences': quotes, 'matters': len(judge['matters']),
              'decisions': len(decisions), 'scans': len(judge['lead_scan']), 'leads': len(leads),
              'limits': 'Checks saved synthetic artifacts and selected semantics, not live model replay or full business correctness.'}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('extraction', 'all'), default='all')
    args = parser.parse_args()
    try:
        raise SystemExit(check(args.stage))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'stage': args.stage, 'errors': [str(exc)]}, ensure_ascii=False))
        raise SystemExit(1)
