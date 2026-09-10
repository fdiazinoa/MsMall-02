export async function fetchAuthJson(bases, path, token, fetcher = fetch) {
    for (const base of bases) {
        try {
            const response = await fetcher(`${base}${path}`, {
                headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
                cache: 'no-store',
                signal: AbortSignal.timeout(15000),
            });
            if (!response.ok) continue;
            return await response.json();
        } catch {
            // Network errors, timeouts and HTML responses can use the next route.
        }
    }
    throw new Error('No se pudieron cargar los datos de acceso. Reintenta en unos segundos.');
}

export function parseMallsPayload(payload) {
    const malls = Array.isArray(payload) ? payload : payload?.data ?? payload?.malls;
    if (!Array.isArray(malls) || malls.some(m => !m || typeof m.id !== 'string' || typeof m.nombre !== 'string')) {
        throw new Error('La respuesta de Malls no es válida. Reintenta la carga.');
    }
    return malls;
}
