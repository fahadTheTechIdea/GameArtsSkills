#!/usr/bin/env python3
"""Basic schema and completeness gate. Optional jsonschema dependency for full validation."""
import json,sys
from pathlib import Path

def main():
    if len(sys.argv)!=2:
        print("Usage: validate_blueprint.py blueprint.json");return 2
    d=json.loads(Path(sys.argv[1]).read_text(encoding='utf8'))
    required={'schema_version','mockup_id','mockup_revision','approval_status','scope','elements','coverage_audit'}
    missing=required-set(d)
    if missing: print('FAIL missing:',sorted(missing));return 1
    if d['approval_status']!='approved': print('INCOMPLETE: mockup not approved');return 1
    if not isinstance(d['elements'],list) or not d['elements']:print('FAIL empty elements');return 1
    for i,e in enumerate(d['elements']):
        need={'element_id','scope','evidence_status','observed_details','motion_candidates','production_strategy'}-set(e)
        if need:print('FAIL element',i,'missing',sorted(need));return 1
    if d['coverage_audit'].get('status')!='pass':print('INCOMPLETE coverage audit not pass');return 1
    try:
        import jsonschema
    except ImportError:
        print('PASS basic checks. Full JSON schema validation NOT RUN (jsonschema not installed)');return 0
    schema=json.loads((Path(__file__).resolve().parent.parent/'schemas/mockup-blueprint.schema.json').read_text())
    jsonschema.validate(d,schema)
    print('PASS blueprint syntax, required fields and schema. Visual completeness NOT proven.');return 0
if __name__=='__main__':sys.exit(main())