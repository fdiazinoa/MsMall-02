export const OPEN_IMPORT_CONNECTION_EVENT = 'msmall:open-import-connection';
const PENDING_IMPORT_CONNECTION_KEY = 'msmall.pendingImportConnection';

export interface ImportConnectionOpenRequest {
  localId?: string;
  localName?: string;
  logId?: string;
}

const canUseBrowserStorage = () => typeof window !== 'undefined' && !!window.sessionStorage;

export const queueImportConnectionOpenRequest = (request: ImportConnectionOpenRequest) => {
  if (!canUseBrowserStorage()) return;
  try {
    window.sessionStorage.setItem(PENDING_IMPORT_CONNECTION_KEY, JSON.stringify(request));
    window.dispatchEvent(new CustomEvent(OPEN_IMPORT_CONNECTION_EVENT, { detail: request }));
  } catch (error) {
    console.warn('No se pudo registrar la navegación a conexión de importación:', error);
  }
};

export const peekImportConnectionOpenRequest = (): ImportConnectionOpenRequest | null => {
  if (!canUseBrowserStorage()) return null;
  try {
    const raw = window.sessionStorage.getItem(PENDING_IMPORT_CONNECTION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    return parsed as ImportConnectionOpenRequest;
  } catch {
    return null;
  }
};

export const clearImportConnectionOpenRequest = () => {
  if (!canUseBrowserStorage()) return;
  try {
    window.sessionStorage.removeItem(PENDING_IMPORT_CONNECTION_KEY);
  } catch {
    // noop
  }
};
