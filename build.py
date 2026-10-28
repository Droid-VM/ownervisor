#!/usr/bin/env python3
"""Build ownervisor, ownerctl and ownertest for iOS (arm64, iOS 17), signed ad hoc with 4 KiB pages.

  build.py OUT_DIR [--entitlements PLIST] [--identifier-prefix PREFIX] [--deployment-target VERSION]

Writes OUT_DIR/{ownervisor,ownerctl,ownertest} and OUT_DIR/ownervisor.json: each binary's CDHash, which the device has to
trust (an owner trust cache) -- AMFI checks a binary's hash at exec. The default entitlements are only
com.apple.private.security.no-container (an owner process may exec it). Needs Xcode with the iphoneos SDK."""
import argparse
import json
import plistlib
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BINARIES = ('ownervisor', 'ownerctl', 'ownertest')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('out', type=Path)
    parser.add_argument('--entitlements', type=Path, help='entitlements plist to sign with')
    parser.add_argument('--identifier-prefix', default='org.droidvm', help='code signing identifier prefix')
    parser.add_argument('--deployment-target', default='17.0', help='minimum iOS version (default 17.0)')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    entitlements = args.entitlements.resolve() if args.entitlements else out / 'entitlements.plist'
    if not args.entitlements:
        entitlements.write_bytes(plistlib.dumps({'com.apple.private.security.no-container': True}))
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
    base = ['xcrun', 'clang', '-target', f'arm64-apple-ios{args.deployment_target}', '-isysroot', sdk, '-O2', '-Wall',
            '-Wextra', '-Werror', '-fobjc-arc', '-framework', 'Foundation']
    cdhashes = {}
    for name in BINARIES:
        binary = out / name
        subprocess.run([*base, HERE / f'{name}.m', '-o', binary], check=True)
        subprocess.run(['codesign', '--force', '--sign', '-', '--pagesize', '4096', '--identifier',
                        f'{args.identifier_prefix}.{name}', '--entitlements', entitlements, binary], check=True)
        detail = subprocess.run(['codesign', '--display', '--verbose=4', binary], capture_output=True, text=True,
                                check=True).stderr
        assert re.search(r'^Page size=4096$', detail, re.M), 'the signature must use 4 KiB pages'
        cdhashes[name] = re.search(r'^CDHash=([a-f0-9]{40})$', detail, re.M)[1]
        print(f'{name} CDHash', cdhashes[name])
    (out / 'ownervisor.json').write_text(json.dumps(
        {'cdhashes': cdhashes, 'entitlements': str(entitlements), 'identifier_prefix': args.identifier_prefix}, indent=2) + '\n')


if __name__ == '__main__':
    main()
