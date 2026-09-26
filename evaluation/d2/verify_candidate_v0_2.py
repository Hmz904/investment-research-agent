"""Reproducible input-only D2 integration and synthetic determinism audit.

Run as a module with explicit --data-root. No real agent output is loaded or
generated. Only permitted DEV CSVs/map, frozen runtime files, and frozen synthetic
fixtures are accessed. Output contains counts/hashes, never benchmark contents.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys

from .validation_v0_2 import require, strict_loads, canonical_json_bytes, result_sha256
from .xbrl_v0_2 import load_frozen_xbrl_v0_2, adapt_dev_xbrl_map_v0_2
from .source_adapters_v0_2 import CSV_COLUMNS, adapt_dev_gold_bundle_v0_2
from .deterministic_evaluator import evaluate_v0_2

ROOT = Path(__file__).resolve().parents[2]
AUTHOR_MANIFEST_SHA = 'f69e14f586a6d2fd94b5500d05db5a984c8180cd609d3e2582316ef481c29e22'
# Authenticated against exact permitted blobs at the clean implementation base.
DEV_MAP_SHA = 'f129bf95b8a3428922ca5b87171f61e7a15481fc34586c37e22dfa23d33a2a53'
DEV_CSV_SHA = {
    'questions.csv': 'fbe81d8cbf01696d53616483276f4156bbb9ef263a999b47c9b3554f25377b04',
    'numeric_answers.csv': 'c6f82689fe8dd1adb1b5b054c393c4a7a5c2ffbc046ff8d100909127fcefcb0e',
    'evidence_checklist.csv': '5f6cec18f47fe5b568b55e24882af17f6c9688d9550b5d6a710c526ff53e9da9',
    'provenance.csv': '1e1347ec0b2c95c065f9a4f0a78ce5541ee0838533f14ce5d4490e1b1d4b53c7',
}


def verify_frozen_contracts():
    manifest = ROOT / 'evaluation/d2/D2_V2_TEST_AUTHOR_FREEZE_SHA256.txt'
    raw = manifest.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == AUTHOR_MANIFEST_SHA, 'Test-author manifest changed')
    rows = raw.decode().splitlines()
    for line in rows:
        expected, relative = line.split(maxsplit=1)
        require(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected, 'Frozen file changed: ' + relative)
    historical = strict_loads((ROOT / 'evaluation/d2/historical_source_authentication_v0.2.json').read_bytes())
    for record in historical['imported']:
        # Only authenticated imports in THIS checkout are opened.
        require(hashlib.sha256((ROOT / record['import_path']).read_bytes()).hexdigest() == record['historical_sha256'],
                'Historical normative import changed')
    return {'test_author_manifest_sha256': AUTHOR_MANIFEST_SHA,
            'verified_test_author_files': len(rows), 'verified_historical_imports': len(historical['imported'])}


def verify(data_root):
    frozen = verify_frozen_contracts()
    runtime = load_frozen_xbrl_v0_2(data_root=data_root)
    map_bytes = (ROOT / 'evaluation/dev/xbrl/dev_xbrl_map_v0.1.json').read_bytes()
    require(hashlib.sha256(map_bytes).hexdigest() == DEV_MAP_SHA, 'Frozen DEV map bytes changed')
    source = strict_loads(map_bytes)
    normalized = adapt_dev_xbrl_map_v0_2(source, source_sha256=result_sha256(source),
        fact_index=runtime['fact_index'], numeric_values=runtime['numeric_values'])
    require(normalized['evaluator_status'] == 'EVAL_OK', str(normalized.get('errors')))
    files = {name: (ROOT / 'benchmark/dev/v0.1' / name).read_bytes() for name in CSV_COLUMNS}
    source_hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    require(source_hashes == DEV_CSV_SHA, 'Frozen DEV CSV bytes changed')
    bundles = adapt_dev_gold_bundle_v0_2(files, declared_source_format='dev_gold_csv_bundle_v0.1',
        source_hashes=source_hashes, chunk_catalog=runtime['chunk_catalog'], normalized_map=normalized['normalized_map'],
        fact_index=runtime['fact_index'], numeric_values=runtime['numeric_values'])
    require(bundles['evaluator_status'] == 'EVAL_OK', str(bundles.get('errors')))
    # Independent fixtures are test inputs, not implementation scoring adapters.
    sys.path.insert(0, str(ROOT / 'tests/evaluation'))
    from d2_v2_contract_fixtures import request, derived_request, xbrl_request, cd02_request
    cases = {'direct': request(), 'derived': derived_request(), 'xbrl': xbrl_request(),
             'cd02': cd02_request('canonical_diagnostics')}
    hashes = {}
    for name, case in cases.items():
        first = evaluate_v0_2(case); second = evaluate_v0_2(case)
        require(first['evaluator_status'] == 'EVAL_OK', 'Synthetic probe failed: ' + name)
        require(canonical_json_bytes(first) == canonical_json_bytes(second), 'Nondeterministic result: ' + name)
        hashes[name] = result_sha256(first)
    packages = ['numpy', 'beautifulsoup4', 'lxml', 'soupsieve', 'pytest', 'jsonschema', 'referencing',
                'attrs', 'jsonschema-specifications', 'rpds-py', 'iniconfig', 'packaging', 'pluggy', 'Pygments', 'typing_extensions']
    verify_frozen_contracts()
    return dict(audit_version='d2_v2_implementation_validation_v0.1', frozen_contracts=frozen,
        data_root=str(data_root), runtime_manifest_sha256=hashlib.sha256((ROOT / 'packaging/frozen_runtime_bundle_v0.1.json').read_bytes()).hexdigest(),
        runtime_file_count=45, xbrl_artifact_fingerprint=runtime['fact_index']['xbrl_artifact_fingerprint'],
        fact_count=len(runtime['fact_index']['facts']), unlinked_fact_count=sum(f['chunk_id'] is None for f in runtime['fact_index']['facts']),
        chunk_count=len(runtime['chunk_catalog']), fact_index_sha256=result_sha256(runtime['fact_index']),
        numeric_catalog_sha256=result_sha256(runtime['numeric_values']), chunk_catalog_sha256=result_sha256(runtime['chunk_catalog']),
        dev_map_source_bytes_sha256=hashlib.sha256(map_bytes).hexdigest(), normalized_map_sha256=result_sha256(normalized['normalized_map']),
        normalized_map_state_counts=dict(sorted(Counter(t['state'] for t in normalized['normalized_map']['targets']).items())),
        dev_csv_source_hashes=source_hashes, dev_gold_bundle_count=len(bundles['gold_bundles']),
        dev_numeric_target_count=sum(len(b['numeric_targets']) for b in bundles['gold_bundles']),
        dev_gold_bundles_sha256=result_sha256(bundles['gold_bundles']), synthetic_result_hashes=hashes,
        python_version=platform.python_version(), package_versions={p: importlib.metadata.version(p) for p in packages},
        model_inference_used=False, real_agent_outputs_used=False, judge_used=False, locked_test_contents_used=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    raw = canonical_json_bytes(verify(args.data_root))
    if args.output:
        args.output.write_bytes(raw)
    else:
        sys.stdout.buffer.write(raw)


if __name__ == '__main__':
    main()
