"""Read-only logical archives. No restore operation is exposed by this service."""
import json
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from services.import_backup_service import BackupSizeExceeded, GeneratedBackup


class DatabaseBackupUnavailable(Exception):
    pass


def connection_error_message(exc):
    # Classify internally; never return PostgreSQL's raw DSN/host/user/password.
    text = str(exc).lower()
    code = getattr(exc, 'sqlstate', None)
    if code == '57014' or 'statement timeout' in text:
        return 'La consulta PostgreSQL excedió el tiempo permitido. Reduce el período del backup SQL y vuelve a intentar.'
    if code in {'28P01', '28000'} or 'password authentication failed' in text or 'tenant or user not found' in text:
        return 'No se pudo autenticar en PostgreSQL. Revisa usuario y contraseña de BACKUP_DATABASE_URL en Railway.'
    if 'ssl' in text or 'certificate' in text:
        return 'No se pudo establecer la conexión TLS con PostgreSQL. Revisa sslmode y la configuración de la conexión.'
    if 'could not translate host name' in text or 'name or service not known' in text:
        return 'No se pudo resolver el servidor PostgreSQL. Revisa el host de BACKUP_DATABASE_URL.'
    if 'network is unreachable' in text or 'timeout' in text or 'timed out' in text or 'connection refused' in text:
        return 'No se pudo conectar con PostgreSQL. Revisa red y puerto; para Railway utiliza el Session pooler de Supabase.'
    return 'La conexión PostgreSQL no está disponible. Revisa BACKUP_DATABASE_URL: usuario, contraseña, puerto y modo Session pooler.'


def configuration():
    return (os.getenv('ENABLE_DATABASE_BACKUPS', '').lower() in {'true', '1', 'yes'}
            and bool(os.getenv('BACKUP_DATABASE_URL'))
            and all(shutil.which(binary) for binary in ('pg_dump', 'pg_dumpall')))


@dataclass
class Table:
    name: str
    columns: list
    parents: list  # (child column, parent table, parent column), public simple FKs


def scope_predicates(tables, mall, start=None, end=None):
    """Positive ownership only: never export an unclassified table unfiltered."""
    from psycopg import sql
    mall = str(UUID(mall))
    predicates = {}
    for name, table in tables.items():
        if name == 'malls' and 'id' in table.columns:
            predicates[name] = sql.SQL('t.id = {}::uuid').format(sql.Literal(mall))
        elif name == 'locales' and 'mall_id' in table.columns:
            predicates[name] = sql.SQL('t.mall_id = {}::uuid').format(sql.Literal(mall))
        elif 'local_id' in table.columns and 'locales' in tables:
            # The parent is authoritative for legacy sales with no mall_id.
            predicate = sql.SQL('EXISTS (SELECT 1 FROM public.locales l WHERE l.id = t.local_id AND l.mall_id = {}::uuid)').format(sql.Literal(mall))
            if 'mall_id' in table.columns:
                predicate += sql.SQL(' AND (t.mall_id IS NULL OR t.mall_id = {}::uuid)').format(sql.Literal(mall))
            predicates[name] = predicate
        elif 'mall_id' in table.columns:
            predicates[name] = sql.SQL('t.mall_id = {}::uuid').format(sql.Literal(mall))
    if start is not None:
        if 'ventas' not in tables or 'fecha' not in tables['ventas'].columns:
            raise DatabaseBackupUnavailable('No se pudo identificar la fecha de ventas para aplicar el período.')
        for name, column in (('ventas', 'fecha'), ('logs_carga', 'fecha_hora')):
            if name in predicates and column in tables[name].columns:
                predicates[name] = sql.SQL('({}) AND t.{} >= {}::date AND t.{} < {}::date').format(
                    predicates[name], sql.Identifier(column), sql.Literal(start), sql.Identifier(column),
                    sql.Literal((date.fromisoformat(end) + timedelta(days=1)).isoformat()))
    # First classify the closure, then compose predicates in dependency order.
    # This includes every scoped parent, not only the first one discovered.
    selected = set(predicates)
    while True:
        added = {name for name, table in tables.items() if name not in selected
                 and any(parent in selected for _, parent, _ in table.parents)}
        if not added:
            break
        selected.update(added)
    roots, predicates = predicates, {}
    for name in table_order(tables, selected):
        parents = [(column, parent, key) for column, parent, key in tables[name].parents if parent in predicates]
        checks, nonnull = [], []
        for column, parent, key in parents:
            checks.append(sql.SQL('(t.{column} IS NULL OR EXISTS (SELECT 1 FROM (SELECT t.{key} FROM public.{parent} t WHERE {predicate}) p WHERE p.{key} = t.{column}))').format(
                column=sql.Identifier(column), key=sql.Identifier(key), parent=sql.Identifier(parent), predicate=predicates[parent]))
            nonnull.append(sql.SQL('t.{} IS NOT NULL').format(sql.Identifier(column)))
        if name in roots:
            predicates[name] = sql.SQL('({})').format(roots[name])
            if checks:
                predicates[name] += sql.SQL(' AND ({})').format(sql.SQL(' AND ').join(checks))
        else:
            predicates[name] = sql.SQL('({}) AND ({})').format(sql.SQL(' AND ').join(checks), sql.SQL(' OR ').join(nonnull))
    return predicates


