/**
 * Pending Import Monitor
 * Detecta importaciones que no encontraron archivo el día de hoy
 * y reintenta procesarlas cada 2-3 horas
 * 
 * Cron (UTC): 0 0,15,18,21 * * * (8pm, 11am, 2pm, 5pm America/Santo_Domingo)
 * Final alert: 0 21 * * * (9pm)
 */

import { createClient } from "@supabase/supabase-js";
import { Client as FtpClient } from "basic-ftp";
import { Resend } from "resend";
import SftpClient from "ssh2-sftp-client";

interface PendingImport {
  local_id: string;
  local_nombre: string;
  mall_id: string;
  mall_nombre: string;
  email: string;
  email_secundario?: string;
  ultimo_intento: string; // fecha_hora del log
  log_id: string;
}

interface LocalConfig {
  id: string;
  nombre: string;
  sftp_host: string;
  sftp_port: number;
  sftp_user: string;
  sftp_pass: string;
  sftp_path: string;
  sftp_protocol: string;
  file_type: string;
  email: string;
  email_secundario?: string;
  mall_id: string;
}

interface RemoteFile {
  name: string;
  modifiedAt: number;
}

interface ProcessResult {
  local_id: string;
  local_nombre: string;
  status: "recovered" | "still_pending" | "error";
  message: string;
  processed_at?: string;
  file_found?: string;
}

const SUPABASE_URL = Bun.env.SUPABASE_URL!;
const SUPABASE_KEY = Bun.env.SUPABASE_KEY!;
const RESEND_API_KEY = Bun.env.RESEND_API_KEY!;
const WORKER_API_URL = Bun.env.WORKER_API_URL || "http://localhost:3000/api";
const DOMINICAN_TIMEZONE = "America/Santo_Domingo";

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);
const resend = new Resend(RESEND_API_KEY);

function startOfTodayInDominicanRepublic(): Date {
  const dateParts = new Intl.DateTimeFormat("en-CA", {
    timeZone: DOMINICAN_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(
    dateParts
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value])
  );

  // República Dominicana es UTC-4 todo el año; el inicio local del día es 04:00 UTC.
  return new Date(
    Date.UTC(Number(values.year), Number(values.month) - 1, Number(values.day), 4)
  );
}

async function findPendingImports(): Promise<PendingImport[]> {
  const today = startOfTodayInDominicanRepublic();

  try {
    const { data, error } = await supabase
      .from("logs_carga")
      .select("*")
      .eq("estado", "exito")
      .eq("archivo", "N/A")
      .ilike("mensaje", "Archivo nuevo no encontrado%")
      .gte("fecha_hora", today.toISOString())
      .order("fecha_hora", { ascending: false });

    if (error) throw error;

    // Agrupar por local_id (tomar el más reciente)
    const grouped = new Map<string, any>();
    for (const log of data || []) {
      if (!grouped.has(log.local_id)) {
        grouped.set(log.local_id, log);
      }
    }

    const pending: PendingImport[] = [];
    for (const log of grouped.values()) {
      pending.push({
        local_id: log.local_id,
        local_nombre: log.local_nombre,
        mall_id: log.mall_id,
        mall_nombre: log.mall_nombre,
        email: log.email || "",
        email_secundario: log.email_secundario,
        ultimo_intento: log.fecha_hora,
        log_id: log.id,
      });
    }

    return pending;
  } catch (e) {
    console.error("Error fetching pending imports:", e);
    return [];
  }
}

async function getLocalConfig(local_id: string): Promise<LocalConfig | null> {
  try {
    const { data, error } = await supabase
      .from("locales")
      .select("*")
      .eq("id", local_id)
      .single();

    if (error) throw error;
    return data as LocalConfig;
  } catch (e) {
    console.error(`Error fetching config for local ${local_id}:`, e);
    return null;
  }
}

