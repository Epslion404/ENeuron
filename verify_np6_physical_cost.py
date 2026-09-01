"""NP6 fail-closed verifier (read-only).

Usage: python verify_np6_physical_cost.py <verify_head_sha>

Reads the committed manifest at <verify_head_sha>, re-checks every bound file
by SHA-256, and recomputes key conclusions directly from the Vivado reports
(utilization / timing / DRC / route status). Never writes any file.
Exit 0 only if every check passes (NP6_VERIFY_PASS).
"""
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
MANIFEST_REL = 'artifacts/results/np6_physical_cost_manifest.json'
EXPECTED_PART = 'xc7z020clg400-1'
EXPECTED_CLOCK = '100.000'
EXPECTED_FILES = ['utilization_synth.rpt', 'timing_synth.rpt', 'drc_synth.rpt',
                  'utilization_impl.rpt', 'timing_impl.rpt', 'drc_impl.rpt',
                  'power_impl.rpt', 'route_status_impl.rpt', 'signoff_summary.txt']
SUMMARY_KEYS = ['RESULT', 'VIVADO_VERSION', 'PART', 'TOP', 'CLOCK_MHZ', 'GIT_HEAD',
                'RUNNER', 'PAIR', 'SIDE', 'LUT', 'FF', 'BRAM36', 'BRAM18', 'DSP',
                'WNS_NS', 'TNS_NS', 'WHS_NS', 'THS_NS',
                'SETUP_FAILING_ENDPOINTS', 'HOLD_FAILING_ENDPOINTS']
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
PAIRS_BOTH = ['3-pulse-mini-l', '4-pulse-mini-l2']
VERIFIER_REL = 'verify_np6_physical_cost.py'

def canonical_bytes(data):
    return data.replace(b'\r\n', b'\n').replace(b'\r', b'\n')

def sha256_file(path):
    # Canonical LF hash (repo convention, matches NP4B verify_local_prune_rtl.py):
    # identical result on CRLF working trees and LF checkouts.
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(canonical_bytes(chunk))
    return h.hexdigest()

def git(*args):
    r = subprocess.run(['git', '-C', str(ROOT)] + list(args), capture_output=True, text=True)
    return r.returncode, r.stdout

def git_epoch_at(sha, fname):
    rc, out = git('log', '-1', '--format=%ct', sha, '--', fname)
    text = out.strip()
    return int(text) if rc == 0 and text else None

def parse_utilization(text):
    vals = {}
    for key, pat in [('LUT', r'Slice LUTs\s*\|\s*([0-9]+)'),
                     ('FF', r'Slice Registers\s*\|\s*([0-9]+)'),
                     ('BRAM36', r'Block RAM Tile\s*\|\s*([0-9]+)'),
                     ('BRAM18', r'RAMB18\s*\|\s*([0-9]+)'),
                     ('DSP', r'DSPs\s*\|\s*([0-9]+)')]:
        m = re.search(pat, text)
        vals[key] = int(m.group(1)) if m else None
    return vals

def parse_timing(text):
    vals = {'setup_fail': None, 'wns': None, 'tns': None,
            'hold_fail': None, 'whs': None, 'ths': None}
    m = re.search(r'Setup\s*:\s*([0-9]+)\s+Failing Endpoints,\s*Worst Slack\s+(-?[0-9.]+)ns,\s*Total Violation\s+(-?[0-9.]+)ns', text)
    if m:
        vals['setup_fail'], vals['wns'], vals['tns'] = int(m.group(1)), float(m.group(2)), float(m.group(3))
    m = re.search(r'Hold\s*:\s*([0-9]+)\s+Failing Endpoints,\s*Worst Slack\s+(-?[0-9.]+)ns,\s*Total Violation\s+(-?[0-9.]+)ns', text)
    if m:
        vals['hold_fail'], vals['whs'], vals['ths'] = int(m.group(1)), float(m.group(2)), float(m.group(3))
    return vals

def parse_drc(text):
    rows = re.findall(r'\|\s*([A-Z][A-Z0-9-]+)\s*\|\s*(Error|Critical Warning|Warning|Info|Advisory)\s*\|', text)
    return sum(1 for _, sev in rows if sev == 'Error')

