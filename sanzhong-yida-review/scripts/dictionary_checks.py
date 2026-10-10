"""Structural checks for the installed field dictionary; no compliance decisions."""
import datetime as dt
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re


def validate_dictionary(data, dictionary=None):
    if dictionary is None:
        dictionary = json.loads((Path(__file__).resolve().parent.parent / 'references/fact_dictionary.json').read_text(encoding='utf-8'))
    fields = dictionary['fields']
    errors = []
    date_items = {}
    role = data.get('agent_name')
    for record in data.get('records', []):
        rid = record['record_id']
        items = record.get('values', {}).get('items', [])
        if not items:
            errors.append(f'{rid}: values.items must contain a supported fact item')
        for index, item in enumerate(items):
            at = f'{rid}.items[{index}]'
            code = item['field']
            spec = fields.get(code)
            if not spec:
                errors.append(f'{at}: unknown dictionary field')
                continue
            if role not in spec['roles']:
                errors.append(f'{at}: dictionary field not allowed for role')
            if code == 'fact.other':
                # An "other" tag is legal without an extension. The specific
                # fact.other dictionary code denotes a type awaiting definition.
                source_ids = {e['file_id'] for e in record['evidence']}
                extension = any(
                    request.get('request_type') == 'dictionary_extension'
                    and rid in request.get('record_ids', [])
                    and (request['file_id'] is None or request['file_id'] in source_ids)
                    for request in data.get('requests', []))
                if not extension:
                    errors.append(f'{at}: fact.other requires a linked dictionary_extension request')
            raw = item['raw']
            evid = item['evidence_indexes']
            if not raw.strip() or not evid or len(evid) != len(set(evid)):
                errors.append(f'{at}: nonempty raw and unique evidence indexes required')
            valid_indexes = [i for i in evid if type(i) is int and 0 <= i < len(record['evidence'])]
            if len(valid_indexes) != len(evid):
                errors.append(f'{at}: evidence index out of range')
            elif raw and not any(raw in record['evidence'][i]['quote'] for i in valid_indexes):
                errors.append(f'{at}: raw must be a continuous excerpt of cited evidence')
            quals = item['qualifiers']
            if set(quals) != set(spec['qualifiers']):
                errors.append(f'{at}: qualifier keys do not match dictionary')
            for key, definition in spec['qualifiers'].items():
                val = quals.get(key)
                if 'enum' in definition:
                    if val not in definition['enum']:
                        errors.append(f'{at}.{key}: unknown enum')
                elif val is not None and not isinstance(val, str):
                    errors.append(f'{at}.{key}: expected string or null')
            normalized = item['normalized']
            kind = spec['value_type']
            if normalized is not None:
                if kind in ('decimal','integer'):
                    try:
                        number = Decimal(normalized)
                        if not re.fullmatch(r'-?\d+(?:\.\d+)?', normalized) or not number.is_finite():
                            raise ValueError('expected plain decimal string')
                        if kind == 'integer' and (not re.fullmatch(r'\d+', normalized) or number < 0):
                            raise ValueError('expected nonnegative integer string')
                    except (InvalidOperation, ValueError, TypeError):
                        errors.append(f'{at}: invalid numeric normalization')
                if code == 'financial.amount' and quals.get('bound') == 'range':
                    errors.append(f'{at}: range amount cannot use a scalar normalization')
            if kind == 'date':
                precision = quals.get('precision')
                date_items[(rid,index)] = (item,spec['event_type'])
                if normalized is not None:
                    try:
                        if precision == 'datetime':
                            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?', normalized):
                                raise ValueError()
                            dt.datetime.fromisoformat(normalized)
                        elif precision == 'date':
                            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',normalized): raise ValueError()
                            dt.date.fromisoformat(normalized)
                        elif precision == 'month':
                            if not re.fullmatch(r'\d{4}-\d{2}',normalized): raise ValueError()
                            dt.date.fromisoformat(normalized+'-01')
                        elif precision == 'year':
                            if not re.fullmatch(r'\d{4}',normalized): raise ValueError()
                            dt.date(int(normalized),1,1)
                        else:
                            raise ValueError()
                    except ValueError:
                        errors.append(f'{at}: date normalization exceeds precision or has invalid format')
                    # Detect the common unsupported assumption of the task year.
                    if re.search(r'\d',raw) and not re.search(r'(?<!\d)\d{4}(?!\d)',raw):
                        errors.append(f'{at}: normalized year absent from raw date; keep null')
    indexed = set()
    for entry in data.get('time_index', []):
        key = (entry['record_id'],entry['item_index'])
        if key in indexed:
            errors.append('time_index: duplicate dictionary item reference')
        indexed.add(key)
        if key not in date_items:
            errors.append('time_index: reference must point to a date dictionary item')
            continue
        item,event = date_items[key]
        if (entry['event_type'] != event or entry['raw'] != item['raw'] or
                entry['normalized'] != item['normalized'] or entry['precision'] != item['qualifiers'].get('precision')):
            errors.append('time_index: indexed values differ from dictionary fact')
    if set(date_items) - indexed:
        errors.append('time_index: missing date dictionary items')
    return errors
