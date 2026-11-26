const api=browser;
const endpoint="http://127.0.0.1:8770";
async function diagnostic(status){await api.storage.local.set({diagnostic:status,diagnosticTime:Date.now()});}
api.runtime.onMessage.addListener((message,sender)=>{
 if(message.type==="sakura-test")return (async()=>{
  try{const {token}=await api.storage.local.get("token");const r=await fetch(endpoint+"/health",{headers:{Authorization:"Bearer "+(token||"")}});return r.ok?{status:(await r.json()).enabled?"Connected — tracking enabled":"Connected — enable tracking in Sakura"}:{status:"Pairing rejected (HTTP "+r.status+")"};}catch(e){return {status:"Cannot reach Sakura on port 8770: "+e.message};}
 })();
 if(!sender.tab)return;
 if(message.type==="sakura-diagnostic"){if(sender.frameId===0)return diagnostic(message.status);return;}
 if(message.type!=="sakura-media")return;
 return (async()=>{
  const {token}=await api.storage.local.get("token");
  if(!token){await diagnostic("Pairing code missing");return;}
  try{
   const r=await fetch(endpoint+"/media",{method:"POST",headers:{Authorization:"Bearer "+token,"Content-Type":"application/json"},body:JSON.stringify(message.data)});
   await diagnostic(r.ok?"Playback report accepted":"Playback rejected (HTTP "+r.status+")");
   if(r.ok){const d=await r.json();if(d.command)await api.tabs.sendMessage(sender.tab.id,{command:d.command},{frameId:sender.frameId});}
  }catch(e){await diagnostic("Connection failed: "+e.message);}
 })();
});
api.browserAction.onClicked.addListener(()=>api.tabs.create({url:api.runtime.getURL("popup.html")}));
