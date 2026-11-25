import test from "node:test";
import assert from "node:assert/strict";
import {seal,unseal,sealEditing,unsealEditing,editDeadline,remainingEdit,EDIT_MINUTES} from "../docs/mobile/vault.mjs";
const credential={repo:"example/private",token:"github_pat_fixture_only",branch:"main"};
const password="a unique strong test phrase";
test("vault round trip, random salt and IV, no clear credentials",async()=>{
 const a=await seal(credential,password),b=await seal(credential,password);
 assert.notEqual(a,b);assert.ok(!a.includes(credential.token));assert.ok(!a.includes(credential.repo));assert.ok(!a.includes(password));
 assert.deepEqual(await unseal(a,password),credential);
});
test("wrong passphrase and tampered ciphertext fail closed",async()=>{
 const a=await seal(credential,password);
 await assert.rejects(unseal(a,"wrong passphrase entirely"),/Cannot unlock/);
 const record=JSON.parse(a);record.cipher=(record.cipher[0]==="A"?"B":"A")+record.cipher.slice(1);
 await assert.rejects(unseal(JSON.stringify(record),password),/Cannot unlock/);
});
test("invalid credential and short passphrase rejected",async()=>{
 await assert.rejects(seal(credential,"short"),/passphrase/);
 await assert.rejects(seal({...credential,token:"linkedin"},password),/credential/);
 await assert.rejects(unseal("{}",password),/Cannot unlock/);
});
test("editing durations are bounded and 30 days does not overflow the deadline",()=>{
 const now=Date.parse("2026-11-24T00:00:00Z");
 for(const minutes of EDIT_MINUTES)assert.equal(editDeadline(minutes,now)-now,minutes*60000);
 assert.equal(remainingEdit(editDeadline(43200,now),now),2592000000);
 for(const minutes of [0,14,43201,Infinity,NaN,"15"])assert.throws(()=>editDeadline(minutes,now),/duration/);
 assert.equal(remainingEdit(now,now),0);
});
test("saved editing authorization is encrypted, bound to workspace and original expiry",async()=>{
 const now=Date.now(),edit={...credential,createdAt:now,minutes:43200,expiresAt:editDeadline(43200,now)};
 const record=await sealEditing(edit,password,now);
 assert.ok(!record.includes(edit.token));assert.ok(!record.includes(edit.repo));
 assert.deepEqual(await unsealEditing(record,password,edit.repo,now+60000),edit);
 await assert.rejects(unsealEditing(record,password,"other/private",now),/another workspace/);
 await assert.rejects(unsealEditing(record,password,edit.repo,edit.expiresAt),/expired/);
 await assert.rejects(unsealEditing(record,"incorrect passphrase",edit.repo,now),/Cannot unlock/);
 await assert.rejects(unseal(record,password),/Cannot unlock/);
 await assert.rejects(unsealEditing(await seal(credential,password),password,edit.repo,now),/Cannot unlock/);
 await assert.rejects(sealEditing({...edit,expiresAt:edit.expiresAt+1},password,now),/invalid/);
});
