import assert from 'node:assert/strict';
import test from 'node:test';
import { fetchAuthJson, parseMallsPayload } from '../utils/authRequests.js';

test('connection failures are errors instead of empty mall assignments', async () => {
    await assert.rejects(fetchAuthJson(['https://direct', ''], '/malls', 'test', async () => new Response('', { status: 503 })), /No se pudieron/);
});

test('HTML response falls back to the next route', async () => {
    let calls = 0;
    const payload = await fetchAuthJson(['https://direct', ''], '/malls', 'test', async () => {
        calls++;
        return calls === 1 ? new Response('<html>') : Response.json([{ id: '1', nombre: 'Mall' }]);
    });
    assert.equal(calls, 2);
    assert.equal(parseMallsPayload(payload)[0].id, '1');
});

test('authoritative empty assignments remain empty; malformed payloads fail', () => {
    assert.deepEqual(parseMallsPayload([]), []);
    for (const value of [null, {}, { data: null }, [{ error: 'unavailable' }]]) {
        assert.throws(() => parseMallsPayload(value), /no es válida/);
    }
});

test('request includes timeout and authenticated no-store headers', async () => {
    await fetchAuthJson([''], '/malls', 'test', async (url, options) => {
        assert.equal(url, '/malls');
        assert.equal(options.headers.Authorization, 'Bearer test');
        assert.equal(options.cache, 'no-store');
        assert.ok(options.signal instanceof AbortSignal);
        return Response.json([]);
    });
});
