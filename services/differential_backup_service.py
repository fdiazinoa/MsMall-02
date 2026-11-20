"""Logical, per-Mall differentials against one private, immutable row-hash baseline.

Operational tables are only read. Baseline generation writes hashes in msmall_backup;
differentials only read them. No timestamps, business triggers or API credentials are used.
"""
import hashlib
import json
import os
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from services.database_backup_service import (
    DatabaseBackupService, DatabaseBackupUnavailable, Table, configuration,
    connection_error_message, scope_predicates, table_order,
)
from services.import_backup_service import BackupSizeExceeded, GeneratedBackup


def enabled():
    return configuration() and os.getenv('ENABLE_DIFFERENTIAL_BACKUPS', '').lower() in {'true', '1', 'yes'}


def normalized_schema_hash(content):
    # pg_dump 17 randomizes the psql restriction token for every invocation.
    lines = [line for line in content.splitlines() if not line.startswith((b'\\restrict ', b'\\unrestrict '))]
    return hashlib.sha256(b'\n'.join(lines)).hexdigest()


class DifferentialSelectionError(ValueError):
    """A safe, deliberately authored message about a missing/incompatible base."""


class DifferentialBackupService(DatabaseBackupService):
    def _snapshot_scope(self,conn,tables,mall):
        # Reuse the existing direct Mall/local roots, then resolve all FK columns.
        roots=scope_predicates({name:Table(name,table.columns,[]) for name,table in tables.items()},mall)
        relations={name:[] for name in tables}
        for row in conn.execute("""
            SELECT child.relname AS child, parent.relname AS parent,
              array_agg(ca.attname ORDER BY k.seq) AS child_columns,
              array_agg(pa.attname ORDER BY k.seq) AS parent_columns
            FROM pg_constraint f
            JOIN pg_class child ON child.oid=f.conrelid JOIN pg_namespace cn ON cn.oid=child.relnamespace
            JOIN pg_class parent ON parent.oid=f.confrelid JOIN pg_namespace pn ON pn.oid=parent.relnamespace
            CROSS JOIN LATERAL unnest(f.conkey,f.confkey) WITH ORDINALITY k(child_num,parent_num,seq)
            JOIN pg_attribute ca ON ca.attrelid=child.oid AND ca.attnum=k.child_num
            JOIN pg_attribute pa ON pa.attrelid=parent.oid AND pa.attnum=k.parent_num
            WHERE f.contype='f' AND cn.nspname='public' AND pn.nspname='public'
            GROUP BY f.oid,child.relname,parent.relname
        """):
            if row['child'] in relations and row['parent'] in tables:
                relations[row['child']].append(row)
        selected=set(roots)
        while True:
            added={name for name,parents in relations.items() if name not in selected
                   and any(rel['parent'] in selected for rel in parents)}
            if not added: break
            selected.update(added)
        # table_order only needs table dependencies; actual ownership checks below
        # use EVERY pair of columns, not the representative pair used in this graph.
        graph={name:Table(name,table.columns,[(rel['child_columns'][0],rel['parent'],rel['parent_columns'][0])
               for rel in relations[name]]) for name,table in tables.items()}
        order=table_order(graph,selected)
        predicates={}
        for name in order:
            checks,nonnull=[],[]
            for rel in relations[name]:
                parent=rel['parent']
                if parent not in predicates: continue
                child_cols,parent_cols=rel['child_columns'],rel['parent_columns']
                missing=sql.SQL(' OR ').join(sql.SQL('t.{} IS NULL').format(sql.Identifier(col)) for col in child_cols)
                populated=sql.SQL(' AND ').join(sql.SQL('t.{} IS NOT NULL').format(sql.Identifier(col)) for col in child_cols)
                match=sql.SQL(' AND ').join(sql.SQL('p.{}=t.{}').format(sql.Identifier(key),sql.Identifier(col)) for col,key in zip(child_cols,parent_cols))
                parent_keys=sql.SQL(', ').join(sql.SQL('t.{}').format(sql.Identifier(key)) for key in parent_cols)
                checks.append(sql.SQL('(({}) OR EXISTS (SELECT 1 FROM (SELECT {} FROM public.{} t WHERE {}) p WHERE {}))').format(
                    missing,parent_keys,sql.Identifier(parent),predicates[parent],match))
                nonnull.append(sql.SQL('({})').format(populated))
            checks_sql=sql.SQL(' AND ').join(checks) if checks else sql.SQL('true')
            if name in roots:
                predicates[name]=sql.SQL('({}) AND ({})').format(roots[name],checks_sql)
            else:
                predicates[name]=sql.SQL('({}) AND ({})').format(checks_sql,sql.SQL(' OR ').join(nonnull))
        return predicates,order

    def _ready(self):
        if not enabled():
            raise DatabaseBackupUnavailable('La opción diferencial no está habilitada en este servidor.')

    def _connection(self):
        return (self._connect or psycopg.connect)(os.environ['BACKUP_DATABASE_URL'], connect_timeout=10, row_factory=dict_row)

    def baseline(self, mall):
        self._ready()
        mall = str(UUID(mall))
        try:
            with self._connection() as conn:
                conn.execute('SET TRANSACTION READ ONLY')
                row = conn.execute('SELECT id, created_at, row_count, sql_bytes FROM msmall_backup.baselines WHERE mall_id = %s', (mall,)).fetchone()
                return ({**row, 'id': str(row['id']), 'created_at': row['created_at'].isoformat()} if row else None)
        except psycopg.Error as exc:
            raise self._safe_error(exc) from exc

    @staticmethod
    def _safe_error(exc):
        if exc.sqlstate in {'42P01', '3F000', '42501'}:
            return DatabaseBackupUnavailable('Falta la migración o el permiso del servidor para las bases diferenciales.')
        if isinstance(exc, psycopg.OperationalError):
            return DatabaseBackupUnavailable(connection_error_message(exc))
        return DatabaseBackupUnavailable('No se pudo generar el diferencial. Revisa el esquema, los permisos y la compatibilidad de la base.')

    @staticmethod
    def _key(keys):
        return sql.SQL('jsonb_build_object({})').format(sql.SQL(', ').join(
            sql.SQL('{}, t.{}').format(sql.Literal(key), sql.Identifier(key)) for key in keys))

    @staticmethod
    def _hash(columns):
        # Hashes are computed in PostgreSQL; unchanged row contents never leave it.
        return sql.SQL("sha256(convert_to(jsonb_build_array({})::text, 'UTF8'))").format(
            sql.SQL(', ').join(sql.SQL('t.{}').format(sql.Identifier(col)) for col in columns))

    def generate_snapshot(self, mode, mall, *, base_id=None, max_bytes, on_progress, check_active, on_ready=None, on_archive_ready=None):
        self._ready()
        if mode not in {'base', 'differential'}:
            raise DifferentialSelectionError('Tipo de backup inválido.')
        mall = str(UUID(mall))
        if mode == 'differential' and not base_id:
            raise DifferentialSelectionError('Selecciona el respaldo completo que servirá de base.')
        base_id = str(UUID(str(base_id))) if base_id else str(uuid4())
        archive = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode='w+b')
        deadline = time.monotonic() + 600
        try:
            with self._connection() as conn, tempfile.TemporaryDirectory(prefix='msmall-differential-') as directory:
                # Only full-base requests write, and only to the private metadata schema.
                conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, ' + ('READ WRITE' if mode == 'base' else 'READ ONLY'))
                conn.execute("SET LOCAL statement_timeout = '540s'")
                conn.execute("SET LOCAL lock_timeout = '5s'")
                conn.execute("SET LOCAL TIME ZONE 'UTC'")
                conn.execute("SET LOCAL DateStyle = 'ISO, YMD'")
                if not conn.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0)) AS locked", ('msmall-differential:' + mall,)).fetchone()['locked']:
                    raise DatabaseBackupUnavailable('Ya se está generando una base o diferencial de este Mall.')
                root = Path(directory)

                def check():
                    check_active()
                    size = sum(path.stat().st_size for path in root.iterdir() if path.is_file())
                    on_progress(size)
                    if size > max_bytes:
                        raise BackupSizeExceeded('El backup SQL supera el tamaño o cuota disponible. Revisa los límites globales de backup.')
                    if time.monotonic() >= deadline:
                        raise DatabaseBackupUnavailable('El backup excedió el tiempo permitido.')

                tables = self._catalog(conn)
                if not {'malls', 'locales'}.issubset(tables) or not conn.execute('SELECT id FROM public.malls WHERE id = %s', (mall,)).fetchone():
                    raise DatabaseBackupUnavailable('El Mall no existe en la base de backups configurada.')
                predicates,order = self._snapshot_scope(conn,tables,mall)
                # Keep DDL stable across catalog discovery, hashing and COPY.
                conn.execute(sql.SQL('LOCK TABLE {} IN ACCESS SHARE MODE').format(
                    sql.SQL(', ').join(sql.Identifier('public', table) for table in order)))
                keys = {}
                for row in conn.execute("""
                    SELECT c.relname AS name, array_agg(a.attname ORDER BY k.ordinality) AS keys
                    FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY k(attnum, ordinality)
                    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum
                    WHERE n.nspname = 'public' AND i.indisprimary
                    GROUP BY c.relname
                """):
                    keys[row['name']] = row['keys']
                if any(not keys.get(table) or not set(keys[table]).issubset(tables[table].columns) for table in order):
                    raise DatabaseBackupUnavailable('Todas las tablas del respaldo diferencial requieren una clave primaria exportable. Usa el backup por período.')

                snapshot = conn.execute('SELECT pg_export_snapshot() AS id').fetchone()['id']
                params = conninfo_to_dict(os.environ['BACKUP_DATABASE_URL'])
                env = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
                for key, value in params.items():
                    # Match the explicit libpq options supported by the existing SQL backup.
                    if key in {'host', 'hostaddr', 'port', 'dbname', 'user', 'password', 'sslmode', 'sslrootcert', 'sslcert', 'sslkey', 'channel_binding'}:
                        env['PGDATABASE' if key == 'dbname' else 'PG' + key.upper().replace('_', '')] = value
                env.update(PGCONNECT_TIMEOUT='10', PGOPTIONS='-c default_transaction_read_only=on', PGAPPNAME='msmall-differential-backup')
                self._command(['pg_dump', '--no-password', '--no-owner', '--no-privileges', '--schema-only', '--schema=public', f'--snapshot={snapshot}'], root / 'schema.sql', env, check, deadline)
                schema_hash = hashlib.sha256(('composite-scope-v2:' + normalized_schema_hash((root / 'schema.sql').read_bytes())).encode()).hexdigest()
                if mode == 'differential':
                    baseline = conn.execute('SELECT id, schema_hash, created_at FROM msmall_backup.baselines WHERE id = %s AND mall_id = %s', (base_id, mall)).fetchone()
                    if not baseline:
                        raise DifferentialSelectionError('La base seleccionada no existe, fue reemplazada o pertenece a otro Mall. Genera un completo nuevo.')
                    if baseline['schema_hash'] != schema_hash:
                        raise DifferentialSelectionError('El esquema cambió desde el respaldo base. Genera un completo nuevo antes del diferencial.')
                    # DDL is checked but not replayed on a differential target.
                    (root / 'schema.sql').unlink()
                else:
                    conn.execute('DELETE FROM msmall_backup.baselines WHERE mall_id = %s', (mall,))
                    conn.execute('INSERT INTO msmall_backup.baselines (id, mall_id, schema_hash) VALUES (%s,%s,%s)', (base_id, mall, schema_hash))

                counts = {}
                export_id = str(uuid4())
                with (root / 'data.sql').open('wb') as output:
                    def write(statement):
                        output.write((statement.as_string(conn) if hasattr(statement, 'as_string') else statement).encode())
                        output.flush()
                        check()

                    def copy(query):
                        with conn.cursor().copy(query) as stream:
                            for block in stream:
                                output.write(block)
                                output.flush()
                                check()
                        write('\\.\n\n')

                    write("-- Restore only in a dedicated recovery environment; contains sensitive data.\nBEGIN;\nSET standard_conforming_strings = on;\nSET LOCAL TIME ZONE 'UTC';\nSET LOCAL DateStyle = 'ISO, YMD';\n")
                    if mode == 'base':
                        write('CREATE SCHEMA IF NOT EXISTS msmall_restore;\nREVOKE ALL ON SCHEMA msmall_restore FROM PUBLIC;\n'
                              'CREATE TABLE IF NOT EXISTS msmall_restore.baselines (mall_id uuid PRIMARY KEY, base_id uuid NOT NULL, state text NOT NULL);\n'
                              'REVOKE ALL ON msmall_restore.baselines FROM PUBLIC;\n')
                    else:
                        # A differential always applies to its original complete, never to another differential.
                        write(sql.SQL("DO $guard$ BEGIN PERFORM 1 FROM msmall_restore.baselines WHERE mall_id = {}::uuid AND base_id = {}::uuid AND state = 'base' FOR UPDATE; IF NOT FOUND THEN RAISE EXCEPTION 'Restore the matching original full base before this differential'; END IF; END $guard$;\n").format(sql.Literal(mall), sql.Literal(base_id)))
                    for index, table in enumerate(order):
                        columns = tables[table].columns
                        names = sql.SQL(', ').join(map(sql.Identifier, columns))
                        selected = sql.SQL(', ').join(sql.SQL('t.{}').format(sql.Identifier(col)) for col in columns)
                        key_expr, hash_expr = self._key(keys[table]), self._hash(columns)
                        predicate = predicates[table]
                        if mode == 'base':
                            write(sql.SQL('COPY public.{} ({}) FROM stdin;\n').format(sql.Identifier(table), names))
                            copy(sql.SQL('COPY (SELECT {} FROM public.{} t WHERE {}) TO STDOUT').format(selected, sql.Identifier(table), predicate))
                            result = conn.execute(sql.SQL('INSERT INTO msmall_backup.row_fingerprints (baseline_id, table_name, row_key, row_hash) SELECT {}, {}, {}, {} FROM public.{} t WHERE {}').format(
                                sql.Literal(base_id), sql.Literal(table), key_expr, hash_expr, sql.Identifier(table), predicate))
                            counts[table] = {'rows': result.rowcount}
                        else:
                            stage, removed = f'msb_rows_{index}', f'msb_deleted_{index}'
                            key_names = sql.SQL(', ').join(map(sql.Identifier, keys[table]))
                            write(sql.SQL('CREATE TEMP TABLE {} ON COMMIT DROP AS SELECT {} FROM public.{} WITH NO DATA;\n').format(sql.Identifier(stage), names, sql.Identifier(table)))
                            write(sql.SQL('COPY pg_temp.{} ({}) FROM stdin;\n').format(sql.Identifier(stage), names))
                            # Anti-join on key and SHA-256 catches inserts and changes, including old business dates.
                            copy(sql.SQL('COPY (SELECT {} FROM public.{} t LEFT JOIN msmall_backup.row_fingerprints b ON b.baseline_id = {}::uuid AND b.table_name = {} AND b.row_key = {} WHERE ({}) AND b.row_hash IS DISTINCT FROM {}) TO STDOUT').format(
                                selected, sql.Identifier(table), sql.Literal(base_id), sql.Literal(table), key_expr, predicate, hash_expr))
                            write(sql.SQL('CREATE TEMP TABLE {} ON COMMIT DROP AS SELECT {} FROM public.{} WITH NO DATA;\n').format(sql.Identifier(removed), key_names, sql.Identifier(table)))
                            write(sql.SQL('COPY pg_temp.{} ({}) FROM stdin;\n').format(sql.Identifier(removed), key_names))
                            extracted_keys = sql.SQL(', ').join(sql.SQL('r.{}').format(sql.Identifier(col)) for col in keys[table])
                            copy(sql.SQL('COPY (SELECT {} FROM msmall_backup.row_fingerprints b CROSS JOIN LATERAL jsonb_populate_record(NULL::public.{}, b.row_key) r WHERE b.baseline_id = {}::uuid AND b.table_name = {} AND NOT EXISTS (SELECT 1 FROM public.{} t WHERE ({}) AND {} = b.row_key)) TO STDOUT').format(
                                extracted_keys, sql.Identifier(table), sql.Literal(base_id), sql.Literal(table), sql.Identifier(table), predicate, key_expr))
                        check()
                    if mode == 'differential':
                        for index in reversed(range(len(order))):
                            table = order[index]
                            match = sql.SQL(' AND ').join(sql.SQL('t.{} = d.{}').format(sql.Identifier(key), sql.Identifier(key)) for key in keys[table])
                            write(sql.SQL('DELETE FROM public.{} t USING pg_temp.{} d WHERE {};\n').format(sql.Identifier(table), sql.Identifier(f'msb_deleted_{index}'), match))
                        for index, table in enumerate(order):
                            names = sql.SQL(', ').join(map(sql.Identifier, tables[table].columns))
                            updates = [col for col in tables[table].columns if col not in keys[table]]
                            conflict = sql.SQL('DO UPDATE SET {}').format(sql.SQL(', ').join(sql.SQL('{} = EXCLUDED.{}').format(sql.Identifier(col), sql.Identifier(col)) for col in updates)) if updates else sql.SQL('DO NOTHING')
                            write(sql.SQL('INSERT INTO public.{} ({}) OVERRIDING SYSTEM VALUE SELECT {} FROM pg_temp.{} WHERE true ON CONFLICT ({}) {};\n').format(
                                sql.Identifier(table), names, names, sql.Identifier(f'msb_rows_{index}'), sql.SQL(', ').join(map(sql.Identifier, keys[table])), conflict))
                        write(sql.SQL("UPDATE msmall_restore.baselines SET state = {} WHERE mall_id = {}::uuid;\n").format(sql.Literal('differential:' + export_id), sql.Literal(mall)))
                    else:
                        write(sql.SQL("INSERT INTO msmall_restore.baselines VALUES ({}::uuid, {}::uuid, 'base');\n").format(sql.Literal(mall), sql.Literal(base_id)))
                    write('COMMIT;\n')
                total_sql = sum(p.stat().st_size for p in root.iterdir())
                if mode == 'base':
                    conn.execute('UPDATE msmall_backup.baselines SET row_count = %s, sql_bytes = %s WHERE id = %s', (sum(r['rows'] for r in counts.values()), total_sql, base_id))
                    # A new baseline can add millions of rows. Do not let its first
                    # differential plan joins against an apparently empty hash table.
                    conn.execute('ANALYZE msmall_backup.row_fingerprints')
                    check()
                manifest = {'format': 'msmall-postgres-differential-v1', 'scope': 'mall', 'mode': mode,
                            'mall_id': mall, 'base_id': base_id, 'export_id': export_id,
                            'generated_at': datetime.now(timezone.utc).isoformat(), 'schema_hash': schema_hash,
                            'date_range': None, 'included_tables': order, 'sql_bytes': total_sql,
                            'contains_sensitive_data': True, 'storage_files_included': False,
                            'restore': 'Original complete base + one differential, in a compatible dedicated recovery database. Never chain differentials.',
                            'excluded_public_tables': sorted(set(tables) - set(order))}
                (root / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
                check()
                with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as bundle:
                    for path in sorted(root.iterdir()):
                        with path.open('rb') as source, bundle.open(path.name, 'w', force_zip64=True) as target:
                            while block := source.read(1024 * 1024):
                                target.write(block)
                                check()
                if archive.tell() > max_bytes:
                    raise BackupSizeExceeded('El ZIP supera la cuota disponible.')
                check()
                if on_archive_ready is not None:
                    archive.seek(0)
                    on_archive_ready(archive, manifest, check)
                    archive.seek(0, 2)
                    check()
                if on_ready is not None:
                    on_ready(archive.tell())
                # Committing the private baseline only happens after the entire archive succeeds.
            archive.seek(0)
            return GeneratedBackup(archive, 0, [])
        except psycopg.Error as exc:
            archive.close()
            raise self._safe_error(exc) from exc
        except BaseException:
            archive.close()
            raise
