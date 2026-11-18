"""Turn genuine raw recordings into reviewable windows and labeled training data."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from ppg_quality import RATE, WindowCollector, parse_raw_packet

REVIEW = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Review pulse recordings</title><style>
body{font:16px/1.6 system-ui;background:#f6f6f2;color:#242923;margin:0;padding:24px}
main{max-width:1000px;margin:auto}h1{font-size:28px}p{max-width:72ch}
svg{display:block;width:100%;height:260px;background:white;border:1px solid #b8bdb4}
button,select{font:inherit;padding:10px 16px;margin:6px 8px 6px 0;min-height:44px}
button{cursor:pointer}button:focus-visible,select:focus-visible{outline:3px solid #345c45;outline-offset:3px}
#identity{overflow-wrap:anywhere}#status{min-height:26px}button:disabled{cursor:default;opacity:.5}
</style><main><h1>Review pulse recordings</h1>
<p>Classify each ten-second waveform as usable for pulse analysis, unreliable, or uncertain.
Use waveform evidence and a reference measurement when available. Movement alone is not a quality label.
These labels do not establish oxygen-saturation accuracy.</p>
<p id="identity"></p><svg id="plot" viewBox="0 0 1000 260" role="img" aria-label="Recorded red and infrared waveforms"></svg>
<p>Red channel: violet. Infrared channel: ochre. Each trace is scaled independently.</p>
<label for="label">Reviewed quality</label><select id="label"><option value="">Not reviewed</option>
<option value="1">Usable</option><option value="0">Unreliable</option><option value="uncertain">Uncertain</option></select>
<div><button id="previous">Previous</button><button id="next">Next</button>
<button id="download">Download reviewed labels</button></div><p id="status" role="status"></p>
<p>Download your labels before closing this page. Ask a second reviewer to label a separate copy, then resolve disagreements.</p>
</main><script type="application/json" id="windows">__WINDOWS__</script><script>
'use strict';const windows=JSON.parse(document.getElementById('windows').textContent);let index=0;
const $=id=>document.getElementById(id);
function draw(){const w=windows[index];if(!w){$('identity').textContent='No complete windows found.';return;}
$('identity').textContent=`${index+1} of ${windows.length} · Participant ${w.participant} · Session ${w.session} · ${w.id}`;
$('label').value=w.label||'';let svg='';
for(const [key,color,center] of [['red','#7359a5',75],['ir','#856214',190]]){const values=w[key],low=Math.min(...values),span=Math.max(1,Math.max(...values)-low);
const d=values.map((v,i)=>`${i?'L':'M'}${(12+i/(values.length-1)*976).toFixed(2)},${(center+45-(v-low)/span*90).toFixed(2)}`).join('');
svg+=`<path d="${d}" stroke="${color}" fill="none" stroke-width="1.8"/>`;}
$('plot').innerHTML=svg;$('previous').disabled=index===0;$('next').disabled=index===windows.length-1;
$('status').textContent=`${windows.filter(w=>w.label!=='').length} reviewed; ${windows.filter(w=>['0','1'].includes(w.label)).length} binary labels ready.`;}
$('label').onchange=()=>{windows[index].label=$('label').value;draw();};
$('previous').onclick=()=>{index=Math.max(0,index-1);draw();};$('next').onclick=()=>{index=Math.min(windows.length-1,index+1);draw();};
$('download').onclick=()=>{const csv='id,label\\n'+windows.map(w=>w.id+','+w.label).join('\\n')+'\\n';
const url=URL.createObjectURL(new Blob([csv],{type:'text/csv'})),a=document.createElement('a');a.href=url;a.download='labels.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};draw();
</script></html>'''


def prepare(recordings, output, labels_path=None):
    output.mkdir(parents=True, exist_ok=True)
    labels = {}
    if labels_path:
        with labels_path.open(newline='') as stream:
            for row in csv.DictReader(stream):
                if row['id'] in labels:
                    raise ValueError('Duplicate reviewed window ID.')
                labels[row['id']] = row['label'].strip()
    windows = []
    for recording in sorted(recordings.rglob('*.jsonl')):
        collector = WindowCollector()
        identity = None
        for line in recording.read_text().splitlines():
            record = json.loads(line)
            participant, session = record['participant'], record['session']
            if not isinstance(participant, str) or not participant or not isinstance(session, str) or not session:
                raise ValueError('Each recording needs participant/session aliases.')
            packet = parse_raw_packet('[PPG] ' + json.dumps(record['packet']))
            if packet is None:
                raise ValueError(f'Invalid raw packet in {recording.name}.')
            if identity != (participant, session):
                collector = WindowCollector()
                identity = (participant, session)
            if collector.append(packet):
                samples = list(collector.samples)
                unique = f'{participant}/{session}/{packet["boot_id"]}/{packet["seq_start"]}'
                window_id = hashlib.sha256(unique.encode()).hexdigest()[:20]
                windows.append(dict(id=window_id, participant=participant, session=session,
                    label=labels.get(window_id, ''), start_ms=samples[0][0],
                    red=[row[1] for row in samples], ir=[row[2] for row in samples]))
                # Nonoverlapping windows with continuity retained between them.
                collector.samples.clear()
    if not windows:
        raise ValueError('No complete ten-second windows found. Record continuous raw samples first.')
    if len({w['id'] for w in windows}) != len(windows):
        raise ValueError('Duplicate session recordings detected; use unique session aliases.')
    unknown = set(labels) - {w['id'] for w in windows}
    if unknown:
        raise ValueError('Reviewed labels do not match these recordings.')
    (output / 'windows.json').write_text(json.dumps(windows) + '\n')
    encoded = json.dumps(windows).replace('<', '\\u003c')
    (output / 'review.html').write_text(REVIEW.replace('__WINDOWS__', encoded))
    if not labels_path:
        with (output / 'labels-template.csv').open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['id', 'label'])
            writer.writerows((w['id'], '') for w in windows)
    reviewed = [w for w in windows if w['label'] in ('0', '1')]
    if labels_path:
        if any(label not in ('', '0', '1', 'uncertain') for label in labels.values()):
            raise ValueError('Labels must be 0, 1, uncertain, or blank.')
        if not reviewed:
            raise ValueError('No usable binary labels yet. Review the windows first.')
        np.savez_compressed(output / 'training.npz', red=[w['red'] for w in reviewed],
            ir=[w['ir'] for w in reviewed], labels=[int(w['label']) for w in reviewed],
            groups=[w['participant'] for w in reviewed], ids=[w['id'] for w in reviewed],
            domain='MAX30102 local pilot', sample_rate_hz=RATE)
    print(f'{len(windows)} complete windows; {len(reviewed)} binary reviewed labels. Open {output / "review.html"}')
    return windows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recordings', type=Path, default=Path('data/ppg'))
    parser.add_argument('--output', type=Path, default=Path('data/local-quality'))
    parser.add_argument('--labels', type=Path)
    args = parser.parse_args()
    prepare(args.recordings, args.output, args.labels)


if __name__ == '__main__':
    main()
