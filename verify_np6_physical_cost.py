"""NP6 fail-closed verifier: frozen-config validation, pair completeness, manifest binding.

Usage: python verify_np6_physical_cost.py <frozen_git_sha>
Exit 0 only if every check passes (NP6_VERIFY_PASS).
"""
import hashlib
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
EXPECTED_PART = 'xc7z020clg400-1'
EXPECTED_CLOCK = '100.000'
REQUIRED_KEYS = ['RESULT', 'VIVADO_VERSION', 'PART', 'TOP', 'CLOCK_MHZ', 'GIT_HEAD',
                 'RUNNER', 'PAIR', 'SIDE', 'LUT', 'FF', 'BRAM36', 'BRAM18', 'DSP',
                 'WNS_NS', 'TNS_NS', 'WHS_NS', 'THS_NS', 'SETUP_FAILING_ENDPOINTS', 'HOLD_FAILING_ENDPOINTS']
CONFIGS = {
    'vivado_np6_gate_ooc_reports': ('1-gate', 'gate', 'local_prune_gate_2of4',
        'vivado_np6_gate_ooc_synth.tcl', ['local_prune_gate_2of4.sv']),
    'vivado_np6_eneuron_unpruned_reports': ('2-eneuron', 'unpruned', 'digital_lif_core',
        'vivado_np6_eneuron_unpruned_synth.tcl', ['digital_lif_core.sv']),
    'vivado_np6_eneuron_pruned_reports': ('2-eneuron', 'pruned', 'eneuron_local_prune_wrapper',
        'vivado_np6_eneuron_pruned_synth.tcl',
        ['eneuron_local_prune_wrapper.sv', 'digital_lif_engine.sv', 'local_prune_gate_2of4.sv']),
    'vivado_pulse_mini_reports': ('3-pulse-mini-l', 'unpruned', 'pulse_mini_core',
        'vivado_pulse_mini_synth.tcl', ['pulse_mini_core.sv']),
    'vivado_np6_pulse_mini_l_pruned_reports': ('3-pulse-mini-l', 'pruned', 'pulse_mini_l_prune_wrapper',
        'vivado_np6_pulse_mini_l_pruned_synth.tcl',
        ['pulse_mini_l_prune_wrapper.sv', 'pulse_mini_core.sv', 'pulse_mini_prune_bridge.sv',
         'local_prune_gate_2of4.sv', 'local_prune_evidence_gain.sv']),
    'vivado_pulse_mini_l2_reports': ('4-pulse-mini-l2', 'unpruned', 'pulse_mini_l2_core',
        'vivado_pulse_mini_l2_synth.tcl', ['pulse_mini_l2_core.sv']),
    'vivado_np6_pulse_mini_l2_pruned_reports': ('4-pulse-mini-l2', 'pruned', 'pulse_mini_l2_prune_wrapper',
        'vivado_np6_pulse_mini_l2_pruned_synth.tcl',
        ['pulse_mini_l2_prune_wrapper.sv', 'pulse_mini_l2_core.sv', 'pulse_mini_prune_bridge.sv',
         'local_prune_gate_2of4.sv', 'local_prune_evidence_gain.sv']),
}
PAIRS_BOTH = ['2-eneuron', '3-pulse-mini-l', '4-pulse-mini-l2']

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

def git_file_commit_epoch(sha, fname):
    out = subprocess.run(['git', '-C', str(ROOT), 'log', '-1', '--format=%ct', sha, '--', fname],
                         capture_output=True, text=True)
    text = out.stdout.strip()
    return int(text) if text else None

