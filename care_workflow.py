"""Persistent local incidents and enrollment-scoped review notes."""
import time
import uuid


def _text(value, label, limit, required=True):
    if not isinstance(value, str) or len(value.strip()) > limit or (required and not value.strip()):
        raise ValueError(f'{label} must contain {1 if required else 0}–{limit} characters.')
    return value.strip()


class CareWorkflow:
    def __init__(self, store):
        self.store = store
        self.active_signals = {}
        with store.lock, store.db:
            store.db.executescript('''
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY, device_id TEXT NOT NULL, enrollment_id TEXT,
                    kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
                    created_at REAL NOT NULL, acknowledged_at REAL, resolved_at REAL,
                    acknowledged_by TEXT, resolved_by TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS unresolved_incident
                    ON incidents(device_id, kind) WHERE status != 'resolved';
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY, device_id TEXT NOT NULL, enrollment_id TEXT NOT NULL,
                    recorded_at REAL NOT NULL, author TEXT NOT NULL,
                    decision TEXT NOT NULL, note TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS reviews_enrollment ON reviews(enrollment_id, recorded_at);
            ''')

    def observe(self, packet):
        device = packet['device_id']
        with self.store.lock, self.store.db:
            enrollment = self.store.db.execute(
                'SELECT id FROM enrollments WHERE device_id=? AND active=1', (device,)).fetchone()
            for kind in ('sos', 'fall'):
                active = packet['alerts'][kind]
                key = (device, kind)
                if active and not self.active_signals.get(key):
                    self.store.db.execute('''INSERT OR IGNORE INTO incidents
                        (id,device_id,enrollment_id,kind,created_at) VALUES(?,?,?,?,?)''',
                        (uuid.uuid4().hex, device, enrollment['id'] if enrollment else None,
                         kind, time.time()))
                self.active_signals[key] = active

    def summary(self, device):
        with self.store.lock:
            incidents = self.store.db.execute('''SELECT * FROM incidents WHERE device_id=?
                ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'acknowledged' THEN 1 ELSE 2 END,
                created_at DESC LIMIT 50''', (device,)).fetchall()
            review = self.store.db.execute('''SELECT r.* FROM reviews r JOIN enrollments e
                ON r.enrollment_id=e.id WHERE e.device_id=? AND e.active=1
                ORDER BY r.recorded_at DESC LIMIT 1''', (device,)).fetchone()
        return dict(incidents=[dict(row) for row in incidents],
                    review=dict(review) if review else None)

    def update_incident(self, device, identity, action, author):
        author = _text(author, 'Reviewer name or alias', 80)
        if action not in ('acknowledge', 'resolve'):
            raise ValueError('Choose acknowledge or resolve.')
        with self.store.lock, self.store.db:
            incident = self.store.db.execute(
                'SELECT * FROM incidents WHERE device_id=? AND id=?', (device, identity)).fetchone()
            if not incident:
                raise ValueError('Incident not found for this device.')
            if action == 'acknowledge' and incident['status'] == 'open':
                self.store.db.execute('''UPDATE incidents SET status='acknowledged',
                    acknowledged_at=?,acknowledged_by=? WHERE id=?''',
                    (time.time(), author, identity))
            elif action == 'resolve' and incident['status'] == 'acknowledged':
                self.store.db.execute('''UPDATE incidents SET status='resolved',
                    resolved_at=?,resolved_by=? WHERE id=?''', (time.time(), author, identity))
            elif not (action == 'resolve' and incident['status'] == 'resolved'):
                if not (action == 'acknowledge' and incident['status'] == 'acknowledged'):
                    raise ValueError('Acknowledge the incident before resolving it.')
        return self.summary(device)

    def add_review(self, device, enrollment_id, author, decision, note):
        author = _text(author, 'Reviewer name or alias', 80)
        note = _text(note, 'Review note', 2000, required=False)
        if decision not in ('reviewed', 'follow_up', 'contact'):
            raise ValueError('Choose a review outcome.')
        with self.store.lock, self.store.db:
            enrollment = self.store.db.execute('''SELECT id FROM enrollments
                WHERE device_id=? AND id=? AND active=1''', (device, enrollment_id)).fetchone()
            if not enrollment:
                raise ValueError('This enrollment ended or changed. Refresh the patient before saving.')
            now = time.time()
            self.store.db.execute('INSERT INTO reviews VALUES(?,?,?,?,?,?,?)',
                (uuid.uuid4().hex, device, enrollment_id, now, author, decision, note))
            detail = {'reviewed': 'Reviewed', 'follow_up': 'Follow-up visit recommended',
                      'contact': 'Contact patient for assessment'}[decision]
            detail += f' · {author}' + (f' · {note}' if note else '')
            self.store.db.execute('''INSERT INTO events
                (enrollment_id,device_id,recorded_at,kind,detail) VALUES(?,?,?,?,?)''',
                (enrollment_id, device, now, 'review', detail))
        return self.summary(device)
