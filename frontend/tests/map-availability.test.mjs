import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/map-availability.ts', import.meta.url), 'utf8');
const {outputText} = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}});
const {watchMapAvailability} = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);

function mapStub() {
  const listeners = new Map();
  return {
    ready: false,
    loaded() {return this.ready;},
    on(name, callback) {listeners.set(name, callback);},
    off(name, callback) {if (listeners.get(name) === callback) listeners.delete(name);},
    emit(name, event) {listeners.get(name)?.(event);},
    listeners,
  };
}

test('HTTP/style errors are reported regardless of message language and clear on recovery', () => {
  const map = mapStub();
  const states = [];
  const dispose = watchMapAvailability(map, failed => states.push(failed));
  map.emit('error', {error: new Error('HTTP 503')});
  map.emit('idle');
  assert.deepEqual(states, [true]);
  map.ready = true;
  map.emit('idle');
  assert.deepEqual(states, [true, false]);
  dispose();
  assert.equal(map.listeners.size, 0);
});

test('a stalled initial load becomes recoverable instead of loading forever', async () => {
  const map = mapStub();
  const states = [];
  const dispose = watchMapAvailability(map, failed => states.push(failed), 1);
  await new Promise(resolve => setTimeout(resolve, 20));
  assert.deepEqual(states, [true]);
  dispose();
});

test('a disposed attempt cannot change the replacement map state', async () => {
  const map = mapStub();
  const states = [];
  const dispose = watchMapAvailability(map, failed => states.push(failed), 1);
  const lateError = map.listeners.get('error');
  dispose();
  lateError();
  await new Promise(resolve => setTimeout(resolve, 20));
  assert.deepEqual(states, []);
});
