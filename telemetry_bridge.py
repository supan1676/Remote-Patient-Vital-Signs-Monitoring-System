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

from personal_baseline import PersonalBaseline
from telemetry_store import TelemetryStore
from temperature_safety import CORE_STATUS, FEVER_MESSAGE

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    # Also support the existing PlatformIO pipx installation.
    candidates = list(Path.home().glob(
        '.local/share/pipx/venvs/platformio/lib/python*/site-packages'))
    if candidates:
        sys.path.append(str(candidates[0]))
    try:
        import serial
        from serial.tools import list_ports
    except ImportError:
        serial = None

STALE_SECONDS = 5.0
SENSOR_STATUSES = {
    'valid', 'warming_up', 'low_quality', 'stale',
    'sensor_error', 'not_available', 'unverified',
}
ACTUAL_SENSOR_STATUSES = SENSOR_STATUSES - {'unverified'}
INSTALLED_SENSORS = ('max', 'mpu', 'tmp117')
VITAL_NUMERIC_FIELDS = {
    'raw_ir': (0, 262143),
    'raw_red': (0, 262143),
    # Firmware reports peak-to-peak / mean * 100 over 100 positive samples.
    # That diagnostic ratio can exceed 20%; its mathematical upper bound is
    # 100 * window length. Do not drop valid telemetry (including SOS) at 20%.
    'optical_perfusion_index': (0, 10_000),
    'temp_object': (-70, 380),
    'temp_amb': (-70, 380),
    'sht40_temp_c': (-40, 125),
    'sht40_humidity_pct': (0, 100),
    'steps': (0, 10_000_000),
}

latest_telemetry = None
last_packet_time = None
hardware_status = dict(
    connected=False, port=None, baud=115200, error=None,
    packets_received=0, duplicates_skipped=0, invalid_packets=0,
    device_id=None)
state_lock = threading.Lock()
sse_clients = []
sse_lock = threading.Lock()
telemetry_store = None
personal_baseline = None
latest_comparisons = {}
last_alerts = {}


class DuplicateSuppressor:
    """Suppress an identical JSON line repeated by the serial stream."""

    def __init__(self, window=1.5):
        self.window = window
        self.last_text = None
        self.last_time = 0.0

    def duplicate(self, text, now=None):
        now = time.monotonic() if now is None else now
        duplicate = (text == self.last_text and
                     now - self.last_time < self.window)
        if not duplicate:
            self.last_text = text
            self.last_time = now
        return duplicate


duplicate_suppressor = DuplicateSuppressor()


def find_serial_port():
    """Select a single USB serial device; never guess when several are attached."""
    if serial is None:
        return None
    ports = [p.device for p in list_ports.comports() if p.vid is not None]
    return ports[0] if len(ports) == 1 else None


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _integer(value):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _json_safe(value):
    """Reject NaN/Infinity anywhere in a packet before it can reach SSE."""
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_safe(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_safe(item)
                   for key, item in value.items())
    return False


def _valid_raw_code(value):
    code = _integer(value)
    return code if code is not None and 0 <= code <= 0xFFFF else None


def _celsius_from_raw(raw):
    signed = raw - 0x10000 if raw & 0x8000 else raw
    return signed * 0.0078125


def _validate_measurement(vitals, value_key, status_key, low, high,
                          sensor, sensors, optical=False):
    status = vitals.get(status_key)
    value = vitals.get(value_key)
    if not isinstance(status, str) or status not in SENSOR_STATUSES:
        return False
    if value is not None:
        numeric = _number(value)
        if numeric is None or not low <= numeric <= high:
            return False
    if status == 'valid':
        if sensors.get(sensor) is not True or value is None:
            return False
        if optical and vitals.get('finger_on') is not True:
            return False
        return True
    return value is None


