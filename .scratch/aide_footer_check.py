import sys, json, subprocess
sys.path.insert(0, r"D:\01_Job\Tool\Hermes Agent")
from pathlib import Path
from agent.model_metadata import get_model_context_length

res = json.loads(Path('aide_e2e_efforts_20261008_124247.json').read_text(encoding='utf-8'))
OA = subprocess.run(['bash','-lc','cd ~/.cchelper && ./coding-cli-helper.exe auth token --tool claude --domain oa'],
                    capture_output=True, text=True, timeout=60).stdout.strip()
ENV = {}
for line in Path.home().joinpath('.hermes','.env').read_text().splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        k, v = line.split('=', 1); ENV[k.strip()] = v.strip()

cases = [
    # (slug, provider_label, base_url, key)
    ('aide',   'custom', 'https://mlop-azure-gateway.mediatek.inc/v1',    OA),
    ('aide-io','custom', 'https://mlop-azure-gateway-io.mediatek.inc/v1', ENV.get('AIDE_IO_API_KEY','')),
]

V3 = json.loads(Path(sorted(Path('.').glob('aide_catalog_*.json'))[-1]).read_text(encoding='utf-8'))['aide']['v3_meta']
KNOWN_922K = ('gpt-5.6-', 'gpt-6')  # AIDE commercial GPT live ceiling (skill ref)

out = {}
for slug, prov, base, key in cases:
    rows = {}
    for m, r in res[slug].items():
        if not r['e2e'].get('ok'):
            continue
        cl = get_model_context_length(m, base_url=base, api_key=key, provider=prov)
        # expected: v3 short-name match else known-922k family else None
        short = m.split('/', 1)[1] if '/' in m else m
        v3e = V3.get(short)
        if v3e:
            expected = v3e['max_model_len']
        elif any(k in m for k in KNOWN_922K):
            expected = 922000
        else:
            expected = None
        rows[m] = {'hermes_resolved': cl, 'expected': expected,
                   'match': (expected is None) or (cl == expected)}
        bad = rows[m]['match'] is False
        flag = ' <<< MISMATCH' if bad else ''
        print(f"{slug:8s} {m:44s} hermes={cl} expected={expected}{flag}", flush=True)
    out[slug] = rows

Path('aide_footer_ctx_check.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
nmm = sum(1 for s in out.values() for v in s.values() if v['match'] is False)
print('MISMATCHES:', nmm)
