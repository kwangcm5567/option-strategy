import test from 'node:test';
import assert from 'node:assert/strict';
import { riskLimitedContracts } from '../src/tabs/scanner/positionSizing.js';

test('zero contracts when one put exceeds the risk budget', () => {
  assert.equal(riskLimitedContracts(50000, 9203.30, 9300), 0);
});

test('unlimited or unknown losses cannot produce a position size', () => {
  for (const loss of [null, undefined, Infinity, NaN, 0, -1]) {
    assert.equal(riskLimitedContracts(50000, loss, 1000), 0);
  }
});

test('both risk and available cash constrain contract counts', () => {
  assert.equal(riskLimitedContracts(50000, 200, 200), 5);
  assert.equal(riskLimitedContracts(50000, 200, 30000), 1);
  assert.equal(riskLimitedContracts(0, 200, 200), 0);
});