def _validate_temperature(vitals, sensors):
    """Validate the actual TMP117 reading and the clinical wrist contact."""
    sensor_status = vitals.get('tmp117_sensor_temperature_status')
    sensor_value_raw = vitals.get('tmp117_sensor_temperature_c')
    sensor_raw_raw = vitals.get('tmp117_sensor_temperature_raw')
    sensor_timestamp_raw = vitals.get('tmp117_sensor_temperature_timestamp_ms')
    if (not isinstance(sensor_status, str)
            or sensor_status not in ACTUAL_SENSOR_STATUSES):
        return False
    sensor_value = _number(sensor_value_raw)
    sensor_raw = _valid_raw_code(sensor_raw_raw)
    sensor_timestamp = _integer(sensor_timestamp_raw)
    if sensor_status == 'valid':
        if (sensors.get('tmp117') is not True or sensor_value is None
                or sensor_raw is None or sensor_raw in (0x0000, 0xFFFF)
                or sensor_timestamp is None or sensor_timestamp < 0
                or not -55 <= sensor_value <= 150):
            return False
        if abs(_celsius_from_raw(sensor_raw) - sensor_value) > 0.02:
            return False
    else:
        # Non-valid means unavailable: no partial or stale evidence may leak out.
        if (sensor_value_raw is not None or sensor_raw_raw is not None
                or sensor_timestamp_raw is not None):
            return False
        if sensors.get('tmp117') is not True and sensor_status != 'not_available':
            return False

    contact_status = vitals.get('wrist_contact_status')
    if (not isinstance(contact_status, str)
            or contact_status not in ('verified', 'unverified')):
        return False
    wrist_status = vitals.get('wrist_skin_temperature_status')
    wrist_value_raw = vitals.get('wrist_skin_temperature_c')
    wrist_raw_raw = vitals.get('wrist_skin_temperature_raw')
    wrist_timestamp_raw = vitals.get('wrist_skin_temperature_timestamp_ms')
    if not isinstance(wrist_status, str) or wrist_status not in SENSOR_STATUSES:
        return False
    wrist_value = _number(wrist_value_raw)
    wrist_raw = _valid_raw_code(wrist_raw_raw)
    wrist_timestamp = _integer(wrist_timestamp_raw)

    if contact_status == 'unverified':
        if (wrist_status != 'unverified' or wrist_value_raw is not None
                or wrist_raw_raw is not None or wrist_timestamp_raw is not None):
            return False
        return True

    if wrist_status == 'unverified':
        return False
    if wrist_value_raw is not None and wrist_value is None:
        return False
    if wrist_raw_raw is not None and wrist_raw is None:
        return False
    if wrist_status == 'valid':
        if (sensors.get('tmp117') is not True or wrist_value is None
                or wrist_raw is None or wrist_raw in (0x0000, 0xFFFF)
                or wrist_timestamp is None or wrist_timestamp < 0
                or not -10 <= wrist_value <= 60):
            return False
        if abs(_celsius_from_raw(wrist_raw) - wrist_value) > 0.02:
            return False
        if (sensor_status != 'valid' or sensor_raw != wrist_raw
                or sensor_timestamp != wrist_timestamp
                or sensor_value is None
                or not math.isclose(sensor_value, wrist_value,
                                    rel_tol=0.0, abs_tol=0.02)):
            return False
    else:
        if (wrist_value_raw is not None or wrist_raw_raw is not None
                or wrist_timestamp_raw is not None):
            return False
    return True