def parse_route(text):
    m = re.search(r'# of nets with routing errors[. ]*:[[:space:]]*([0-9]+)'.replace('[[:space:]]', '\\s'), text)
    if m is None:
        return None
    return int(m.group(1))

def main():
    if len(sys.argv) != 2:
        print('usage: verify_np6_physical_cost.py <verify_head_sha>')
        return 2
    verify_head = sys.argv[1]
    failures = []
    rc, committed = git('show', verify_head + ':' + MANIFEST_REL)
    if rc != 0:
        print('NP6_VERIFY_FAIL: manifest not committed at', verify_head)
        return 1
    disk_path = ROOT / 'artifacts' / 'results' / 'np6_physical_cost_manifest.json'
    if not disk_path.exists():
        print('NP6_VERIFY_FAIL: manifest missing on disk')
        return 1
    disk_bytes = disk_path.read_bytes()
    if canonical_bytes(disk_bytes) != canonical_bytes(committed.encode('utf-8')):
        failures.append('manifest on disk differs from committed bytes at ' + verify_head)
    manifest = json.loads(disk_bytes.decode('utf-8'))
    frozen = manifest.get('frozen_git_head', '')
    if not frozen:
        failures.append('manifest missing frozen_git_head')
    if '.dcp' in json.dumps(manifest):
        failures.append('manifest binds a .dcp file (DCPs are not committed and must not be bound)')
    if manifest.get('part') != EXPECTED_PART or manifest.get('clock_mhz') != EXPECTED_CLOCK:
        failures.append('manifest frozen part/clock mismatch')
    summaries = {}
    bound_sources = set()
    for dirname, (pair, side, top, runner, sources) in CONFIGS.items():
        tag = pair + '/' + side
        bound_sources.update(sources)
        centry = manifest.get('configs', {}).get(tag)
        if centry is None:
            failures.append(tag + ': missing from manifest')
            continue
        if centry.get('runner') != runner or centry.get('top') != top or centry.get('side') != side:
            failures.append(tag + ': manifest runner/top/side mismatch')
        d = ROOT / dirname
        mfiles = centry.get('files_sha256', {})
        if sorted(mfiles.keys()) != sorted(EXPECTED_FILES):
            failures.append(tag + ': manifest file set differs from expected report set')
        for fname in EXPECTED_FILES:
            fp = d / fname
            if not fp.exists():
                failures.append(tag + ': missing report file ' + fname)
                continue
            expect = mfiles.get(fname)
            actual = sha256_file(fp)
            if expect != actual:
                failures.append(tag + ': SHA-256 mismatch for ' + fname)
        spath = d / 'signoff_summary.txt'
        if not spath.exists():
            continue
        kv = {}
        for line in spath.read_text(encoding='utf-8').splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
                kv[k.strip()] = v.strip()
        summaries[tag] = kv
        for key in SUMMARY_KEYS:
            if key not in kv:
                failures.append(tag + ': summary missing key ' + key)
        if kv.get('RESULT') != 'ROUTED':
            failures.append(tag + ': RESULT is ' + str(kv.get('RESULT')))
        if kv.get('PART') != EXPECTED_PART:
            failures.append(tag + ': PART is ' + str(kv.get('PART')))
        if kv.get('CLOCK_MHZ') != EXPECTED_CLOCK:
            failures.append(tag + ': CLOCK_MHZ is ' + str(kv.get('CLOCK_MHZ')))
        if kv.get('TOP') != top:
            failures.append(tag + ': TOP mismatch')
        if kv.get('RUNNER') != runner:
            failures.append(tag + ': RUNNER mismatch')
        if kv.get('GIT_HEAD') != frozen:
            failures.append(tag + ': summary GIT_HEAD != manifest frozen head')
        if '2024.2' not in str(kv.get('VIVADO_VERSION', '')):
            failures.append(tag + ': VIVADO_VERSION is ' + str(kv.get('VIVADO_VERSION')))
        util = parse_utilization((d / 'utilization_impl.rpt').read_text(encoding='utf-8', errors='ignore'))
        for key in ['LUT', 'FF', 'BRAM36', 'BRAM18', 'DSP']:
            if util[key] is None:
                failures.append(tag + ': cannot recompute ' + key + ' from utilization report')
            elif str(util[key]) != kv.get(key):
                failures.append(tag + ': ' + key + ' recomputed ' + str(util[key]) + ' != summary ' + str(kv.get(key)))
        tim = parse_timing((d / 'timing_impl.rpt').read_text(encoding='utf-8', errors='ignore'))
        for skey, tkey in [('WNS_NS', 'wns'), ('TNS_NS', 'tns'), ('WHS_NS', 'whs'), ('THS_NS', 'ths')]:
            if tim[tkey] is None:
                failures.append(tag + ': cannot recompute ' + tkey + ' from timing report')
            elif abs(float(kv.get(skey, 'NA') or '1e30') - tim[tkey]) > 1e-6:
                failures.append(tag + ': ' + skey + ' summary ' + str(kv.get(skey)) + ' != recomputed ' + str(tim[tkey]))
        for skey, tkey in [('SETUP_FAILING_ENDPOINTS', 'setup_fail'), ('HOLD_FAILING_ENDPOINTS', 'hold_fail')]:
            if tim[tkey] is None:
                failures.append(tag + ': cannot recompute failing endpoints from timing report')
            elif str(tim[tkey]) != kv.get(skey):
                failures.append(tag + ': failing-endpoint count mismatch ' + skey)
        drc_errors = parse_drc((d / 'drc_impl.rpt').read_text(encoding='utf-8', errors='ignore'))
        if drc_errors != 0:
            failures.append(tag + ': DRC errors reported: ' + str(drc_errors))
        route_errors = parse_route((d / 'route_status_impl.rpt').read_text(encoding='utf-8', errors='ignore'))
        if route_errors is None:
            failures.append(tag + ': cannot parse route status report')
        elif route_errors != 0:
            failures.append(tag + ': route errors reported: ' + str(route_errors))
        for src in sources + [runner, VERIFIER_REL]:
            epoch = git_epoch_at(frozen, src)
            if epoch is None:
                failures.append(tag + ': ' + src + ' absent at frozen HEAD')
            elif spath.stat().st_mtime < epoch:
                failures.append(tag + ': summary older than frozen commit of ' + src)
    bindings = manifest.get('bindings', {})
    must_bind = sorted(set([c[3] for c in CONFIGS.values()] + [VERIFIER_REL] + list(bound_sources)))
    for rel in must_bind:
        if rel not in bindings:
            failures.append('binding missing: ' + rel)
            continue
        fp = ROOT / rel
        if not fp.exists():
            failures.append('bound file missing on disk: ' + rel)
        elif sha256_file(fp) != bindings[rel]:
            failures.append('binding SHA-256 mismatch: ' + rel)
    for pair in PAIRS_BOTH:
        if pair + '/unpruned' not in summaries or pair + '/pruned' not in summaries:
            failures.append(pair + ': pair incomplete')
    if '1-gate/gate' not in summaries:
        failures.append('1-gate: gate run missing')
    gate_ok = True
    for tag in sorted(summaries):
        kv = summaries[tag]
        try:
            sf = int(kv['SETUP_FAILING_ENDPOINTS']); hf = int(kv['HOLD_FAILING_ENDPOINTS'])
            wns = float(kv['WNS_NS']); whs = float(kv['WHS_NS'])
            passed = sf == 0 and hf == 0 and wns >= 0.0 and whs >= 0.0
        except (ValueError, KeyError):
            passed = False
        if not passed:
            gate_ok = False
        print('TIMING_GATE', tag, 'PASS' if passed else 'FAIL')
    print('PAIR_DELTA 2-eneuron NOT_COMPARABLE (microarchitecture differs; freeze decision 10)')
    for pair in PAIRS_BOTH:
        u = summaries[pair + '/unpruned']; p = summaries[pair + '/pruned']
        print('PAIR_DELTA', pair, 'dLUT=' + str(int(p['LUT']) - int(u['LUT'])),
              'dFF=' + str(int(p['FF']) - int(u['FF'])))
    if failures:
        for f in failures:
            print('NP6_VERIFY_FAIL:', f)
        print('NP6_VERIFY_FAIL total=' + str(len(failures)))
        return 1
    print('NP6_VERIFY_PASS configs=' + str(len(summaries)))
    print('NP6_TIMING_GATE', 'ALL_PASS' if gate_ok else 'PARTIAL_FAIL')
    return 0

if __name__ == '__main__':
    sys.exit(main())