def table_order(tables, selected):
    result, pending = [], set(selected)
    while pending:
        ready = sorted(name for name in pending if not any(parent in pending and parent != name for _, parent, _ in tables[name].parents))
        if not ready:
            # Explicitly report cycles instead of promising a directly replayable dump.
            raise DatabaseBackupUnavailable('Las dependencias del Mall contienen un ciclo. Se requiere un backup completo por el administrador global.')
        result.extend(ready)
        pending.difference_update(ready)
    return result


class DatabaseBackupService:
    def __init__(self, *, connect=None):
        self._connect = connect

    def _command(self, argv, path, env, check, deadline):
        # Credentials go through libpq's environment, never argv, logs or stderr responses.
        with path.open('wb') as output, tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(argv, env=env, stdout=output, stderr=errors)
            try:
                while process.poll() is None:
                    check()
                    if time.monotonic() >= deadline:
                        raise DatabaseBackupUnavailable('El backup excedió el tiempo permitido. Reduce su alcance o revisa el servidor.')
                    time.sleep(0.1)
                check()
                if process.returncode:
                    raise DatabaseBackupUnavailable('PostgreSQL no pudo generar el backup. Revisa permisos, conectividad y versión de pg_dump en el servidor.')
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()

    def _catalog(self, conn):
        rows = conn.execute("""
            SELECT c.relname AS name,
              array_agg(a.attname ORDER BY a.attnum) AS columns
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid
            WHERE n.nspname = 'public' AND c.relkind IN ('r','p') AND NOT c.relispartition
              AND a.attnum > 0 AND NOT a.attisdropped AND a.attgenerated = ''
            GROUP BY c.oid, c.relname ORDER BY c.relname
        """).fetchall()
        tables = {row['name']: Table(row['name'], row['columns'], []) for row in rows}
        for row in conn.execute("""
            SELECT child.relname AS child, ca.attname AS child_column, parent.relname AS parent, pa.attname AS key
            FROM pg_constraint fk
            JOIN pg_class child ON child.oid = fk.conrelid JOIN pg_namespace cn ON cn.oid = child.relnamespace
            JOIN pg_class parent ON parent.oid = fk.confrelid JOIN pg_namespace pn ON pn.oid = parent.relnamespace
            JOIN pg_attribute ca ON ca.attrelid = child.oid AND ca.attnum = fk.conkey[1]
            JOIN pg_attribute pa ON pa.attrelid = parent.oid AND pa.attnum = fk.confkey[1]
            WHERE fk.contype = 'f' AND cn.nspname = 'public' AND pn.nspname = 'public'
              AND cardinality(fk.conkey) = 1
        """).fetchall():
            if row['child'] in tables:
                tables[row['child']].parents.append((row['child_column'], row['parent'], row['key']))
        return tables

    def generate(self, scope, mall, *, max_bytes, on_progress, check_active, start=None, end=None):
        if scope not in {'mall', 'platform'}:
            raise ValueError('Alcance inválido.')
        mall = str(UUID(mall))
        if (start is None) != (end is None):
            raise ValueError('Indica ambas fechas del backup SQL.')
        if start is not None:
            start, end = date.fromisoformat(start).isoformat(), date.fromisoformat(end).isoformat()
            if end < start or end == '9999-12-31':
                raise ValueError('Período SQL inválido.')
        if not configuration():
            raise DatabaseBackupUnavailable('Los backups SQL no están habilitados en este servidor.')
        import psycopg
        from psycopg import sql
        from psycopg.rows import dict_row
        connect = self._connect or psycopg.connect
        deadline = time.monotonic() + 600
        from psycopg.conninfo import conninfo_to_dict
        params = conninfo_to_dict(os.environ['BACKUP_DATABASE_URL'])
        env = dict(os.environ)
        for key in ('host', 'hostaddr', 'port', 'dbname', 'user', 'password', 'sslmode', 'sslrootcert', 'sslcert', 'sslkey', 'channel_binding'):
            if key in params:
                env['PGDATABASE' if key == 'dbname' else 'PG' + key.upper().replace('_', '')] = params[key]
        env.update({'PGCONNECT_TIMEOUT': '10',
               'PGAPPNAME': 'msmall-logical-backup', 'PGOPTIONS': '-c default_transaction_read_only=on -c statement_timeout=540000'})
        archive = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode='w+b')
        try:
            with tempfile.TemporaryDirectory(prefix='msmall-db-backup-') as directory:
                root = Path(directory)

                def check():
                    check_active()
                    size = sum(path.stat().st_size for path in root.iterdir() if path.is_file())
                    if size > max_bytes:
                        raise BackupSizeExceeded('El backup SQL supera el tamaño o cuota disponible. Revisa los límites globales de backup.')
                    on_progress(size)
                    if time.monotonic() > deadline:
                        raise DatabaseBackupUnavailable('El backup excedió el tiempo permitido.')

                # All data and schema dumps share one read-only repeatable-read snapshot.
                with connect(os.environ['BACKUP_DATABASE_URL'], connect_timeout=10, row_factory=dict_row) as conn:
                    conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                    conn.execute("SET LOCAL statement_timeout = '540s'")
                    conn.execute("SET LOCAL TIME ZONE 'America/Santo_Domingo'")
                    snapshot = conn.execute('SELECT pg_export_snapshot() AS snapshot').fetchone()['snapshot']
                    flags = ['--no-password', '--no-owner', '--lock-wait-timeout=10000', f'--snapshot={snapshot}']
                    if scope == 'mall':
                        flags.append('--no-privileges')
                    self._command(['pg_dump', *flags, '--schema-only', *(['--schema=public'] if scope == 'mall' else [])], root / 'schema.sql', env, check, deadline)
                    manifest = {'format': 'msmall-postgres-backup-v1', 'scope': scope,
                                'mall_id': mall if scope == 'mall' else None,
                                'generated_at': datetime.now(timezone.utc).isoformat(),
                                'storage_files_included': False, 'contains_sensitive_data': True,
                                'restore_via_csv': False, 'role_passwords_included': False,
                                'date_range': {'start': start, 'end': end, 'timezone': 'America/Santo_Domingo'} if start else None,
                                'date_filtered_tables': ['ventas.fecha', 'logs_carga.fecha_hora'] if start else []}
                    if scope == 'platform':
                        self._command(['pg_dump', *flags, '--data-only', '--exclude-table-data=storage.buckets_vectors',
                                       '--exclude-table-data=storage.vector_indexes'], root / 'data.sql', env, check, deadline)
                        self._command(['pg_dumpall', '--no-password', '--roles-only', '--no-role-passwords'], root / 'roles.sql', env, check, deadline)
                        manifest['excluded_data'] = ['storage.buckets_vectors', 'storage.vector_indexes']
                        manifest['restore_target'] = 'Administración PostgreSQL; verificar roles y esquemas administrados de Supabase antes de restaurar.'
                    else:
                        tables = self._catalog(conn)
                        if not {'malls', 'locales'}.issubset(tables):
                            raise DatabaseBackupUnavailable('La base configurada no contiene las tablas de MsMall.')
                        if not conn.execute('SELECT id FROM public.malls WHERE id = %s', (mall,)).fetchone():
                            raise ValueError('Mall no encontrado en la base de backups.')
                        predicates = scope_predicates(tables, mall, start, end)
                        order = table_order(tables, predicates)
                        with (root / 'data.sql').open('wb') as output:
                            output.write(b'-- Mall data only. Restore into compatible schema with shared catalogs/users already present.\nBEGIN;\nSET standard_conforming_strings = on;\n')
                            for name in order:
                                columns = sql.SQL(', ').join(map(sql.Identifier, tables[name].columns))
                                header = sql.SQL('COPY public.{} ({}) FROM stdin;\n').format(sql.Identifier(name), columns)
                                output.write(header.as_string(conn).encode())
                                query = sql.SQL('COPY (SELECT {} FROM public.{} t WHERE {}) TO STDOUT').format(columns, sql.Identifier(name), predicates[name])
                                with conn.cursor().copy(query) as copy:
                                    for block in copy:
                                        output.write(block)
                                        output.flush()
                                        check()
                                output.write(b'\\.\n\n')
                            output.write(b'COMMIT;\n')
                        manifest.update(included_tables=order, excluded_public_tables=sorted(set(tables) - set(predicates)),
                                        ownership='mall_id, local_id or simple foreign keys to scoped parents',
                                        excluded_schemas=['auth', 'storage'],
                                        restore_target='Esquema compatible existente, usuarios y catálogos globales presentes. No ejecutar schema.sql sobre producción.')
                    (root / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
                    check()
                with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
                    for path in sorted(root.iterdir()):
                        bundle.write(path, path.name)
                if archive.tell() > max_bytes:
                    raise BackupSizeExceeded('El ZIP supera la cuota disponible.')
                archive.seek(0)
                return GeneratedBackup(archive, 0, [])
        except psycopg.OperationalError as exc:
            archive.close()
            raise DatabaseBackupUnavailable(connection_error_message(exc)) from exc
        except BaseException:
            archive.close()
            raise