def _validate_fever(vitals):
    fever = vitals.get('fever_screening')
    if fever is None:
        return True
    if not isinstance(fever, dict):
        return False
    if fever.get('status') != 'not_available':
        return False
    screening_supported = fever.get('screening_supported')
    if screening_supported is not None and screening_supported is not False:
        return False
    if fever.get('message') != FEVER_MESSAGE:
        return False
    if fever.get('rule') is not None:
        return False
    input_data = fever.get('input')
    if input_data is None:
        return True
    if not isinstance(input_data, dict):
        return False
    if input_data.get('measurement') not in (None, 'wrist_skin_temperature'):
        return False
    unit = input_data.get('unit')
    if unit is not None and unit != 'C':
        return False

    wrist_status = vitals.get('wrist_skin_temperature_status')
    if not isinstance(wrist_status, str) or wrist_status not in SENSOR_STATUSES:
        return False
    quality = input_data.get('quality')
    if not isinstance(quality, str) or quality not in SENSOR_STATUSES:
        return False
    if quality != wrist_status:
        return False

    measured = input_data.get('measured')
    if not isinstance(measured, bool):
        return False
    value_raw = input_data.get('value_c')
    value = _number(value_raw)
    if value_raw is not None and value is None:
        return False
    timestamp_raw = input_data.get('timestamp_ms')
    timestamp = _integer(timestamp_raw)
    if timestamp_raw is not None and (timestamp is None or timestamp < 0):
        return False
    raw_raw = input_data.get('raw_register')
    raw = _valid_raw_code(raw_raw)
    if raw_raw is not None and raw is None:
        return False

    wrist_value = _number(vitals.get('wrist_skin_temperature_c'))
    wrist_raw = _valid_raw_code(vitals.get('wrist_skin_temperature_raw'))
    wrist_timestamp = _integer(vitals.get('wrist_skin_temperature_timestamp_ms'))
    if measured:
        if (quality != 'valid' or wrist_status != 'valid'
                or vitals.get('wrist_contact_status') != 'verified'
                or value is None or wrist_value is None):
            return False
        if not math.isclose(value, wrist_value, rel_tol=0.0, abs_tol=1e-6):
            return False
        if (timestamp is None or wrist_timestamp is None
                or timestamp != wrist_timestamp):
            return False
        if (raw is None or wrist_raw is None or raw != wrist_raw
                or raw in (0x0000, 0xFFFF)):
            return False
        if abs(_celsius_from_raw(raw) - value) > 0.02:
            return False
    else:
        # An unmeasured input must not carry a value, timestamp or raw evidence,
        # nor claim a valid wrist observation that it did not use.
        if (value_raw is not None or timestamp_raw is not None
                or raw_raw is not None or wrist_status == 'valid'):
            return False
    return True


def _validate_imu(vitals):
    acceleration = vitals.get('acceleration')
    gyroscope = vitals.get('gyroscope')
    for obj, fields, low, high in (
            (acceleration, ('x_g', 'y_g', 'z_g', 'magnitude_g'), -30, 30),
            (gyroscope, ('x_dps', 'y_dps', 'z_dps', 'magnitude_dps'), -4000, 4000)):
        if obj is None:
            continue
        if not isinstance(obj, dict):
            return False
        for field in fields:
            if field not in obj:
                return False
            value = obj[field]
            if value is None:
                continue
            numeric = _number(value)
            if numeric is None or not low <= numeric <= high:
                return False
    raw = vitals.get('imu_raw')
    if raw is not None:
        if not isinstance(raw, dict):
            return False
        for field in ('accel_counts', 'gyro_counts'):
            counts = raw.get(field)
            if counts is None:
                continue
            if not isinstance(counts, list) or len(counts) != 3:
                return False
            if any(_integer(value) is None or not -32768 <= value <= 32767
                   for value in counts):
                return False
    return True


