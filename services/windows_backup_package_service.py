"""Download-only Windows client package. Contains a public key, never a session."""
import base64
import io
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID
import zipfile

from pydantic import BaseModel, Field


class WindowsBackupPackageRequest(BaseModel):
    publishable_key: str = Field(min_length=15, max_length=2048)


def build_windows_package(mall, supabase_url, publishable_key):
    mall = str(UUID(str(mall)))
    url = urlsplit(supabase_url or '')
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
        raise ValueError('Supabase URL no válida.')
    # Legacy anon JWTs and modern publishable keys are public configuration.
    # Reject any accidental secret/service-role key instead of shipping it to a PC.
    public = publishable_key.startswith('sb_publishable_')
    if not public:
        try:
            parts = publishable_key.split('.')
            claims = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4))) if len(parts) == 3 else {}
            public = claims.get('role') == 'anon'
        except (ValueError, IndexError, UnicodeError):
            public = False
    if not public:
        raise ValueError('Se requiere la clave pública de la plataforma, nunca una clave secreta.')
    output = io.BytesIO()
    root = Path(__file__).resolve().parents[1] / 'scripts' / 'windows-sql-backup'
    config = {'mall_id': mall, 'supabase_url': supabase_url.rstrip('/'),
              'publishable_key': publishable_key,
              'api_url': 'https://msmall-02-production.up.railway.app/api/v1'}
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in ('backup_client.py', 'Instalar.ps1', 'LEEME.txt'):
            archive.write(root / name, name)
        archive.writestr('config.json', json.dumps(config, indent=2))
    return output.getvalue()
