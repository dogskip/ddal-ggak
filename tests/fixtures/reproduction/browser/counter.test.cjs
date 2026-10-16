const { test } = require('node:test');
const assert = require('node:assert/strict');
const { reset } = require('./counter.js');

test('reset returns zero', () => assert.equal(reset(), 0));
