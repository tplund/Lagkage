"""Selvopdatering: tjek den seneste udgivelse på GitHub, hent installeren og kør den."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.request

from PySide6.QtCore import QObject, Signal

from . import __version__

REPO = 'tplund/Lagkage'
API = f'https://api.github.com/repos/{REPO}/releases/latest'


def parse(v):
    v = v.strip().lstrip('vV')
    out = []
    for part in v.split('.'):
        num = ''.join(ch for ch in part if ch.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out + [0] * (3 - len(out)))


def is_installed():
    """Kun installerede kopier opdaterer sig selv (ikke udviklingsbygget i C:\\_proj)."""
    if not getattr(sys, 'frozen', False):
        return False
    return os.path.exists(os.path.join(os.path.dirname(sys.executable), 'unins000.exe'))


def latest_release(timeout=10):
    req = urllib.request.Request(API, headers={'Accept': 'application/vnd.github+json',
                                               'User-Agent': 'Lagkage-updater'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    asset = next((a for a in data.get('assets', [])
                  if a['name'].lower().endswith('.exe') and 'setup' in a['name'].lower()), None)
    if asset is None:
        return None
    return dict(version=data['tag_name'].lstrip('vV'), url=asset['browser_download_url'],
                size=asset.get('size', 0), notes=data.get('body') or '', name=asset['name'])


def newer_than_current(info, current=__version__):
    return info is not None and parse(info['version']) > parse(current)


class UpdateChecker(QObject):
    found = Signal(dict)
    none = Signal(str)

    def check(self, quiet=True):
        def run():
            try:
                info = latest_release()
            except Exception as e:  # ingen net, GitHub nede osv.
                if not quiet:
                    self.none.emit(f'Kunne ikke tjekke for opdateringer ({e}).')
                return
            if newer_than_current(info):
                self.found.emit(info)
            elif not quiet:
                self.none.emit(f'Du har den nyeste version ({__version__}).')
        threading.Thread(target=run, daemon=True).start()


def download(info, progress=None):
    path = os.path.join(tempfile.gettempdir(), info['name'])
    req = urllib.request.Request(info['url'], headers={'User-Agent': 'Lagkage-updater'})
    with urllib.request.urlopen(req, timeout=60) as r, open(path + '.part', 'wb') as f:
        total = int(r.headers.get('Content-Length') or info.get('size') or 0)
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and progress(done, total) is False:
                f.close()
                os.remove(path + '.part')
                return None
    os.replace(path + '.part', path)
    return path


def run_installer(path):
    """Start installeren i stille tilstand; den lukker Lagkage, opdaterer og starter programmet igen."""
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([path, '/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CLOSEAPPLICATIONS'],
                     creationflags=flags, close_fds=True)
