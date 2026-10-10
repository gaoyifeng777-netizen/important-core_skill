"""Portable assembly checks and synthetic regressions; no client inputs required."""
from pathlib import Path
import json
import argparse
import hashlib
import re
import subprocess
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT.parent
ROLES=['meeting_schedule','proposal_extract','meeting_record','meeting_minutes']
def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError(f'duplicate JSON key: {key}')
        result[key]=value
    return result

def parse_json(text):
    return json.loads(text,object_pairs_hook=unique_object)

def check(output=None):
    failures=[]; json_blocks=0; links=0
    all_roles=['master_control','read_adjust','base_rule',*ROLES,'rule_judge','quality_review']
    for role_name in all_roles:
        if not (ROOT/f'prompts/{role_name}.md').is_file(): failures.append(f'missing prompt {role_name}')
    entry=(ROOT/'SKILL.md').read_text(encoding='utf-8')
    if not entry.startswith('---\nname: sanzhong-yida-review\n') or 'version: "1.0.0"' not in entry:
        failures.append('entry format/version mismatch')
    dictionary=json.loads((ROOT/'references/fact_dictionary.json').read_text(encoding='utf-8'))
    all_fields=set(dictionary['fields'])
    for role in ROLES:
        content=(ROOT/f'prompts/{role}.md').read_text(encoding='utf-8')
        actual=set(re.findall(r'^\| `([^`]+)` \|',content,re.M)) & all_fields
        expected={k for k,v in dictionary['fields'].items() if role in v['roles']}
        if actual!=expected: failures.append(f'{role}: dictionary table mismatch')
        if '"schema_version": "1.1"' not in content: failures.append(f'{role}: schema version missing')
    for p in BASE.rglob('*.json'):
        if '__pycache__' in p.parts: continue
        try: parse_json(p.read_text(encoding='utf-8'))
        except Exception as exc: failures.append(f'{p.name}: {exc}')
    for p in BASE.rglob('*.md'):
        txt=p.read_text(encoding='utf-8')
        if re.search(r'(?i)\b[A-Z]:[/\\]|/Users/|/home/[^/]+/',txt): failures.append(f'{p.name}: machine-specific path')
        if re.search(r'(?i)(?:AI|人工智能|ChatGPT|Codex)\s*(?:编辑|撰写|生成|编写)|研究Agent取得',txt): failures.append(f'{p.name}: editing attribution')
        for block in re.findall(r'```json\s*\n(.*?)\n```',txt,re.S):
            json_blocks+=1
            try: parse_json(block)
            except Exception as exc: failures.append(f'{p.name} JSON: {exc}')
        for target in re.findall(r'\]\(([^)]+)\)',txt):
            target=target.strip('<>').split('#')[0]
            if not target or '://' in target: continue
            links+=1
            if not (p.parent/target).exists(): failures.append(f'{p.name}: missing link {target}')
    logic=(ROOT/'rules/judgment_logic.md').read_text(encoding='utf-8')
    if '版本：1.2' not in logic: failures.append('logic version must be 1.2')
    if len(re.findall(r'^### T\d{2} ',logic,re.M))!=14: failures.append('14 test cards expected')
    # Exact backticked dotted names in the logic must not be stale field codes.
    namespaces=('meeting','agenda','matter','document','proposal','approval','schedule','history','decision','condition','follow_up','attendance','statement','voting','recusal','financial','notice','fact','facts')
    field_documents=['rules/judgment_logic.md','rules/business_rules.md','rules/material_sorting.md',
                     'prompts/rule_judge.md']
    for relative in field_documents:
        content=(ROOT/relative).read_text(encoding='utf-8')
        for code in set(re.findall(r'\b([a-z_]+\.[a-z_]+)\b',content)):
            if code.split('.')[0] in namespaces and code not in all_fields:
                failures.append(f'{relative}: unknown dictionary field {code}')
    catalog=(ROOT/'rules/business_rules.md').read_text(encoding='utf-8')
    catalog_ids=re.findall(r'^### ([CL]\d{2,})\s',catalog,re.M)
    if len(catalog_ids)!=len(set(catalog_ids)): failures.append('duplicate catalog heading ID')
    if not any(x.startswith('C') for x in catalog_ids): failures.append('no CONTROL cards')
    if not any(x.startswith('L') for x in catalog_ids): failures.append('no LEAD cards')
    for card_id in catalog_ids:
        if not re.search(r'^\| '+re.escape(card_id)+r' \| (?:CONTROL|LEAD) \|',catalog,re.M):
            failures.append(f'{card_id}: missing catalog index row')
    for name in ('material_sorting','business_rules'):
        txt=(ROOT/f'rules/{name}.md').read_text(encoding='utf-8')
        present=set(re.findall(r'\b([a-z_]+\.[a-z_]+)\b',txt)) & all_fields
        if present!=all_fields: failures.append(f'{name}: incomplete dictionary navigation {sorted(all_fields-present)}')
    manifest_path=ROOT/'manifest.json'
    if not manifest_path.is_file():
        failures.append('manifest.json missing')
    else:
        manifest=parse_json(manifest_path.read_text(encoding='utf-8'))
        entries={x['path']:x for x in manifest['files']}
        actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and p!=manifest_path and '__pycache__' not in p.parts}
        if actual!=set(entries): failures.append('manifest inventory mismatch')
        for name,entry in entries.items():
            path=ROOT/name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
                failures.append(f'manifest hash mismatch: {name}')
    tests=[]
    for filename in ('validator_regression.py','dictionary_regression.py','release_regression.py'):
        res=subprocess.run([sys.executable,'-B','-X','utf8',str(ROOT/'validation/dictionary'/filename)],capture_output=True,text=True,encoding='utf-8')
        tests.append({'file':filename,'exit_code':res.returncode,'output':res.stdout+res.stderr})
        if res.returncode: failures.append(f'{filename}: tests failed')
    result={'bundle_version':'1.0.0','schema_version':'1.1','judge_schema_version':'1.3','dictionary_version':dictionary['dictionary_version'],
            'dictionary_fields':len(all_fields),'role_prompts':9,'json_blocks':json_blocks,'relative_links':links,
            'control_cards':sum(x.startswith('C') for x in catalog_ids),
            'lead_methods':sum(x.startswith('L') for x in catalog_ids),
            'tests':tests,'failures':failures,'ok':not failures,
            'limits':'Synthetic and assembly checks only; not real client workflow, OCR, business accuracy, access isolation or RRSI validation.'}
    if output:
        output=Path(output).resolve()
        if output.is_relative_to(ROOT): raise ValueError('Output must be outside fixed Skill directory')
        with output.open('x',encoding='utf-8') as f:
            f.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='tests'},ensure_ascii=False))
    if failures: raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',help='New report path outside the Skill directory')
    args=parser.parse_args()
    try:
        check(args.output)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'ok':False,'failures':[str(exc)]},ensure_ascii=False))
        raise SystemExit(1)
