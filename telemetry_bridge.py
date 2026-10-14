#!/usr/bin/env python3
"""Serve the dashboard and relay fresh ESP32 JSON packets over SSE."""
import argparse
import json
import math
import os
import queue
import sqlite3
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from telemetry_store import TelemetryStore
from personal_baseline import PersonalBaseline

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    # Also support the existing PlatformIO pipx installation.
    candidates = list(Path.home().glob('.local/share/pipx/venvs/platformio/lib/python*/site-packages'))
    if candidates:
        sys.path.append(str(candidates[0]))
    try:
        import serial
        from serial.tools import list_ports
    except ImportError:
        serial = None

STALE_SECONDS = 5.0
latest_telemetry = None
last_packet_time = None
hardware_status = dict(connected=False, port=None, baud=115200, error=None,
                       packets_received=0, device_id=None)
state_lock = threading.Lock()
sse_clients = []
sse_lock = threading.Lock()
telemetry_store = None
personal_baseline = None
latest_comparisons = {}
last_alerts = {}


def find_serial_port():
    """Select a single USB serial device; never guess when several are attached."""
    if serial is None:
        return None
    ports = [p.device for p in list_ports.comports() if p.vid is not None]
    return ports[0] if len(ports) == 1 else None


def parse_packet(line):
    text = line.removeprefix('[JSON]').strip()
    if not text.startswith('{'):
        return None
    try:
        packet = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(packet, dict) or not isinstance(packet.get('device_id'), str):
        return None
    if not all(isinstance(packet.get(key), dict) for key in ('vitals', 'sensors', 'alerts')):
        return None
    uptime = packet.get('uptime_s')
    if isinstance(uptime, bool) or not isinstance(uptime, (int, float)) or not math.isfinite(uptime) or uptime < 0:
        return None
    # Reject NaN/Infinity and wrong field types before they reach JSON consumers.
    for key, value in packet['vitals'].items():
        if key == 'finger_on':
            if not isinstance(value, bool):
                return None
        elif value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            return None
    return packet


def snapshot():
    with state_lock:
        status = hardware_status.copy()
        fresh = last_packet_time is not None and time.monotonic() - last_packet_time < STALE_SECONDS
        if not fresh and status['connected']:
            status.update(connected=False, error='Telemetry timed out; waiting for fresh packets.')
        return {'status': status, 'telemetry': latest_telemetry if fresh and status['connected'] else None,
                'comparisons': latest_comparisons if fresh and status['connected'] else {}}


def broadcast():
    payload = snapshot()
    with sse_lock:
        for client in sse_clients:
            try:
                client.put_nowait(payload)
            except queue.Full:
                # Slow browsers must not block acquisition from the serial port.
                try:
                    client.get_nowait()
                except queue.Empty:
                    pass
                client.put_nowait(payload)


def set_disconnected(message):
    global latest_telemetry, last_packet_time
    with state_lock:
        latest_telemetry = None
        last_packet_time = None
        hardware_status.update(connected=False, error=message)
    broadcast()


def serial_reader_thread(port=None):
    global latest_telemetry, last_packet_time, latest_comparisons
    if serial is None:
        set_disconnected('pyserial is missing. Install with: pip install pyserial')
        return
    while True:
        target = port or find_serial_port()
        with state_lock:
            hardware_status['port'] = target
        if target is None:
            set_disconnected('Connect one USB serial device or select it with --serial-port.')
            time.sleep(2)
            continue
        ser = None
        try:
            ser = serial.Serial(port=None, baudrate=115200, timeout=0.5)
            ser.dtr = False
            ser.rts = False
            ser.port = target
            if os.name == 'posix':
                ser.exclusive = True
            ser.open()
            set_disconnected('Serial port open; waiting for ESP32 telemetry.')
            print(f'[SERIAL] Opened {target}; waiting for JSON packets.', flush=True)
            buffer = bytearray()
            while True:
                buffer.extend(ser.read(ser.in_waiting or 1))
                if len(buffer) > 65536:
                    buffer.clear()
                while b'\n' in buffer:
                    line, _, remaining = buffer.partition(b'\n')
                    buffer = bytearray(remaining)
                    packet = parse_packet(line.decode('utf-8', errors='replace').strip())
                    if packet is None:
                        continue
                    packet['_received_at'] = time.time()
                    with state_lock:
                        latest_telemetry = packet
                        last_packet_time = time.monotonic()
                        hardware_status['packets_received'] += 1
                        hardware_status.update(connected=True, error=None, device_id=packet['device_id'])
                    if telemetry_store is not None:
                        try:
                            telemetry_store.record(packet)
                            if personal_baseline is not None:
                                latest_comparisons = personal_baseline.compare(packet)
                                for kind in ('sos', 'fall'):
                                    key = (packet['device_id'], kind)
                                    active = packet['alerts'].get(kind) is True
                                    if active and not last_alerts.get(key):
                                        with telemetry_store.lock, telemetry_store.db:
                                            enrollment = personal_baseline.summary(packet['device_id']).get('id')
                                            telemetry_store.db.execute('INSERT INTO events(enrollment_id,device_id,recorded_at,kind,detail) VALUES(?,?,?,?,?)',
                                                (enrollment,packet['device_id'],time.time(),kind,'SOS button activated.' if kind == 'sos' else 'Device reported a possible fall.'))
                                    last_alerts[key] = active
                            hardware_status.pop('storage_error', None)
                        except sqlite3.Error as exc:
                            hardware_status['storage_error'] = str(exc)
                    broadcast()
                if hardware_status['connected'] and not snapshot()['status']['connected']:
                    set_disconnected('Telemetry timed out; waiting for fresh packets.')
        except (OSError, serial.SerialException) as exc:
            set_disconnected(str(exc))
            print(f'[SERIAL] {target}: {exc}', flush=True)
        finally:
            if ser is not None:
                ser.close()
        time.sleep(2)


