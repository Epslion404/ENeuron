"""NP6 manifest generator. Run ONCE at evidence time, then commit the manifest.

Usage: python generate_np6_manifest.py <frozen_run_sha>
Writes artifacts/results/np6_physical_cost_manifest.json binding only committed
report files (never .dcp) plus runner/verifier/RTL hashes.
"""
import hashlib
import json
import pathlib
import sys
import time
from verify_np6_physical_cost import (CONFIGS, EXPECTED_FILES, EXPECTED_PART,
                                       EXPECTED_CLOCK, VERIFIER_REL, canonical_bytes)

ROOT = pathlib.Path(__file__).resolve().parent

from verify_np6_physical_cost import sha256_file, sha256_bytes  # canonical LF hashing

def main():
    if len(sys.argv) != 2:
        print('usage: generate_np6_manifest.py <frozen_run_sha>')
        return 2
    frozen = sys.argv[1]
    manifest = {'frozen_git_head': frozen, 'generated_at_epoch': int(time.time()),
                'part': EXPECTED_PART, 'clock_mhz': EXPECTED_CLOCK,
                'configs': {}, 'bindings': {}}
    bound = set()
    for dirname, (pair, side, top, runner, sources) in CONFIGS.items():
        tag = pair + '/' + side
        d = ROOT / dirname
        files = {}
        for fname in EXPECTED_FILES:
            fp = d / fname
            if not fp.exists():
                print('MISSING', tag, fname)
                return 1
            files[fname] = sha256_file(fp)
        manifest['configs'][tag] = {'report_dir': dirname, 'runner': runner,
                                    'top': top, 'side': side, 'sources': sources,
                                    'files_sha256': files}
        bound.update(sources)
        bound.add(runner)
    import subprocess
    for rel in sorted(bound):
        r = subprocess.run(['git', '-C', str(ROOT), 'show', frozen + ':' + rel],
                           capture_output=True)
        if r.returncode != 0:
            print('NOT AT FROZEN', rel)
            return 1
        manifest['bindings'][rel] = sha256_bytes(canonical_bytes(r.stdout))
    manifest['tool_bindings'] = {VERIFIER_REL: sha256_file(ROOT / VERIFIER_REL)}
    out = ROOT / 'artifacts' / 'results' / 'np6_physical_cost_manifest.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    print('MANIFEST_WRITTEN', out.relative_to(ROOT), 'configs=' + str(len(manifest['configs'])),
          'bindings=' + str(len(manifest['bindings'])))
    return 0

if __name__ == '__main__':
    sys.exit(main())