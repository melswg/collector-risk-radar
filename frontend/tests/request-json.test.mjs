import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/request-json.ts', import.meta.url), 'utf8');
const {outputText} = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}});
const {requestJson} = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);

test('stalled reads stop with a recovery message instead of waiting forever', async t => {
  t.mock.method(globalThis, 'fetch', (_url, {signal}) => new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
  }));
  await assert.rejects(requestJson('/test', {method: 'GET'}, 5), /Повторите загрузку/);
});

test('HTML gateway failures have a useful message instead of a JSON parse error', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response('<html>Bad gateway</html>', {status: 502}));
  await assert.rejects(requestJson('/test', {}), /HTTP 502/);
});

test('structured validation failures preserve the service explanation', async t => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({error: {message: 'Укажите причину решения'}}, {status: 422}));
  await assert.rejects(requestJson('/test', {method: 'POST'}), /Укажите причину решения/);
});

test('long writes are not aborted by the read deadline', async t => {
  t.mock.method(globalThis, 'fetch', async (_url, {signal}) => {
    await new Promise(resolve => setTimeout(resolve, 15));
    assert.equal(signal.aborted, false);
    return Response.json({saved: true});
  });
  assert.deepEqual(await requestJson('/test', {method: 'POST'}, 1), {saved: true});
});

test('empty successful responses and successful JSON both work', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => new Response(null, {status: 204}));
  assert.equal(await requestJson('/test', {method: 'POST'}), null);
  fetch.mock.mockImplementation(async () => Response.json({items: []}));
  assert.deepEqual(await requestJson('/test', {}), {items: []});
});

test('an uncertain write result does not invite blind resubmission', async t => {
  t.mock.method(globalThis, 'fetch', async () => {throw new TypeError('Network failure');});
  await assert.rejects(requestJson('/test', {method: 'POST'}), /Проверьте результат действия/);
});
