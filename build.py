#!/usr/bin/env python3
"""Build the debug shell of an iOS guest: ownervisor (the service manager), its client and test child, the shell it serves
-- applebox, dropbear, zsh, debugserver, libimobiledevice -- and its built-in services.

  build.py OUT_DIR [--only PART,...] [--applebox DIR]

PARTS (each built in OUT_DIR/<part>, which keeps its downloads and objects for the next build):
  manager           ownervisor, ownerctl, ownertest (manager/)
  applebox          Apple's command-line tools as one multicall binary, from github.com/Droid-VM/applebox at the commit
                    pinned below (--applebox DIR takes another checkout), signed with entitlements/debug.plist
  dropbear, zsh, debugserver, libimobiledevice      tools/<part>.py

Then OUT_DIR/bin holds every binary, and a link per command of a multicall binary (libimobiledevice's tools), as they go
under /private/var/ngpu/bin of the guest; OUT_DIR/services.d and OUT_DIR/enabled the built-in services (services/) as they go
under ownervisor's root; OUT_DIR/debug-shell.json each binary's CDHash (the device must trust every one: an owner trust
cache), the links and the services. --only builds those parts again and collects the rest as earlier builds left them.
Needs a Mac with Xcode (the iphoneos and macOS SDKs)."""
import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path
# DROIDVM_IOS_TARGET picks the build: arm64-apple-ios17.0 (the default) or arm64e-apple-ios27.0 (iPadOS 27 runs no arm64 platform
# binaries: it killed them at exec).
TARGET = os.environ.get('DROIDVM_IOS_TARGET', 'arm64-apple-ios17.0')
ARCH, IOS = TARGET.split('-', 1)[0], TARGET.rsplit('ios', 1)[1]

HERE = Path(__file__).resolve().parent
PARTS = ['manager', 'applebox', 'dropbear', 'zsh', 'debugserver', 'libimobiledevice']
APPLEBOX = ('https://github.com/Droid-VM/applebox.git', '2307bb9a14d949c8a0056bf2f339822a5f978505')
MANAGER = ('ownervisor', 'ownerctl', 'ownertest')


def sign(binary, identifier, entitlements):
    subprocess.run(['codesign', '--force', '--sign', '-', '--pagesize', '4096', '--identifier', identifier,
                    '--entitlements', entitlements, binary], check=True)
    detail = subprocess.run(['codesign', '--display', '--verbose=4', binary], capture_output=True, text=True,
                            check=True).stderr
    assert re.search(r'^Page size=4096$', detail, re.M), 'the signature must use 4 KiB pages'
    return re.search(r'^CDHash=([a-f0-9]{40})$', detail, re.M)[1]


def build_manager(out):
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
    base = ['xcrun', 'clang', '-target', TARGET, '-isysroot', sdk, '-O2', '-Wall', '-Wextra', '-Werror',
            '-fobjc-arc', '-framework', 'Foundation']
    entitlements = out / 'entitlements.plist'
    entitlements.write_bytes(plistlib.dumps({'com.apple.private.security.no-container': True}))
    binaries = {}
    for name in MANAGER:
        subprocess.run([*base, HERE / 'manager' / f'{name}.m', '-o', out / name], check=True)
        binaries[name] = sign(out / name, f'org.droidvm.{name}', entitlements)
    (out / 'record.json').write_text(json.dumps({'binaries': binaries, 'source': 'manager/'}, indent=2) + '\n')


def build_applebox(out, checkout):
    if checkout is None:
        url, commit = APPLEBOX
        checkout = out / 'source'
        if not (checkout / '.git').is_dir():
            checkout.mkdir(parents=True, exist_ok=True)
            subprocess.run(['git', '-C', checkout, 'init', '-q'], check=True)
            subprocess.run(['git', '-C', checkout, 'remote', 'add', 'origin', url], check=True)
        subprocess.run(['git', '-C', checkout, 'fetch', '-q', '--depth', '1', 'origin', commit], check=True)
        subprocess.run(['git', '-C', checkout, 'checkout', '-q', '-f', '--detach', commit], check=True)
    subprocess.run([sys.executable, Path(checkout) / 'build.py', out, '--entitlements', HERE / 'entitlements/debug.plist',
                    '--identifier', 'org.droidvm.applebox'], check=True)
    built = json.loads((out / 'applebox.json').read_text())
    (out / 'record.json').write_text(json.dumps(
        {'binaries': {'applebox': built['cdhash']}, 'commands': built['commands'], 'source': built['source']}, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('out', type=Path)
    parser.add_argument('--only', help='parts to build again, separated by commas')
    parser.add_argument('--applebox', type=Path, default=os.environ.get('APPLEBOX') or None,
                        help='a checkout of applebox to build instead of the pinned commit (default: $APPLEBOX)')
    args = parser.parse_args()
    out = args.out.resolve()
    wanted = args.only.split(',') if args.only else PARTS
    for part in wanted:
        if part not in PARTS:
            sys.exit(f'unknown part {part}; parts: {" ".join(PARTS)}')
        work = out / part
        work.mkdir(parents=True, exist_ok=True)
        (work / 'record.json').unlink(missing_ok=True)
        print(f'== {part}', flush=True)
        if part == 'manager':
            build_manager(work)
        elif part == 'applebox':
            build_applebox(work, args.applebox.resolve() if args.applebox else None)
        else:
            subprocess.run([sys.executable, HERE / 'tools' / f'{part}.py', work], check=True)

    # Collect: the binaries and links as they go into the guest, the services, one record of everything.
    for name in ('bin', 'services.d', 'enabled'):
        if (out / name).exists():
            shutil.rmtree(out / name)
        (out / name).mkdir()
    binaries, links, sources = {}, {}, {}
    for part in PARTS:
        record_file = out / part / 'record.json'
        if not record_file.is_file():
            sys.exit(f'{part} has not been built: build.py {out} --only {part}')
        record = json.loads(record_file.read_text())
        for name, cdhash in record['binaries'].items():
            shutil.copy2(out / part / name, out / 'bin' / name)
            binaries[name] = cdhash
        for name, target in record.get('links', {}).items():
            os.symlink(target, out / 'bin' / name)
            links[name] = target
        sources[part] = record.get('source', '')
    autostart = [line.strip() for line in (HERE / 'services/autostart').read_text().splitlines()
                 if line.strip() and not line.startswith('#')]
    services = sorted(p.stem for p in (HERE / 'services').glob('*.json'))
    for name in services:
        shutil.copyfile(HERE / 'services' / f'{name}.json', out / 'services.d' / f'{name}.json')
    for name in autostart:
        if name not in services:
            sys.exit(f'services/autostart names {name}, which services/ does not define')
        (out / 'enabled' / name).write_text('')
    (out / 'debug-shell.json').write_text(json.dumps(
        {'binaries': binaries, 'links': links, 'services': services, 'autostart': autostart, 'sources': sources},
        indent=2) + '\n')
    print(f'debug shell: {len(binaries)} binaries, {len(links)} links, services {", ".join(services)}; '
          f'autostart {", ".join(autostart)} -> {out}')


if __name__ == '__main__':
    main()