def _validate_packet(packet):
    if not isinstance(packet, dict) or not _json_safe(packet):
        return False
    device_id = packet.get('device_id')
    if not isinstance(device_id, str) or not device_id or len(device_id) > 128:
        return False
    if packet.get('schema_version') != 2:
        return False
    uptime = _number(packet.get('uptime_s'))
    if uptime is None or uptime < 0:
        return False
    for key in ('vitals', 'sensors', 'alerts'):
        if not isinstance(packet.get(key), dict):
            return False
    vitals, sensors, alerts = packet['vitals'], packet['sensors'], packet['alerts']
    for key in ('sos', 'fall'):
        if not isinstance(alerts.get(key), bool):
            return False
    for key in INSTALLED_SENSORS:
        if not isinstance(sensors.get(key), bool):
            return False
    for key in ('oled', 'sht40', 'mlx'):
        if key in sensors and not isinstance(sensors[key], bool):
            return False
    if sensors.get('sht40') is True or sensors.get('mlx') is True:
        return False
    active = _integer(sensors.get('active'))
    active_max = _integer(sensors.get('active_max'))
    installed_count = sum(sensors[key] is True for key in INSTALLED_SENSORS)
    if active_max != 3 or active != installed_count:
        return False
    if not isinstance(vitals.get('finger_on'), bool):
        return False

    if not _validate_measurement(vitals, 'heart_rate', 'heart_rate_status',
                                 20, 250, 'max', sensors, optical=True):
        return False
    if not _validate_measurement(vitals, 'spo2', 'spo2_status',
                                 0.1, 100, 'max', sensors, optical=True):
        return False
    if not _validate_measurement(vitals, 'motion_g', 'motion_status',
                                 0, 20, 'mpu', sensors):
        return False
    if not _validate_temperature(vitals, sensors):
        return False

    if vitals.get('estimated_core_temperature_c') is not None:
        return False
    if vitals.get('estimated_core_temperature_status') != CORE_STATUS:
        return False
    # SHT40/MLX90614 are not installed. Null legacy aliases are tolerated for
    # older producers, but a non-null legacy reading is contradictory and must
    # not enter the record or the dashboard.
    for legacy in ('tmp117_temp_c', 'temp_core', 'temp_skin', 'temp_object', 'temp_amb',
                   'sht40_temp_c', 'sht40_humidity_pct'):
        if vitals.get(legacy) is not None:
            return False
    if not _validate_fever(vitals):
        return False
    if not _validate_imu(vitals):
        return False

    for field, (low, high) in VITAL_NUMERIC_FIELDS.items():
        if field not in vitals or vitals[field] is None:
            continue
        value = _number(vitals[field])
        if value is None or not low <= value <= high:
            return False
    for field in ('heart_rate_timestamp_ms', 'spo2_timestamp_ms',
                  'motion_timestamp_ms'):
        value = vitals.get(field)
        if value is not None and (_integer(value) is None or value < 0):
            return False
    if vitals.get('heart_rate_status') == 'valid':
        value = vitals.get('heart_rate_timestamp_ms')
        if _integer(value) is None or value < 0:
            return False
    if vitals.get('spo2_status') == 'valid':
        value = vitals.get('spo2_timestamp_ms')
        if _integer(value) is None or value < 0:
            return False
    if vitals.get('motion_status') == 'valid':
        value = vitals.get('motion_timestamp_ms')
        if _integer(value) is None or value < 0:
            return False
    for field in ('optical_signal_quality', 'activity_state', 'orientation',
                  'status_summary', 'firmware_version', 'risk'):
        if field in packet and not isinstance(packet[field], str):
            return False
        if field in vitals and not isinstance(vitals[field], str):
            return False
    if 'steps' in vitals and vitals['steps'] is not None:
        if _integer(vitals['steps']) is None:
            return False
    if 'urgent' in packet and not isinstance(packet['urgent'], bool):
        return False
    if 'board' in packet:
        board = packet['board']
        if not isinstance(board, dict):
            return False
        for key in ('flash_bytes', 'psram_bytes'):
            value = board.get(key)
            if value is not None and (_integer(value) is None or value < 0):
                return False
    return True


