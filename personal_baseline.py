"""An explicit seven-day, per-wearer statistical reference (not a diagnostic model)."""
import json
import statistics
import time
import uuid
from telemetry_store import METRICS, measurements

DAY = 86400
REQUIRED_DAYS = 7
MIN_MINUTES_PER_DAY = 30
# Engineering noise floors, not clinical decision thresholds.
NOISE_FLOORS = {'heart_rate': 5.0, 'spo2': 2.0, 'temp_object': 0.3, 'motion_g': 0.1}


class PersonalBaseline:
    def __init__(self, store):
        self.store = store
        self.cache = {}
        self.runs = {}
        with store.lock, store.db:
            store.db.executescript('''
                CREATE TABLE IF NOT EXISTS enrollments (
                    id TEXT PRIMARY KEY, device_id TEXT NOT NULL,
                    person TEXT NOT NULL, started_at REAL NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1, models TEXT NOT NULL DEFAULT '{}'
                );
                CREATE UNIQUE INDEX IF NOT EXISTS active_enrollment
                    ON enrollments(device_id) WHERE active = 1;
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, enrollment_id TEXT,
                    device_id TEXT NOT NULL, recorded_at REAL NOT NULL,
                    kind TEXT NOT NULL, metric TEXT, value REAL,
                    detail TEXT NOT NULL
                );
            ''')

    def start(self, device_id, person, now=None):
        person = str(person).strip()
        if not person or len(person) > 80:
            raise ValueError('Enter a name or alias, up to 80 characters.')
        if not device_id or len(device_id) > 128:
            raise ValueError('Connect a device before starting a baseline.')
        now = time.time() if now is None else now
        with self.store.lock, self.store.db:
            if self.store.db.execute('SELECT 1 FROM enrollments WHERE device_id=? AND active=1',(device_id,)).fetchone():
                raise ValueError('This device already has an active baseline. End it before changing wearer.')
            identity = uuid.uuid4().hex
            self.store.db.execute('INSERT INTO enrollments(id,device_id,person,started_at) VALUES(?,?,?,?)',
                                  (identity,device_id,person,now))
            self.store.db.execute('INSERT INTO events(enrollment_id,device_id,recorded_at,kind,detail) VALUES(?,?,?,?,?)',
                                  (identity,device_id,now,'collection','Personal baseline collection started.'))
        self.cache.pop(device_id,None)
        return self.summary(device_id,now=now,force=True)

    def end(self, device_id):
        with self.store.lock, self.store.db:
            self.store.db.execute('UPDATE enrollments SET active=0 WHERE device_id=? AND active=1',(device_id,))
        self.cache.pop(device_id,None)
        self.runs = {key:value for key,value in self.runs.items() if key[0]!=device_id}

    def summary(self, device_id, now=None, force=False):
        now = time.time() if now is None else now
        cached = self.cache.get(device_id)
        if not force and cached and 0 <= now-cached[0] < 30:
            return cached[1]
        with self.store.lock, self.store.db:
            row=self.store.db.execute('SELECT * FROM enrollments WHERE device_id=? AND active=1',(device_id,)).fetchone()
            if not row:
                return dict(status='not_started',person=None,metrics={},days=[],required_days=REQUIRED_DAYS,
                            min_minutes_per_day=MIN_MINUTES_PER_DAY,ready_metrics=0)
            models=json.loads(row['models'])
            started=row['started_at']
            # Minute means reduce the influence of high-rate bursts. Each metric has its own coverage.
            minutes=self.store.db.execute('''SELECT CAST((recorded_at-?)/60 AS INTEGER) AS minute,
                AVG(heart_rate) AS heart_rate, AVG(spo2) AS spo2,
                AVG(temp_object) AS temp_object, AVG(motion_g) AS motion_g
                FROM observations WHERE device_id=? AND recorded_at>=? AND recorded_at<=?
                GROUP BY minute ORDER BY minute''',(started,device_id,started,now)).fetchall()
            current_day=max(0,int((now-started)//DAY))
            days=[dict(day=i+1,recorded_minutes=0,qualified_metrics=0) for i in range(max(0,current_day-6),max(7,current_day+1))]
            days_by_index={d['day']-1:d for d in days}
            metric_results={}
            changed=False
            for key in METRICS:
                counts={}
                values=[]
                first_minute=None
                for item in minutes:
                    if item[key] is None: continue
                    day=int(item['minute']//1440)
                    counts[day]=counts.get(day,0)+1
                    values.append(item[key])
                    if first_minute is None: first_minute=item['minute']
                qualified=sum(count>=MIN_MINUTES_PER_DAY for count in counts.values())
                elapsed=first_minute is not None and now-(started+first_minute*60)>=REQUIRED_DAYS*DAY
                if key not in models and qualified>=REQUIRED_DAYS and elapsed:
                    center=statistics.median(values)
                    mad=statistics.median(abs(v-center) for v in values)
                    width=max(3*1.4826*mad,NOISE_FLOORS[key])
                    models[key]=dict(center=center,low=center-width,high=center+width,
                        mad=mad,trained_at=now,minutes=len(values),qualified_days=qualified,
                        method='median ± max(3 × 1.4826 × MAD, engineering noise floor)')
                    if key=='spo2':
                        models[key]['low']=max(0,models[key]['low'])
                        models[key]['high']=min(100,models[key]['high'])
                    if key=='motion_g': models[key]['low']=max(0,models[key]['low'])
                    changed=True
                for day,count in counts.items():
                    if day in days_by_index:
                        days_by_index[day]['recorded_minutes']=max(days_by_index[day]['recorded_minutes'],count)
                        if count>=MIN_MINUTES_PER_DAY: days_by_index[day]['qualified_metrics']+=1
                metric_results[key]=dict(status='ready' if key in models else 'collecting' if values else 'waiting',
                    valid_minutes=len(values),qualified_days=min(qualified,REQUIRED_DAYS),
                    today_minutes=counts.get(current_day,0),model=models.get(key))
            if changed:
                self.store.db.execute('UPDATE enrollments SET models=? WHERE id=?',(json.dumps(models),row['id']))
            ready=len(models)
            result=dict(id=row['id'],person=row['person'],device_id=device_id,started_at=started,
                status='ready' if ready==len(METRICS) else 'partial' if ready else 'collecting',
                elapsed_days=(now-started)/DAY,ready_metrics=ready,metrics=metric_results,days=days,
                required_days=REQUIRED_DAYS,min_minutes_per_day=MIN_MINUTES_PER_DAY)
            self.cache[device_id]=(now,result)
            return result

    def compare(self, packet, now=None):
        now=time.time() if now is None else now
        summary=self.summary(packet['device_id'],now)
        values=measurements(packet)
        comparisons={}
        for key,value in values.items():
            model=summary.get('metrics',{}).get(key,{}).get('model')
            state='unavailable' if value is None else 'collecting' if not model else 'outside' if value<model['low'] or value>model['high'] else 'within'
            comparisons[key]=dict(state=state,value=value,model=model)
            runkey=(packet['device_id'],key)
            prior=self.runs.get(runkey,dict(count=0,last_seen=0,last_event=0))
            consecutive=state=='outside' and now-prior['last_seen']<=5
            count=prior['count']+1 if consecutive else 1 if state=='outside' else 0
            last_event=prior['last_event']
            if count>=3 and now-last_event>=300:
                detail=f"{METRICS[key]['label']} stayed outside this person's recorded reference for three readings."
                with self.store.lock,self.store.db:
                    self.store.db.execute('INSERT INTO events(enrollment_id,device_id,recorded_at,kind,metric,value,detail) VALUES(?,?,?,?,?,?,?)',
                        (summary['id'],packet['device_id'],now,'deviation',key,value,detail))
                last_event=now
            self.runs[runkey]=dict(count=count,last_seen=now,last_event=last_event)
        return comparisons

    def events(self,device_id):
        with self.store.lock:
            rows=self.store.db.execute('SELECT * FROM events WHERE device_id=? ORDER BY recorded_at DESC LIMIT 30',(device_id,)).fetchall()
        return [dict(row) for row in rows]
