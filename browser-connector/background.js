const api=browser;
const endpoint="http://127.0.0.1:8770";
function request(path,method,token,data){
 return new Promise((resolve,reject)=>{
  const x=new XMLHttpRequest();
  x.open(method,endpoint+path,true);
  x.timeout=5000;
  x.setRequestHeader("Authorization","Bearer "+(token||""));
  if(data)x.setRequestHeader("Content-Type","application/json");
  x.onload=()=>resolve({ok:x.status>=200&&x.status<300,status:x.status,json:async()=>JSON.parse(x.responseText)});
  x.onerror=()=>reject(new Error("Loopback request blocked or unavailable"));
  x.ontimeout=()=>reject(new Error("Loopback request timed out"));
  x.send(data?JSON.stringify(data):null);
 });
}
async function diagnostic(status){await api.storage.local.set({diagnostic:status,diagnosticTime:Date.now()});}
api.runtime.onMessage.addListener((message,sender)=>{
 if(message.type==="sakura-test")return (async()=>{
  try{const {token}=await api.storage.local.get("token");const granted=await api.permissions.contains({origins:["http://127.0.0.1/*"]});if(!granted)return {status:"Loopback permission missing — reinstall connector ZIP"};const r=await request("/health","GET",token);return r.ok?{status:(await r.json()).enabled?"Connected — tracking enabled":"Connected — enable tracking in Sakura"}:{status:"Pairing rejected (HTTP "+r.status+")"};}catch(e){return {status:"Cannot reach Sakura on port 8770: "+e.message};}
 })();
 if(!sender.tab)return;
 if(message.type==="sakura-diagnostic"){if(sender.frameId===0)return diagnostic(message.status);return;}
 if(message.type!=="sakura-media")return;
 return (async()=>{
  const {token}=await api.storage.local.get("token");
  if(!token){await diagnostic("Pairing code missing");return;}
  try{
   const r=await request("/media","POST",token,message.data);
   await diagnostic(r.ok?"Playback report accepted":"Playback rejected (HTTP "+r.status+")");
   if(r.ok){const d=await r.json();if(d.command)await api.tabs.sendMessage(sender.tab.id,{command:d.command},{frameId:sender.frameId});}
  }catch(e){await diagnostic("Connection failed: "+e.message);}
 })();
});
api.browserAction.onClicked.addListener(()=>api.tabs.create({url:api.runtime.getURL("popup.html")}));