function configuredExtensions(fileType?: string): string[] {
  const configured = String(fileType || "CSV,TXT")
    .split(/[,;\s]+/)
    .map((value) => value.trim().replace(/^\./, "").toLowerCase())
    .filter(Boolean);
  return configured.length > 0 ? configured : ["csv", "txt"];
}

function isCandidateFile(name: string, extensions: string[]): boolean {
  const normalized = String(name || "").trim();
  const lowerName = normalized.toLowerCase();
  const extension = lowerName.split(".").pop() || "";
  return Boolean(normalized)
    && !/^(pr_|err_|tmp_|\.)/i.test(normalized)
    && !lowerName.endsWith(".part")
    && extensions.includes(extension);
}

async function listRemoteFiles(config: LocalConfig): Promise<RemoteFile[]> {
  const protocol = String(config.sftp_protocol || "SFTP").trim().toUpperCase();
  const host = String(config.sftp_host || "").trim();
  const username = String(config.sftp_user || "").trim();
  const password = String(config.sftp_pass || "");
  const port = Number(config.sftp_port || (protocol === "FTP" ? 21 : 22));
  const remotePath = String(config.sftp_path || ".").trim() || ".";

  if (!host || !username || !password) {
    throw new Error("La conexión remota no tiene host, usuario o contraseña configurados.");
  }

  if (protocol === "SFTP") {
    const client = new SftpClient();
    try {
      await client.connect({ host, port, username, password, readyTimeout: 20_000 });
      const files = await client.list(remotePath);
      return files
        .filter((file: any) => file.type !== "d")
        .map((file: any) => ({
          name: String(file.name || ""),
          modifiedAt: Number(file.modifyTime || 0),
        }));
    } finally {
      await client.end().catch(() => undefined);
    }
  }

  if (protocol === "FTP") {
    const client = new FtpClient(20_000);
    try {
      await client.access({ host, port, user: username, password, secure: false });
      const files = await client.list(remotePath);
      return files
        .filter((file) => !file.isDirectory)
        .map((file) => ({
          name: String(file.name || ""),
          modifiedAt: file.modifiedAt?.getTime() || 0,
        }));
    } finally {
      client.close();
    }
  }

  throw new Error(`Protocolo remoto no soportado: ${protocol}.`);
}

async function latestUnprocessedFile(config: LocalConfig): Promise<string | undefined> {
  const extensions = configuredExtensions(config.file_type);
  const { data, error } = await supabase
    .from("logs_carga")
    .select("archivo")
    .eq("local_id", config.id)
    .eq("estado", "exito")
    .neq("archivo", "N/A")
    .order("fecha_hora", { ascending: false })
    .limit(1000);
  if (error) throw error;

  const alreadyProcessed = new Set(
    (data || []).map((row: any) => String(row.archivo || "").trim().toLowerCase())
  );
  const candidates = (await listRemoteFiles(config))
    .filter((file) => isCandidateFile(file.name, extensions))
    .filter((file) => !alreadyProcessed.has(file.name.toLowerCase()))
    .sort((left, right) => right.modifiedAt - left.modifiedAt);
  return candidates[0]?.name;
}

