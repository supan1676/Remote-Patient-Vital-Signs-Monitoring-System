"""Exercise actual local Jeff/LLM integration against the explicitly simulated bridge."""
import argparse
import json
from pathlib import Path
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8080')
    parser.add_argument('--output', type=Path, default=Path('data/assistant-verification.json'))
    args = parser.parse_args()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(path, payload=None):
        req = urllib.request.Request(args.url + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Content-Type': 'application/json'})
        with opener.open(req, timeout=10) as response:
            return json.loads(response.read())
    telemetry = request('/api/telemetry')
    if not telemetry['hardware'].get('simulation'):
        raise ValueError('This check requires --simulate and does not use real monitoring data.')
    results = []
    for question in ('Summarize the latest readings.', 'Summarize recent oxygen trends.',
                     'Summarize the optical signal quality.', 'Summarize recorded incidents.'):
        started = time.monotonic()
        job = request('/api/assistant', dict(question=question, device_id=telemetry['latest']['device_id']))
        while job['status'] in ('queued', 'running'):
            if time.monotonic() - started > 240:
                raise TimeoutError('Assistant check timed out.')
            time.sleep(1)
            job = request('/api/assistant/job?id=' + job['id'])
        results.append(dict(job, elapsed_seconds=round(time.monotonic() - started, 2)))
        print(json.dumps({k: job.get(k) for k in ('question', 'status', 'summary', 'message', 'tool')}), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(source='synthetic live simulator with actual models', results=results), indent=2) + '\n')
    if not any(j['status'] == 'complete' for j in results):
        raise RuntimeError('No summary completed the real model pipeline; inspect the report.')
    if any(j['status'] == 'error' for j in results):
        raise RuntimeError('A real model call failed; inspect the report.')
    print('Real model verification saved to', args.output)


if __name__ == '__main__':
    main()
