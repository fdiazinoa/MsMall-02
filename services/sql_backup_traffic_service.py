"""Free shared weekly SQL traffic budget; every outbound file requires a lease."""
import os
import threading
from datetime import datetime, timezone
from uuid import uuid4

import psycopg

from services.import_backup_quota_service import BackupQuotaError


def enabled():
    return os.getenv('ENABLE_SQL_BACKUP_WEEKLY_QUOTA', '').lower() in {'true','1','yes'}


class TrafficQuotaError(BackupQuotaError):
    def __init__(self, reason):
        super().__init__(reason)
        if reason == 'weekly_bytes':
            self.args = ('No hay cuota gratuita semanal suficiente para este respaldo SQL. La operación está bloqueada; espera al reinicio semanal o elige un respaldo menor. No se generarán cargos adicionales.',)
        elif reason == 'weekly_reset':
            self.args = ('La semana de cuota cambió. Vuelve a solicitar el respaldo con la cuota de la nueva semana.',)
        elif reason == 'disabled':
            self.args = ('El plan gratuito de backups SQL está desactivado.',)
        elif reason == 'frequency':
            self.args = ('Espera antes de solicitar otra generación manual de backup SQL.',)
        elif reason == 'daily_downloads':
            self.args = ('Se alcanzó el límite diario de generaciones manuales SQL de este Mall. Puedes descargar los archivos automáticos disponibles dentro de la cuota semanal.',)


class SQLBackupTrafficService:
    def __init__(self, mall, actor=None, mode='period', connect=None):
        self.mall, self.actor, self.mode = mall, actor, mode
        self.connect = connect or psycopg.connect

    def call(self, action, **params):
        try:
            with self.connect(os.environ['BACKUP_DATABASE_URL'], connect_timeout=10) as conn:
                result = conn.execute('SELECT msmall_backup.traffic_control(%s,%s,%s,%s,%s,%s,%s)',
                    (action,self.mall,self.actor,params.get('job'),self.mode,params.get('bytes',0),params.get('days',1))).fetchone()[0]
        except (psycopg.Error, KeyError) as exc:
            raise BackupQuotaError('unavailable',20) from exc
        if result.get('configured') and not result.get('allowed'):
            raise TrafficQuotaError(result.get('reason') or 'unavailable')
        return result

    def status(self):
        return self.call('status')

    def reserve(self, days):
        job = str(uuid4())
        result = self.call('reserve',job=job,days=days)
        if not result.get('configured'):
            raise BackupQuotaError('unavailable',20)
        return TrafficLease(self,job,int(result['max_bytes']),result['quota']['resets_at'])


class TrafficLease:
    def __init__(self, service, job, max_bytes, reset):
        self.service,self.request_id,self.max_bytes=service,job,max_bytes
        self.reset=datetime.fromisoformat(reset.replace('Z','+00:00'))
        self.produced_bytes=0
        self.prepared=False
        self.closed=False
        self.stop=threading.Event()
        self.lost=threading.Event()
        self.thread=threading.Thread(target=self._heartbeat,daemon=True)

    def start(self):
        self.thread.start()

    def _heartbeat(self):
        while not self.stop.wait(20):
            try:
                self.service.call('renew',job=self.request_id)
            except BackupQuotaError:
                self.lost.set()
                return

    def check(self):
        if self.lost.is_set():
            raise BackupQuotaError('lease_expired',20)
        if datetime.now(timezone.utc)>=self.reset:
            raise TrafficQuotaError('weekly_reset')

    def progress(self,size):
        self.produced_bytes=max(self.produced_bytes,size)
        self.check()

    def prepare(self,size):
        self.check()
        charge = size if self.service.mode=='download' else max(self.produced_bytes,size)+size
        self.service.call('prepare',job=self.request_id,bytes=charge)
        self.prepared=True

    def close(self,failed=False):
        if self.closed:
            return
        self.closed=True
        self.stop.set()
        if self.thread.is_alive():
            self.thread.join(timeout=1)
        try:
            # Failures may have transferred data before failing; conservatively charge it.
            charge=self.produced_bytes*(1 if self.service.mode=='download' else 2)
            self.service.call('fail' if failed else 'finish',job=self.request_id,bytes=charge)
        except BackupQuotaError:
            # The reservation remains charged on expiry if the DB could not close it.
            pass