def _object_without_duplicates(pairs):
    """Reject duplicate JSON keys instead of silently keeping the last one."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def parse_packet(line):
    text = line.removeprefix('[JSON]').strip()
    if not text.startswith('{'):
        return None
    try:
        packet = json.loads(text, object_pairs_hook=_object_without_duplicates)
    except (ValueError, TypeError):
        return None
    return packet if _validate_packet(packet) else None


def snapshot():
    with state_lock:
        status = hardware_status.copy()
        fresh = (last_packet_time is not None and
                 time.monotonic() - last_packet_time < STALE_SECONDS)
        if not fresh and status['connected']:
            status.update(connected=False,
                          error='Telemetry timed out; waiting for fresh packets.')
        return {
            'status': status,
            'telemetry': (latest_telemetry if fresh and status['connected']
                          else None),
            'comparisons': (latest_comparisons if fresh and status['connected']
                            else {}),
        }


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


def _record_event_if_new(packet):
    for kind in ('sos', 'fall'):
        key = (packet['device_id'], kind)
        active = packet['alerts'].get(kind) is True
        if (active and not last_alerts.get(key) and
                telemetry_store is not None and personal_baseline is not None):
            enrollment = personal_baseline.summary(
                packet['device_id']).get('id')
            with telemetry_store.lock, telemetry_store.db:
                telemetry_store.db.execute(
                    'INSERT INTO events(enrollment_id,device_id,recorded_at,kind,detail) '
                    'VALUES(?,?,?,?,?)',
                    (enrollment, packet['device_id'], time.time(), kind,
                     'SOS button activated.' if kind == 'sos'
                     else 'Device reported a possible fall.'))
        last_alerts[key] = active


def _accept_packet(packet):
    global latest_telemetry, last_packet_time, latest_comparisons
    packet['_received_at'] = time.time()
    with state_lock:
        latest_telemetry = packet
        last_packet_time = time.monotonic()
        hardware_status['packets_received'] += 1
        hardware_status.update(connected=True, error=None,
                               device_id=packet['device_id'])
    if telemetry_store is not None:
        try:
            telemetry_store.record(packet)
            if personal_baseline is not None:
                latest_comparisons = personal_baseline.compare(packet)
                _record_event_if_new(packet)
            with state_lock:
                hardware_status.pop('storage_error', None)
        except sqlite3.Error as exc:
            with state_lock:
                hardware_status['storage_error'] = str(exc)
    broadcast()


def serial_reader_thread(port=None):
    if serial is None:
        set_disconnected('pyserial is missing. Install with: pip install pyserial')
        return
    while True:
        target = port or find_serial_port()
        with state_lock:
            hardware_status['port'] = target
        if target is None:
            set_disconnected(
                'Connect one USB serial device or select it with --serial-port.')
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
            print(f'[SERIAL] Opened {target}; waiting for JSON packets.',
                  flush=True)
            buffer = bytearray()
            while True:
                buffer.extend(ser.read(ser.in_waiting or 1))
                if len(buffer) > 65536:
                    buffer.clear()
                while b'\n' in buffer:
                    line, _, remaining = buffer.partition(b'\n')
                    buffer = bytearray(remaining)
                    text = line.decode('utf-8', errors='replace').strip()
                    if duplicate_suppressor.duplicate(text):
                        with state_lock:
                            hardware_status['duplicates_skipped'] += 1
                        continue
                    packet = parse_packet(text)
                    if packet is None:
                        if '{"' in text:
                            with state_lock:
                                hardware_status['invalid_packets'] += 1
                        continue
                    _accept_packet(packet)
                with state_lock:
                    connected = hardware_status['connected']
                if (connected and last_packet_time is not None and
                        time.monotonic() - last_packet_time >= STALE_SECONDS):
                    set_disconnected(
                        'Telemetry timed out; waiting for fresh packets.')
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
            device = parse_qs(url.query).get(
                'device_id', [hardware_status.get('device_id')])[0]
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
            body = json.dumps(
                {'hardware': state['status'], 'latest': state['telemetry']},
                allow_nan=False).encode()
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
                    self.wfile.write(
                        ('data: ' + json.dumps(payload, allow_nan=False) + '\n\n').encode())
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
        elif url.path in (
                '/', '/index.html', '/dashboard.html', '/wiring-guide.html',
                '/assets/dashboard.css', '/assets/dashboard.js',
                '/assets/dashboard_core.js',
                '/assets/fonts/fira-sans-regular.ttf',
                '/assets/fonts/fira-sans-medium.ttf',
                '/assets/fonts/fira-sans-semibold.ttf'):
            super().do_GET()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != '/api/baseline' or personal_baseline is None:
            return self.send_json({'error': 'Endpoint unavailable.'}, 404)
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            return self.send_json(
                {'error': 'Use the local dashboard to update collection.'}, 403)
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
    parser.add_argument('port', nargs='?', type=int, default=8080,
                        help='HTTP port (default: 8080)')
    parser.add_argument('--serial-port',
                        help='Explicit serial port, for example /dev/ttyACM0 or COM6')
    parser.add_argument(
        '--database',
        default=str(Path(__file__).resolve().parent / 'data' / 'telemetry.sqlite3'))
    args = parser.parse_args()
    telemetry_store = TelemetryStore(args.database)
    personal_baseline = PersonalBaseline(telemetry_store)
    handler = partial(TelemetryRequestHandler,
                      directory=str(Path(__file__).resolve().parent))
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler)
    threading.Thread(target=serial_reader_thread,
                     args=(args.serial_port,), daemon=True).start()
    print(f'Dashboard: http://localhost:{args.port}/index.html', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