class TelemetryRequestHandler(SimpleHTTPRequestHandler):
    def send_json(self, payload, status=200):
        body = json.dumps(payload, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path in ('/api/baseline', '/api/events'):
            if personal_baseline is None:
                return self.send_json({'error': 'Baseline service is not running.'}, 503)
            device = parse_qs(url.query).get('device_id', [hardware_status.get('device_id')])[0]
            if url.path == '/api/events':
                return self.send_json({'events': personal_baseline.events(device)})
            return self.send_json(personal_baseline.summary(device))
        if url.path == '/api/history':
            if telemetry_store is None:
                return self.send_json({'error': 'History storage is not running.'}, 503)
            params = parse_qs(url.query)
            device = params.get('device_id', [hardware_status.get('device_id')])[0]
            try:
                seconds = int(params.get('seconds', ['900'])[0])
            except ValueError:
                return self.send_json({'error': 'seconds must be an integer.'}, 400)
            return self.send_json(telemetry_store.history(device, seconds))
        if self.path == '/api/telemetry':
            state = snapshot()
            body = json.dumps({'hardware': state['status'], 'latest': state['telemetry']}, allow_nan=False).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
        elif self.path == '/api/stream':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            client = queue.Queue(maxsize=8)
            with sse_lock:
                sse_clients.append(client)
            try:
                payload = snapshot()
                while True:
                    self.wfile.write(('data: ' + json.dumps(payload, allow_nan=False) + '\n\n').encode())
                    self.wfile.flush()
                    try:
                        payload = client.get(timeout=1)
                    except queue.Empty:
                        payload = snapshot()
            except (OSError, ConnectionError):
                pass
            finally:
                with sse_lock:
                    sse_clients.remove(client)
        elif url.path in ('/', '/index.html', '/dashboard.html', '/wiring-guide.html') or url.path in ('/assets/dashboard.css', '/assets/dashboard.js', '/assets/fonts/fira-sans-regular.ttf', '/assets/fonts/fira-sans-medium.ttf', '/assets/fonts/fira-sans-semibold.ttf'):
            super().do_GET()
        else:
            self.send_error(404)


    def do_POST(self):
        if self.path != '/api/baseline' or personal_baseline is None:
            return self.send_json({'error': 'Endpoint unavailable.'}, 404)
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            return self.send_json({'error': 'Use the local dashboard to update collection.'}, 403)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096:
                raise ValueError('Invalid request size.')
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError('Expected a JSON object.')
            device = payload.get('device_id')
            if not isinstance(device, str) or device != hardware_status.get('device_id'):
                raise ValueError('Select the currently connected device.')
            if payload.get('action') == 'start':
                if not snapshot()['status']['connected']:
                    raise ValueError('Connect the device before starting collection.')
                person = payload.get('person')
                if not isinstance(person, str):
                    raise ValueError('Enter a name or alias.')
                return self.send_json(personal_baseline.start(device, person))
            if payload.get('action') == 'end':
                personal_baseline.end(device)
                return self.send_json(personal_baseline.summary(device))
            raise ValueError('Unknown collection action.')
        except (ValueError, TypeError) as exc:
            return self.send_json({'error': str(exc)}, 400)


def main():
    global telemetry_store, personal_baseline
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port', nargs='?', type=int, default=8080, help='HTTP port (default: 8080)')
    parser.add_argument('--serial-port', help='Explicit serial port, for example /dev/ttyACM0 or COM6')
    parser.add_argument('--database', default=str(Path(__file__).resolve().parent / 'data' / 'telemetry.sqlite3'))
    args = parser.parse_args()
    telemetry_store = TelemetryStore(args.database)
    personal_baseline = PersonalBaseline(telemetry_store)
    handler = partial(TelemetryRequestHandler, directory=str(Path(__file__).resolve().parent))
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler)
    threading.Thread(target=serial_reader_thread, args=(args.serial_port,), daemon=True).start()
    print(f'Dashboard: http://localhost:{args.port}/index.html', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
