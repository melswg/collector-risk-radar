import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';
const source=await readFile(new URL('../src/critical-queue.ts',import.meta.url),'utf8');
const {outputText}=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}});
const {appendCritical}=await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
test('a second critical signal waits behind the visible one and survives its dismissal',()=>{
 const fire={id:'fire',notificationId:'n1'},flood={id:'flood',notificationId:'n2'};
 const queue=appendCritical(appendCritical([],fire),flood);
 assert.equal(queue[0],fire);
 assert.deepEqual(queue.slice(1),[flood]);
 assert.deepEqual(queue,[fire,flood]);
});
test('replayed notifications do not duplicate alerts, distinct notifications remain visible',()=>{
 const queue=appendCritical([],{id:'prediction',notificationId:'n1'});
 assert.equal(appendCritical(queue,{id:'prediction',notificationId:'n1'}),queue);
 assert.equal(appendCritical(queue,{id:'prediction',notificationId:'n2'}).length,2);
 assert.equal(appendCritical([{id:'demo'}],{id:'demo'}).length,1);
});
