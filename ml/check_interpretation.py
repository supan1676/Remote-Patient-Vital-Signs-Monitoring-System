"""Actual-model checks of symptom-aware interpretation, using the simulator only."""
import json
from pathlib import Path
import time
import urllib.request


def main():
    base = 'http://127.0.0.1:8080'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(path, payload=None):
        req = urllib.request.Request(base + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Content-Type': 'application/json'})
        with opener.open(req, timeout=10) as response:
            return json.loads(response.read())
    state = request('/api/telemetry')
    if not state['hardware'].get('simulation'):
        raise ValueError('This check requires the isolated --simulate mode.')
    cases = [('unknown', []), ('reported', ['cough', 'feverish']), ('reported', ['severe_breathing'])]
    results = []
    for status, selected in cases:
        start = time.monotonic()
        result = request('/api/assistant', dict(device_id=state['latest']['device_id'],
            question='Interpret the latest readings and symptoms.', symptoms=dict(status=status, selected=selected)))
        immediate = time.monotonic() - start
        assert 'not a final medical evaluation' in result['assessment']['disclaimer']
        if 'severe_breathing' in selected:
            assert result['assessment']['level'] == 'emergency'
            assert immediate < 5
        while result['status'] in ('queued', 'running'):
            if time.monotonic() - start > 240:
                raise TimeoutError('Interpretation took too long.')
            time.sleep(1)
            result = request('/api/assistant/job?id=' + result['id'])
        results.append(dict(result, elapsed_seconds=round(time.monotonic() - start, 2),
                            immediate_guidance_seconds=round(immediate, 3)))
        print(json.dumps({k: result.get(k) for k in ('status', 'summary', 'message')}), flush=True)
    out = Path('data/interpretation-verification.json')
    out.write_text(json.dumps(dict(source='actual local models and synthetic live readings', results=results), indent=2) + '\n')
    assert any(r['status'] == 'complete' for r in results), 'No actual AI explanation passed checks.'
    assert not any(r['status'] == 'error' for r in results), 'A model call failed.'
    assert results[-1]['status'] == 'complete', 'The emergency case did not produce an AI explanation.'
    assert results[-1]['generation']['model'] == 'qwen3:1.7b'
    print('Actual interpretation checks saved to', out)


if __name__ == '__main__':
    main()
