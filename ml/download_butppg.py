"""Download the openly licensed BUT PPG v2 benchmark from PhysioNet."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

URL = 'https://physionet-open.s3.amazonaws.com/butppg/butppg-2.0.0.zip'
SOURCE = 'https://physionet.org/content/butppg/2.0.0/'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('data/butppg'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    archive = args.output / 'butppg-2.0.0.zip'
    if not archive.exists():
        temporary = archive.with_suffix('.download')
        print('Downloading BUT PPG v2 from PhysioNet (about 87 MB).', flush=True)
        with urllib.request.urlopen(URL, timeout=60) as response, temporary.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        temporary.replace(archive)
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            target = (args.output / member.filename).resolve()
            if not target.is_relative_to(args.output.resolve()):
                raise ValueError('Unsafe archive path.')
        zipped.extractall(args.output)
    with archive.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    metadata = dict(source=SOURCE, download=URL, version='2.0.0', license='CC BY 4.0', sha256=checksum)
    (args.output / 'download.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print('Dataset extracted to', args.output)


if __name__ == '__main__':
    main()
