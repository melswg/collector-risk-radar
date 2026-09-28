import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/event-presentation.ts', import.meta.url), 'utf8');
const {outputText} = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}});
const {eventPresentation} = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);

test('only an explicit normal event is labelled normal', () => {
  assert.equal(eventPresentation('normal').label, 'Норма');
  for (const value of ['info', 'warning', 'critical', 'alarm', 'error', 'new-type', '', null, undefined, 'constructor']) {
    assert.notEqual(eventPresentation(value).label, 'Норма');
  }
});
test('critical events retain their level and unknown values stay unknown', () => {
  for (const value of ['critical', 'alarm', 'error']) assert.equal(eventPresentation(value).tone, 'critical');
  assert.equal(eventPresentation('info').label, 'Информация');
  assert.equal(eventPresentation('new-type').tone, 'unknown');
  assert.equal(eventPresentation(null).tone, 'unknown');
});
