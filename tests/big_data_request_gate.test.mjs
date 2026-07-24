import assert from 'node:assert/strict';
import test from 'node:test';
import { createBigDataRequestGate } from '../utils/bigDataRequestGate.js';

test('rapid mall changes ignore a delayed response from the prior mall', () => {
  const gate = createBigDataRequestGate();
  const state = { mall: null, data: null, loading: false };

  const mallARequest = gate.begin();
  state.mall = 'mall-a';
  state.data = null;
  state.loading = true;

  const mallBRequest = gate.begin();
  state.mall = 'mall-b';
  state.data = null;
  state.loading = true;

  if (gate.isCurrent(mallBRequest)) {
    state.data = { mall: 'mall-b' };
    state.loading = false;
  }
  if (gate.isCurrent(mallARequest)) {
    state.data = { mall: 'mall-a' };
    state.loading = false;
  }

  assert.deepEqual(state, { mall: 'mall-b', data: { mall: 'mall-b' }, loading: false });
});
