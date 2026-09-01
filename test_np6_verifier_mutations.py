"""NP6 verifier mutation suite: every known mutation must be rejected (non-zero exit)."""
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent

def run_verifier(workdir, head):
    r = subprocess.run([sys.executable, 'verify_np6_physical_cost.py', head],
                       cwd=str(workdir), capture_output=True, text=True)
    return r.returncode, r.stdout

def git_restore(workdir):
    subprocess.run(['git', '-C', str(workdir), 'checkout', '--', '.'], capture_output=True)

def main():
    if len(sys.argv) != 2:
        print('usage: test_np6_verifier_mutations.py <verify_head_sha>')
        return 2
    head = sys.argv[1]
    tmp_parent = pathlib.Path(tempfile.mkdtemp(prefix='np6_mut_'))
    tmp = tmp_parent / 'repo'
    print('cloning repo to', tmp)
    clone = subprocess.run(['git', 'clone', '--quiet', '--no-hardlinks', str(ROOT), str(tmp)],
                           capture_output=True, text=True)
    if clone.returncode != 0:
        print('clone failed:', clone.stderr.strip())
        shutil.rmtree(tmp_parent, ignore_errors=True)
        return 1
    results = []
    manifest_rel = pathlib.Path('artifacts') / 'results' / 'np6_physical_cost_manifest.json'
    before = (tmp / manifest_rel).read_bytes()
    rc, out = run_verifier(tmp, head)
    clean = subprocess.run(['git', '-C', str(tmp), 'status', '--porcelain'], capture_output=True, text=True).stdout
    after = (tmp / manifest_rel).read_bytes()
    results.append(('T0 baseline forward pass', rc == 0))
    results.append(('T0 manifest bytes unchanged', before == after))
    results.append(('T0 worktree clean after verify', clean.strip() == ''))
    gate = pathlib.Path('vivado_np6_gate_ooc_reports')
    def mutate(name, fn, expect_fail=True):
        fn(tmp)
        rc, out = run_verifier(tmp, head)
        ok = (rc != 0) if expect_fail else (rc == 0)
        results.append((name, ok))
        print('---', name, 'rc=' + str(rc))
        for line in out.splitlines():
            if 'FAIL' in line:
                print('   ', line[:160])
        git_restore(tmp)
    def del_timing(w):
        (w / gate / 'timing_impl.rpt').unlink()
    def tamper_summary(w):
        p = w / gate / 'signoff_summary.txt'
        t = p.read_text(encoding='utf-8')
        p.write_text(t.replace('LUT=200', 'LUT=201'), encoding='utf-8')
    def tamper_report(w):
        p = w / gate / 'utilization_impl.rpt'
        t = p.read_text(encoding='utf-8')
        p.write_text(t + ' ' , encoding='utf-8')
    def tamper_runner(w):
        p = w / 'vivado_np6_gate_ooc_synth.tcl'
        p.write_text(p.read_text(encoding='utf-8') + '# mutation\n', encoding='utf-8')
    def del_summary(w):
        (w / gate / 'signoff_summary.txt').unlink()
    def tamper_manifest(w):
        p = w / manifest_rel
        t = p.read_text(encoding='utf-8')
        p.write_text(t.replace('frozen_git_head', 'frozen_git_head_'), encoding='utf-8')
    mutate('T1 delete timing report', del_timing)
    mutate('T2 tamper summary LUT', tamper_summary)
    mutate('T3 tamper utilization report', tamper_report)
    mutate('T4 tamper runner tcl', tamper_runner)
    mutate('T5 delete signoff summary', del_summary)
    mutate('T6 tamper manifest bytes', tamper_manifest)
    manifest_text = (tmp / manifest_rel).read_text(encoding='utf-8')
    results.append(('T7 manifest binds no .dcp', '.dcp' not in manifest_text))
    def committed_attack(name, target_rel):
        tp = tmp / target_rel
        tp.write_text(tp.read_text(encoding='utf-8') + chr(10) + '// post-freeze mutation', encoding='utf-8')
        mp = tmp / manifest_rel
        m = json.loads(mp.read_text(encoding='utf-8'))
        data = tp.read_bytes().replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        m['bindings'][target_rel] = hashlib.sha256(data).hexdigest()
        mp.write_text(json.dumps(m, indent=2, ensure_ascii=False, sort_keys=True) + chr(10), encoding='utf-8')
        subprocess.run(['git', '-C', str(tmp), 'add', '-A'], capture_output=True)
        subprocess.run(['git', '-C', str(tmp), '-c', 'user.email=np6@test.local', '-c', 'user.name=np6-mutation', 'commit', '-qm', 'tamper'], capture_output=True)
        new_head = subprocess.run(['git', '-C', str(tmp), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
        rc, out = run_verifier(tmp, new_head)
        results.append((name, rc != 0))
        print('---', name, 'rc=' + str(rc))
        for line in out.splitlines():
            if 'frozen binding' in line or 'binding' in line:
                print('   ', line[:160])
        subprocess.run(['git', '-C', str(tmp), 'reset', '--hard', head], capture_output=True)
    committed_attack('T8 post-freeze RTL tamper + manifest co-update', 'local_prune_gate_2of4.sv')
    committed_attack('T9 post-freeze runner tamper + manifest co-update', 'vivado_np6_gate_ooc_synth.tcl')
    shutil.rmtree(tmp_parent, ignore_errors=True)
    all_ok = True
    for name, ok in results:
        print(('MUTATION_TEST_PASS' if ok else 'MUTATION_TEST_FAIL'), name)
        if not ok:
            all_ok = False
    print('MUTATION_SUITE', 'PASS' if all_ok else 'FAIL', 'checks=' + str(len(results)))
    return 0 if all_ok else 1

if __name__ == '__main__':
    sys.exit(main())
