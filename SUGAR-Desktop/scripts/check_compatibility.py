#!/usr/bin/env python3
"""Check Mach-O deployment targets, including libraries inside PyInstaller archives."""
import argparse
import re
import subprocess
import tempfile
from pathlib import Path


def version(value):
    parts = tuple(map(int, value.split('.')))
    return parts + (0,) * (3 - len(parts))


def check(path, label, minimum, arch):
    output = subprocess.check_output(['xcrun', 'otool', '-l', str(path)], text=True)
    versions = re.findall(r'^\s*minos\s+([\d.]+)', output, re.M)
    versions += re.findall(r'cmd LC_VERSION_MIN_MACOSX\s+cmdsize \d+\s+version ([\d.]+)', output)
    if not versions:
        raise RuntimeError(f'{label}: no macOS deployment target found')
    errors = [f'{label}: requires macOS {v} (target {minimum})'
              for v in versions if version(v) > version(minimum)]
    arches = subprocess.check_output(['lipo', '-archs', str(path)], text=True).split()
    if arch not in arches:
        errors.append(f'{label}: missing {arch}; found {arches}')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', type=Path)
    parser.add_argument('--minimum', default='13.0')
    parser.add_argument('--arch', required=True, choices=['arm64', 'x86_64'])
    parser.add_argument('--archive', action='store_true')
    args = parser.parse_args()
    errors = check(args.binary, str(args.binary), args.minimum, args.arch)
    count = 1
    if args.archive:
        from PyInstaller.archive.readers import CArchiveReader
        archive = CArchiveReader(str(args.binary))
        with tempfile.TemporaryDirectory() as directory:
            for name, entry in archive.toc.items():
                if entry[-1] != 'b':
                    continue
                # Never use archive paths as extraction destinations.
                path = Path(directory) / 'binary'
                data = archive.extract(name)
                if data[:4] not in (b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe',
                                    b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe',
                                    b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
                                    b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'):
                    continue  # PyInstaller also labels some data files as binaries.
                path.write_bytes(data)
                errors.extend(check(path, name, args.minimum, args.arch))
                count += 1
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'Checked {count} binaries: deployment targets <= macOS {args.minimum}, architecture {args.arch}.')


if __name__ == '__main__':
    main()
