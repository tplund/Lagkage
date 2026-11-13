"""Udgiv en ny version af Lagkage.

    .venv\\Scripts\\python.exe release.py 1.2 "Kort beskrivelse af, hvad der er nyt"

Sætter versionsnummeret, bygger exe og installer, committer, tagger og lægger
installeren ud som en GitHub-udgivelse. Installerede kopier finder den selv ved
næste opstart.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(ROOT, '.venv', 'Scripts', 'python.exe')
ISCC = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Inno Setup 6', 'ISCC.exe')


def run(*cmd):
    print('>', ' '.join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def main():
    if len(sys.argv) < 2 or not re.fullmatch(r'\d+\.\d+(\.\d+)?', sys.argv[1]):
        sys.exit(__doc__)
    ver = sys.argv[1]
    notes = sys.argv[2] if len(sys.argv) > 2 else f'Lagkage {ver}'
    tag = f'v{ver}'
    if subprocess.run(['git', 'rev-parse', '-q', '--verify', f'refs/tags/{tag}'], cwd=ROOT,
                      capture_output=True).returncode == 0:
        sys.exit(f'{tag} findes allerede.')

    with open(os.path.join(ROOT, 'lagkage', '__init__.py'), 'w', encoding='utf-8') as f:
        f.write(f'__version__ = "{ver}"\n')

    run(PY, '-m', 'PyInstaller', '--noconfirm', '--windowed', '--name', 'Lagkage',
        '--icon', 'lagkage/lagkage.ico', '--add-data', 'lagkage/lagkage.ico;lagkage',
        '--collect-binaries', 'onnxruntime', '--exclude-module', 'tkinter',
        '--exclude-module', 'matplotlib', '--log-level', 'WARN', 'run.py')
    run(ISCC, '/Q', f'/DMyAppVersion={ver}', r'installer\Lagkage.iss')
    setup = os.path.join(ROOT, 'installer', 'Output', f'Lagkage-Setup-{ver}.exe')
    assert os.path.exists(setup), setup

    run('git', 'add', '-A')
    run('git', 'commit', '-m', f'Version {ver}\n\n{notes}\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>')
    run('git', 'tag', tag)
    run('git', 'push')
    run('git', 'push', 'origin', tag)
    run('gh', 'release', 'create', tag, setup, '--title', f'Lagkage {ver}', '--notes', notes)
    print(f'\nUdgivet: {setup}')


if __name__ == '__main__':
    main()
