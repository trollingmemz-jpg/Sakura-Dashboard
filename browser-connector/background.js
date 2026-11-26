const api=typeof browser!=="undefined"?browser:chrome;
let active=null;
api.runtime.onMessage.addListener((message,sender)=>{
 if(message.type!=="sakura-media"||!sender.tab)return;
 if(active!==null&&active!==sender.tab.id&&!message.data.playing)return;
 active=sender.tab.id;
 return (async()=>{
  const {token}=await api.storage.local.get("token");
  if(!token)return;
  try{
   const response=await fetch("http://127.0.0.1:8765/media",{method:"POST",headers:{"Authorization":"Bearer "+token,"Content-Type":"application/json"},body:JSON.stringify(message.data)});
   if(response.ok){const data=await response.json();if(data.command)await api.tabs.sendMessage(sender.tab.id,{command:data.command});}
  }catch(e){}
 })();
});
api.tabs.onRemoved.addListener(id=>{if(active===id)active=null;});

api.browserAction.onClicked.addListener(()=>api.tabs.create({url:api.runtime.getURL('popup.html')}));
