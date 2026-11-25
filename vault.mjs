// Optional device vault. Only ciphertext is persisted; no automatic unlock.
const ITERATIONS=600000;
const utf8=new TextEncoder();
const b64=bytes=>btoa(String.fromCharCode(...bytes));
function bytes(value,max){
 if(typeof value!=="string"||value.length>max*2||!/^[A-Za-z0-9+/]+={0,2}$/.test(value))throw Error("Invalid saved vault");
 const b=Uint8Array.from(atob(value),x=>x.charCodeAt(0));if(b.length>max)throw Error("Invalid saved vault");return b;
}
function pass(value){
 if(typeof value!=="string"||value.length<12||value.length>256)throw Error("Choose a separate unlock passphrase of 12–256 characters.");
 return value;
}
function validate(v){
 if(!v||typeof v.repo!=="string"||!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(v.repo)||v.repo.length>200||typeof v.token!=="string"||!/^github_pat_[A-Za-z0-9_]+$/.test(v.token)||v.token.length>512||!["main","v2-core-development"].includes(v.branch))throw Error("Invalid workspace credential.");
 return {repo:v.repo,token:v.token,branch:v.branch};
}
async function key(password,salt){
 const material=await crypto.subtle.importKey("raw",utf8.encode(pass(password)),"PBKDF2",false,["deriveKey"]);
 return crypto.subtle.deriveKey({name:"PBKDF2",hash:"SHA-256",salt,iterations:ITERATIONS},material,{name:"AES-GCM",length:256},false,["encrypt","decrypt"]);
}
const aad=utf8.encode("PostForge AI mobile device vault v1");
async function sealRecord(credential,password,context){
 const salt=crypto.getRandomValues(new Uint8Array(16)),iv=crypto.getRandomValues(new Uint8Array(12));
 const cipher=await crypto.subtle.encrypt({name:"AES-GCM",iv,additionalData:context},await key(password,salt),utf8.encode(JSON.stringify(credential)));
 return JSON.stringify({version:1,salt:b64(salt),iv:b64(iv),cipher:b64(new Uint8Array(cipher))});
}
async function unsealRecord(record,password,context,validator){
 try{
  if(typeof record!=="string"||record.length>4096)throw Error();
  const v=JSON.parse(record);if(v.version!==1)throw Error();
  const salt=bytes(v.salt,16),iv=bytes(v.iv,12),cipher=bytes(v.cipher,2048);if(salt.length!==16||iv.length!==12||cipher.length<16)throw Error();
  const clear=await crypto.subtle.decrypt({name:"AES-GCM",iv,additionalData:context},await key(password,salt),cipher);
  return validator(JSON.parse(new TextDecoder("utf-8",{fatal:true}).decode(clear)));
 }catch{throw Error("Cannot unlock saved workspace. Check the passphrase or forget the saved connection.");}
}

export const EDIT_MINUTES=Object.freeze([15,30,60,480,1440,10080,20160,43200]);
export function editDeadline(minutes,now=Date.now()){
 if(!EDIT_MINUTES.includes(minutes)||!Number.isSafeInteger(now)||now<0)throw Error("Choose an editing duration from 15 minutes to 30 days.");
 return now+minutes*60000;
}
export function remainingEdit(deadline,now=Date.now()){
 return Number.isSafeInteger(deadline)&&Number.isSafeInteger(now)?Math.max(0,deadline-now):0;
}
const editAad=utf8.encode("PostForge AI mobile editing vault v1");
function validateEdit(v,now){
 const credential=validate(v);
 if(credential.branch!=="main"||!Number.isSafeInteger(v.createdAt)||v.createdAt>now||v.expiresAt!==editDeadline(v.minutes,v.createdAt)||!remainingEdit(v.expiresAt,now))throw Error("Saved editing authorization has expired or is invalid.");
 return {...credential,createdAt:v.createdAt,expiresAt:v.expiresAt,minutes:v.minutes};
}
export async function seal(value,password){return sealRecord(validate(value),password,aad);}
export async function unseal(record,password){return unsealRecord(record,password,aad,validate);}
export async function sealEditing(value,password,now=Date.now()){
 return sealRecord(validateEdit(value,now),password,editAad);
}
export async function unsealEditing(record,password,repo,now=Date.now()){
 const v=await unsealRecord(record,password,editAad,x=>x);
 const credential=validateEdit(v,now);
 if(credential.repo!==repo)throw Error("Saved editing authorization belongs to another workspace.");
 return credential;
}