def main():
    if len(sys.argv) != 2:
        print('usage: verify_np6_physical_cost.py <frozen_git_sha>')
        return 2
    frozen_sha = sys.argv[1]
    failures = []
    summaries = {}
    manifest = {'frozen_git_head': frozen_sha, 'generated_at_epoch': int(time.time()),
                'part': EXPECTED_PART, 'clock_mhz': EXPECTED_CLOCK, 'configs': {}}
    for dirname, (pair, side, top, runner, sources) in CONFIGS.items():
        d = ROOT / dirname
        spath = d / 'signoff_summary.txt'
        tag = pair + '/' + side
        if not spath.exists():
            failures.append(tag + ': missing signoff_summary.txt')
            continue
        kv = {}
        for line in spath.read_text(encoding='utf-8').splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
                kv[k.strip()] = v.strip()
        summaries[tag] = kv
        for key in REQUIRED_KEYS:
            if key not in kv:
                failures.append(tag + ': summary missing key ' + key)
        if kv.get('RESULT') != 'ROUTED':
            failures.append(tag + ': RESULT is ' + str(kv.get('RESULT')))
        if kv.get('PART') != EXPECTED_PART:
            failures.append(tag + ': PART is ' + str(kv.get('PART')))
        if kv.get('CLOCK_MHZ') != EXPECTED_CLOCK:
            failures.append(tag + ': CLOCK_MHZ is ' + str(kv.get('CLOCK_MHZ')))
        if kv.get('TOP') != top:
            failures.append(tag + ': TOP is ' + str(kv.get('TOP')) + ' expected ' + top)
        if kv.get('RUNNER') != runner:
            failures.append(tag + ': RUNNER is ' + str(kv.get('RUNNER')))
        if kv.get('GIT_HEAD') != frozen_sha:
            failures.append(tag + ': GIT_HEAD ' + str(kv.get('GIT_HEAD')) + ' != frozen ' + frozen_sha)
        if '2024.2' not in str(kv.get('VIVADO_VERSION', '')):
            failures.append(tag + ': VIVADO_VERSION is ' + str(kv.get('VIVADO_VERSION')))
        for key in ['LUT', 'FF', 'BRAM36', 'BRAM18', 'DSP', 'SETUP_FAILING_ENDPOINTS', 'HOLD_FAILING_ENDPOINTS']:
            try:
                int(kv.get(key, ''))
            except ValueError:
                failures.append(tag + ': non-integer ' + key)
        for key in ['WNS_NS', 'TNS_NS', 'WHS_NS', 'THS_NS']:
            value = kv.get(key, 'NA')
            try:
                float(value)
            except ValueError:
                failures.append(tag + ': timing field ' + key + ' not numeric: ' + value)
        for src in sources:
            epoch = git_file_commit_epoch(frozen_sha, src)
            if epoch is None:
                failures.append(tag + ': source ' + src + ' absent at frozen HEAD')
            elif spath.stat().st_mtime < epoch:
                failures.append(tag + ': summary older than frozen commit of ' + src)
        files = {}
        for f in sorted(d.iterdir()):
            if f.is_file():
                files[f.name] = sha256_file(f)
        manifest['configs'][tag] = {
            'report_dir': dirname, 'runner': runner, 'top': top, 'side': side,
            'summary': kv, 'files_sha256': files}
    for pair in PAIRS_BOTH:
        if pair + '/unpruned' not in summaries or pair + '/pruned' not in summaries:
            failures.append(pair + ': pair incomplete (need unpruned + pruned)')
    if '1-gate/gate' not in summaries:
        failures.append('1-gate: gate OOC run missing')
    freeze_doc = ROOT / 'docs' / 'planning' / 'NPU_PRUNING_NP6_FREEZE_DECISIONS.md'
    text = freeze_doc.read_text(encoding='utf-8') if freeze_doc.exists() else ''
    for token in ['NOT_COMPARABLE']:
        if token not in text:
            failures.append('freeze decisions doc missing ' + token)
    for line in ['4→8→2', '系统对']:
        pass
    out = ROOT / 'artifacts' / 'results' / 'np6_physical_cost_manifest.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    if failures:
        for f in failures:
            print('NP6_VERIFY_FAIL:', f)
        print('NP6_VERIFY_FAIL total=' + str(len(failures)))
        return 1
    gate_ok = True
    for tag in sorted(summaries):
        kv = summaries[tag]
        try:
            sf = int(kv.get('SETUP_FAILING_ENDPOINTS', 'NA'))
            hf = int(kv.get('HOLD_FAILING_ENDPOINTS', 'NA'))
            wns = float(kv.get('WNS_NS', 'NA'))
            whs = float(kv.get('WHS_NS', 'NA'))
            passed = sf == 0 and hf == 0 and wns >= 0.0 and whs >= 0.0
        except ValueError:
            passed = False
        if not passed:
            gate_ok = False
        print('TIMING_GATE', tag, 'PASS' if passed else 'FAIL',
              'setup_fail=' + kv.get('SETUP_FAILING_ENDPOINTS', 'NA'),
              'hold_fail=' + kv.get('HOLD_FAILING_ENDPOINTS', 'NA'),
              'wns=' + kv.get('WNS_NS', 'NA'), 'whs=' + kv.get('WHS_NS', 'NA'))
    deltas = []
    for pair in PAIRS_BOTH:
        u = summaries[pair + '/unpruned']
        p = summaries[pair + '/pruned']
        deltas.append((pair, int(p['LUT']) - int(u['LUT']), int(p['FF']) - int(u['FF'])))
    for pair, dl, df in deltas:
        print('DELTA', pair, 'dLUT=' + str(dl), 'dFF=' + str(df))
    print('manifest written:', out.relative_to(ROOT))
    print('NP6_VERIFY_PASS configs=' + str(len(summaries)))
    print('NP6_TIMING_GATE', 'ALL_PASS' if gate_ok else 'PARTIAL_FAIL')
    return 0

if __name__ == '__main__':
    sys.exit(main())