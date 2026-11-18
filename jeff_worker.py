"""Isolated CPU Jeff process. JSON-lines interface; never owns serial or SQLite."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.environ.setdefault('HF_HOME', str(ROOT / 'data' / 'cache' / 'huggingface'))
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')

TOOLS = {
    't1': 'Read the latest validated heart rate, SpO2, movement, alert priority and reported symptoms to explain the supplied interpretation guidance.',
    't2': 'Read recent numerical trends and ranges from the monitoring history.',
    't3': 'Read optical waveform quality and measurement availability.',
    't4': 'List, inspect or summarize recorded SOS/fall incidents and their acknowledgment status for the already selected patient.',
}


def load_client(download=False):
    os.environ['HF_HUB_OFFLINE'] = '0' if download else '1'
    from jeff import Jeff
    from jeff.catalogue import Catalogue
    catalogue = Catalogue.from_dir(ROOT / 'data' / 'jeff-source' / 'catalogue')
    return Jeff.local(['tools', 'ground'], backend='torch', catalogue=catalogue)


def decide(client, request):
    if request['operation'] == 'route':
        if request.get('passages'):
            decision = client.function('ground.rerank', labels=request['passages'])(request['question'])
        else:
            decision = client.function('tools.tool', context={
                'agent': 'A read-only monitoring dashboard assistant. Retrieve recorded evidence to summarize it. '
                         'The current device and patient enrollment are already selected. No patient name, ID or date is needed. '
                         'Do not diagnose, prescribe or modify records. Missing measurements stay unavailable.',
                'conversation': [],
            }, labels=TOOLS)(request['question'])
    elif request['operation'] == 'ground':
        decision = client.function('ground.grounding', context={
            'sources': request['sources'],
        })(request['answer'])
    else:
        raise ValueError('Unknown Jeff operation.')
    return decision.to_json()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true', help='Download weights and run a model smoke test')
    args = parser.parse_args()
    with contextlib.redirect_stdout(sys.stderr):
        client = load_client(download=args.prepare)
    if args.prepare:
        report = {'routing': decide(client, dict(operation='route', question='Show recent oxygen trends.'))}
        sources = 'Synthetic demonstration. Heart rate is 72 bpm. Oxygen saturation is 98%. Core temperature is unavailable.'
        for name, answer in [('supported', 'The recorded heart rate is 72 bpm.'),
                             ('contradicted', 'The recorded heart rate is 190 bpm.')]:
            report[name] = decide(client, dict(operation='ground', sources=sources, answer=answer))
        path = ROOT / 'models' / 'jeff.smoke.json'
        path.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'ready': True, 'report': str(path)}), flush=True)
        return
    print(json.dumps({'ready': True}), flush=True)
    for line in sys.stdin:
        try:
            if len(line) > 100_000:
                raise ValueError('Jeff request too large.')
            request = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                result = decide(client, request)
            response = {'decision': result}
        except Exception as exc:
            response = {'error': str(exc)}
        print(json.dumps(response, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
