const { test } = require('node:test');
const assert = require('node:assert/strict');
const { label } = require('./label.cjs');

test('empty input keeps its label', () => assert.equal(label(''), '(empty)'));
test('normalized input remains unchanged', () => assert.equal(label('hello-world'), 'hello-world'));