async function triggerManualImport(
  local_id: string,
  filename: string
): Promise<boolean> {
  try {
    // Llamar al endpoint del worker
    const response = await fetch(`${WORKER_API_URL}/v1/remote/execute-manual`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${SUPABASE_KEY}`,
      },
      body: JSON.stringify({
        config_id: local_id,
        filename: filename,
        request_id: `pending-monitor-${Date.now()}`,
      }),
    });

    return response.ok;
  } catch (e) {
    console.error(`Error triggering import for ${local_id}:`, e);
    return false;
  }
}

async function logRetryAttempt(
  pending: PendingImport,
  result: ProcessResult,
  startedAt: number
): Promise<void> {
  try {
    const completedAt = new Date().toISOString();
    const failed = result.status === "error";
    const run = {
      mall_id: pending.mall_id,
      local_id: pending.local_id,
      run_type: "scheduled",
      status: failed ? "fail" : "ok",
      error_code: failed ? "unknown_error" : null,
      error_message: failed ? result.message.slice(0, 500) : null,
      started_at: new Date(startedAt).toISOString(),
      finished_at: completedAt,
      duration_ms: Math.max(0, Date.now() - startedAt),
    };
    const { data: connectionRun, error: runError } = await supabase
      .from("connection_runs")
      .insert(run)
      .select("id")
      .single();
    if (runError) throw runError;

    const { error: retryError } = await supabase.from("retry_attempts").insert({
      connection_run_id: connectionRun.id,
      attempt_no: 1,
      status: failed ? "fail" : "ok",
      error_code: failed ? "unknown_error" : null,
      error_message: `${result.message} [source_log=${pending.log_id}]`.slice(0, 500),
      attempted_at: completedAt,
      duration_ms: Math.max(0, Date.now() - startedAt),
      mall_id: pending.mall_id,
    });
    if (retryError) throw retryError;
  } catch (e) {
    console.error(`Error logging retry:`, e);
  }
}

async function getMallAdminEmails(mall_id: string): Promise<string[]> {
  try {
    const { data, error } = await supabase
      .rpc("get_mall_admin_emails", { p_mall_id: mall_id });

    if (error) {
      // Fallback: función RPC podría no existir
      return [];
    }

    return (data || []).map((u: any) => u.email).filter(Boolean);
  } catch (e) {
    console.error(`Error fetching mall admin emails:`, e);
    return [];
  }
}

async function sendNotificationEmail(
  results: ProcessResult[],
  pending: Map<string, PendingImport>
): Promise<void> {
  const recovered = results.filter((r) => r.status === "recovered");
  const stillPending = results.filter((r) => r.status === "still_pending");

  if (recovered.length === 0 && stillPending.length === 0) {
    return;
  }

  // Agrupar por local para enviar emails personalizados
  const emailsByLocal = new Map<
    string,
    {
      to: string[];
      local_nombre: string;
      mall_nombre: string;
      recovered: ProcessResult[];
      pending: ProcessResult[];
    }
  >();

  for (const result of results) {
    const p = pending.get(result.local_id);
    if (!p) continue;

    const recipients = [p.email];
    if (p.email_secundario) recipients.push(p.email_secundario);

    const key = `${p.local_id}`;
    if (!emailsByLocal.has(key)) {
      emailsByLocal.set(key, {
        to: recipients,
        local_nombre: p.local_nombre,
        mall_nombre: p.mall_nombre,
        recovered: [],
        pending: [],
      });
    }

    const entry = emailsByLocal.get(key)!;
    if (result.status === "recovered") {
      entry.recovered.push(result);
    } else {
      entry.pending.push(result);
    }
  }

  // Enviar emails
  for (const [_, email_data] of emailsByLocal) {
    const subject = email_data.recovered.length
      ? `✅ Archivos importados - ${email_data.local_nombre}`
      : `⏳ Archivos pendientes - ${email_data.local_nombre}`;

    const html = buildEmailHtml(
      email_data.local_nombre,
      email_data.mall_nombre,
      email_data.recovered,
      email_data.pending
    );

    try {
      await resend.emails.send({
        from: "Monitor <notificaciones@mercasend.net>",
        to: email_data.to,
        subject,
        html,
      });
      console.log(`✅ Email sent to ${email_data.to.join(", ")}`);
    } catch (e) {
      console.error(`Error sending email:`, e);
    }
  }
}

function buildEmailHtml(
  local_nombre: string,
  mall_nombre: string,
  recovered: ProcessResult[],
  pending: ProcessResult[]
): string {
  const now = new Date().toLocaleString("es-DO");

  let html = `
    <h2>📊 Monitor de Importaciones - ${local_nombre}</h2>
    <p><strong>Mall:</strong> ${mall_nombre}</p>
    <p><strong>Revisado:</strong> ${now}</p>
  `;

  if (recovered.length > 0) {
    html += `
      <h3>✅ Archivos Recuperados</h3>
      <ul>
    `;
    for (const r of recovered) {
      html += `<li>${r.file_found} - Importado a las ${r.processed_at}</li>`;
    }
    html += `</ul>`;
  }

  if (pending.length > 0) {
    html += `
      <h3>⏳ Archivos Pendientes</h3>
      <p>Los siguientes archivos aún no se encuentran en el servidor:</p>
      <ul>
    `;
    for (const p of pending) {
      html += `<li>${p.message}</li>`;
    }
    html += `</ul>
      <p><em>Se volverá a revisar en el próximo ciclo de monitoreo.</em></p>
    `;
  }

  html += `
    <hr>
    <p style="color: #999; font-size: 12px;">
      Próxima revisión: ${new Date(Date.now() + 3 * 60 * 60 * 1000).toLocaleString("es-DO")}
    </p>
  `;

  return html;
}

async function runMonitor(): Promise<void> {
  console.log("🔍 [Pending Import Monitor] Starting...");

  const pending = await findPendingImports();
  console.log(`📋 Found ${pending.length} pending imports today`);

  if (pending.length === 0) {
    console.log("✅ No pending imports, exiting");
    return;
  }

  const results: ProcessResult[] = [];
  const pendingMap = new Map(pending.map((p) => [p.local_id, p]));

  for (const p of pending) {
    const startedAt = Date.now();
    const config = await getLocalConfig(p.local_id);
    if (!config) {
      const result: ProcessResult = {
        local_id: p.local_id,
        local_nombre: p.local_nombre,
        status: "error",
        message: "No se pudo cargar configuración del local",
      };
      results.push(result);
      await logRetryAttempt(p, result, startedAt);
      continue;
    }

    console.log(`\n🔎 Checking ${config.local_nombre}...`);

    let filename: string | undefined;
    try {
      filename = await latestUnprocessedFile(config);
    } catch (error) {
      const result: ProcessResult = {
        local_id: config.id,
        local_nombre: config.nombre,
        status: "error",
        message: `No se pudo revisar el servidor remoto: ${error instanceof Error ? error.message : "error desconocido"}`,
      };
      results.push(result);
      await logRetryAttempt(p, result, startedAt);
      continue;
    }

    if (filename) {
      console.log(`  📁 File found: ${filename}`);
      const success = await triggerManualImport(config.id, filename);

      if (success) {
        const result: ProcessResult = {
          local_id: config.id,
          local_nombre: config.nombre,
          status: "recovered",
          message: `Archivo ${filename} encontrado y procesado`,
          processed_at: new Date().toISOString(),
          file_found: filename,
        };
        results.push(result);
        await logRetryAttempt(p, result, startedAt);
      } else {
        const result: ProcessResult = {
          local_id: config.id,
          local_nombre: config.nombre,
          status: "error",
          message: `Archivo encontrado pero error al procesar: ${filename}`,
        };
        results.push(result);
        await logRetryAttempt(p, result, startedAt);
      }
    } else {
      console.log(`  ⏳ No file found yet`);
      const result: ProcessResult = {
        local_id: config.id,
        local_nombre: config.nombre,
        status: "still_pending",
        message: "Archivo no encontrado aún. Próxima revisión en 3 horas.",
      };
      results.push(result);
      await logRetryAttempt(p, result, startedAt);
    }
  }

  // Enviar notificaciones
  if (results.length > 0) {
    await sendNotificationEmail(results, pendingMap);
  }

  console.log("\n✅ Monitor completed");
  console.log(`   Recovered: ${results.filter((r) => r.status === "recovered").length}`);
  console.log(`   Pending: ${results.filter((r) => r.status === "still_pending").length}`);
  console.log(`   Errors: ${results.filter((r) => r.status === "error").length}`);
}

// Ejecutar monitor
await runMonitor();
