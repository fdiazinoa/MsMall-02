"""Windows SQL downloader: standard library only, no persistent cloud ZIPs."""
import argparse
import base64
import ctypes
import getpass
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone
from urllib import request, parse, error
from uuid import UUID
import zipfile
import zlib

SD = timezone(timedelta(hours=-4))
TIMEOUT = 2700
MAX_ZIP = 5_000_000_000


class ClientError(Exception):
    pass


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ClientError('El servidor redirigió la solicitud. Revisa las URL configuradas.')


OPENER = request.build_opener(NoRedirect())


def atomic_write(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('wb') as target:
        target.write(data)
        target.flush()
        os.fsync(target.fileno())
    os.replace(temporary, path)


def dpapi(data, decrypt=False):
    if sys.platform != 'win32':
        raise ClientError('El inicio de sesión protegido requiere Windows.')
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ClientError('No se pudo acceder a la sesión protegida de este usuario Windows.')
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


def load_config(path):
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    config['mall_id'] = str(UUID(config['mall_id']))
    for field in ('api_url', 'supabase_url'):
        url = parse.urlsplit(config[field])
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ClientError('La configuración requiere URL HTTPS sin credenciales.')
        config[field] = config[field].rstrip('/')
    return config


def open_http(url, headers, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = request.Request(url, data=body, headers={**headers, 'Content-Type': 'application/json'})
    try:
        return OPENER.open(req, timeout=TIMEOUT)
    except error.HTTPError as exc:
        messages = {401: 'La sesión venció. Ejecuta el instalador con -LoginOnly.',
                    403: 'El usuario no tiene permiso de respaldo para este Mall.',
                    409: 'La base cambió o hay otro respaldo en curso. Reintenta más tarde.',
                    413: 'El respaldo supera el tamaño permitido.',
                    429: 'Descarga bloqueada por cuota o frecuencia. No se generaron cargos.'}
        raise ClientError(messages.get(exc.code, f'El servidor respondió HTTP {exc.code}.')) from None
    except (error.URLError, TimeoutError, OSError):
        raise ClientError('No se pudo completar la conexión. Revisa Internet y reintenta.') from None


def http_json(url, headers, payload=None):
    with open_http(url, headers, payload) as response:
        return json.load(response)


class Client:
    def __init__(self, config_path, destination):
        self.path = Path(config_path).resolve()
        self.config = load_config(self.path)
        self.mall = self.config['mall_id']
        self.root = Path(destination).resolve() / self.mall
        self.root.mkdir(parents=True, exist_ok=True)
        self.session = self.path.with_suffix('.session')
        self.token = None

    def authenticate(self, login=False):
        if login:
            payload = {'email': input('Email de MsMall: ').strip(), 'password': getpass.getpass('Contraseña de MsMall: ')}
            grant = 'password'
        else:
            if not self.session.exists():
                raise ClientError('Primero ejecuta el instalador e inicia sesión.')
            payload = {'refresh_token': dpapi(self.session.read_bytes(), decrypt=True).decode()}
            grant = 'refresh_token'
        session = http_json(self.config['supabase_url'] + '/auth/v1/token?grant_type=' + grant,
                            {'apikey': self.config['publishable_key']}, payload)
        # Save the rotated refresh token before touching the backup API. Password is never stored.
        atomic_write(self.session, dpapi(session['refresh_token'].encode()))
        self.token = session['access_token']
        caps = self.api('/capabilities')
        if not caps.get('mall') or not caps.get('enabled') or not caps.get('differential'):
            raise ClientError('El usuario o servidor no tiene habilitado el respaldo SQL diferencial.')

    def api(self, suffix):
        return http_json(self.config['api_url'] + '/export/import-backup/database' + suffix,
                         {'Authorization': 'Bearer ' + self.token, 'X-Mall-Id': self.mall})

    def manifest(self, path, mode=None, base_id=None):
        with zipfile.ZipFile(path) as archive:
            if archive.getinfo('manifest.json').file_size > 1_000_000:
                raise ClientError('Manifiesto demasiado grande.')
            manifest = json.loads(archive.read('manifest.json'))
            if (manifest.get('format') != 'msmall-postgres-differential-v1'
                    or manifest.get('mall_id') != self.mall
                    or manifest.get('mode') not in ('base', 'differential')
                    or (mode and manifest.get('mode') != mode)
                    or (base_id and manifest.get('base_id') != base_id)):
                raise ClientError('El ZIP no corresponde al Mall o a la base esperada.')
            UUID(manifest['base_id'])
            UUID(manifest['export_id'])
            required = {'data.sql', 'manifest.json'} | ({'schema.sql'} if manifest['mode'] == 'base' else set())
            if not required <= set(archive.namelist()):
                raise ClientError('El respaldo está incompleto.')
            if archive.testzip() is not None:
                raise ClientError('El ZIP no pasó la validación de integridad.')
            return manifest

    def find_base(self, base_id):
        # Never produce a differential unless the matching complete is present and intact locally.
        if not base_id:
            return None
        for path in self.root.glob('base_*.zip'):
            try:
                manifest = self.manifest(path, 'base', base_id)
                return path, manifest
            except (ClientError, ValueError, KeyError, zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError, zlib.error):
                continue
        return None

    def download(self, mode, day, base_id=None):
        query = {'mode': mode}
        if base_id:
            query['base_id'] = base_id
        temporary = self.root / 'descarga.zip.part'
        url = self.config['api_url'] + '/export/import-backup/database/mall?' + parse.urlencode(query)
        try:
            with open_http(url, {'Authorization': 'Bearer ' + self.token, 'X-Mall-Id': self.mall}, {}) as response:
                expected = response.headers.get('Content-Length')
                total = 0
                with temporary.open('wb') as target:
                    while block := response.read(1024 * 1024):
                        total += len(block)
                        if total > MAX_ZIP:
                            raise ClientError('El ZIP supera los 5 GB permitidos.')
                        target.write(block)
                    target.flush()
                    os.fsync(target.fileno())
                if expected is not None and total != int(expected):
                    raise ClientError('La descarga quedó incompleta.')
            manifest = self.manifest(temporary, mode, base_id)
            # Unique export ID preserves existing valid fulls even across same-day retries.
            target = self.root / f'{mode}_{day}_{manifest["export_id"]}.zip'
            os.replace(temporary, target)
            with target.open('rb') as source:
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
            atomic_write(target.with_suffix('.sha256'), (digest + '  ' + target.name + '\n').encode())
            print(f'Guardado y validado: {target}')
            return target, manifest
        finally:
            temporary.unlink(missing_ok=True)

    def run(self):
        # OS lock prevents two processes racing on refresh rotation or the partial ZIP.
        import msvcrt
        lock = (self.root / '.run.lock').open('a+b')
        try:
            lock.seek(0)
            if lock.read(1) == b'':
                lock.write(b'0')
                lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise ClientError('Ya hay una descarga en curso para este Mall.') from None
            self.authenticate()
            self.run_backups(datetime.now(SD).date().isoformat())
        finally:
            lock.close()

    def run_backups(self, day):
        baseline = self.api('/baseline').get('baseline')
        base = self.find_base(str(baseline['id']) if baseline else None)
        base_day = datetime.fromisoformat(base[1]['generated_at'].replace('Z', '+00:00')).astimezone(SD).date().isoformat() if base else None
        if not base or base_day[:7] != day[:7]:
            self.download('base', day)
            return
        # A full generated today already covers today's scheduled run.
        if base_day == day:
            print('El completo de hoy ya está guardado. No se consume tráfico adicional.')
            return
        for path in self.root.glob(f'differential_{day}_*.zip'):
            try:
                self.manifest(path, 'differential', base[1]['base_id'])
                print('El diferencial de hoy ya está guardado. No se consume tráfico adicional.')
                return
            except (ClientError, ValueError, KeyError, zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError, zlib.error):
                continue
        self.download('differential', day, base[1]['base_id'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('config.json'))
    parser.add_argument('--destination', required=True)
    parser.add_argument('--login', action='store_true')
    args = parser.parse_args()
    try:
        client = Client(args.config, args.destination)
        if args.login:
            client.authenticate(login=True)
            print('Sesión guardada y permisos validados para este usuario Windows.')
        else:
            client.run()
        return 0
    except Exception as exc:
        # No remote response, URL, credential or Python traceback in scheduler logs.
        message = str(exc) if isinstance(exc, ClientError) else 'No se completó el respaldo. Revisa configuración, sesión, disco y conexión.'
        print(message, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
