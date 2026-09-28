import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import ts from 'typescript';
const source=await readFile(new URL('../src/latest-request.ts',import.meta.url),'utf8');
const {outputText}=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}});
const {createLatestRequest}=await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);

test('a late result cannot replace the result of a more recent filter',async()=>{
 const begin=createLatestRequest();
 let oldResolve,newResolve,visible;
 const old=new Promise(resolve=>{oldResolve=resolve});
 const recent=new Promise(resolve=>{newResolve=resolve});
 async function load(promise){const current=begin();const data=await promise;if(current())visible=data}
 const first=load(old),second=load(recent);
 newResolve('new filter');await second;
 oldResolve('old filter');await first;
 assert.equal(visible,'new filter');
});

test('an old failure cannot cover a successfully refreshed view',async()=>{
 const begin=createLatestRequest();
 let fail,visible,error;
 async function load(promise){const current=begin();try{const data=await promise;if(current()){visible=data;error=undefined}}catch(e){if(current())error=e}}
 const old=load(new Promise((_resolve,reject)=>{fail=reject}));
 await load(Promise.resolve('fresh data'));
 fail(new Error('stale timeout'));await old;
 assert.equal(visible,'fresh data');assert.equal(error,undefined);
});
