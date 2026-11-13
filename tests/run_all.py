"""Kør alle tests: .venv\Scripts\python.exe tests\run_all.py"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
env = dict(os.environ, PYTHONUTF8='1')
ok_total = fail_total = 0
for name in sorted(f for f in os.listdir(HERE) if f.startswith('test_') and f.endswith('.py')):
    r = subprocess.run([sys.executable, os.path.join(HERE, name)], capture_output=True, text=True, env=env,
                       timeout=600)
    lines = (r.stdout + r.stderr).splitlines()
    ok = sum(l.startswith('OK') for l in lines)
    fails = [l for l in lines if l.startswith('FAIL') or 'Traceback' in l or 'Error' in l]
    ok_total += ok
    fail_total += len(fails)
    print(f'{name}: {ok} OK' + (f', {len(fails)} fejl' if fails else ''))
    for l in fails:
        print('   ', l)
print(f'\nI alt: {ok_total} OK, {fail_total} fejl')
sys.exit(1 if fail_total else 0)
