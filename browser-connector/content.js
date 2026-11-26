const api=browser;
function report(){
 if(document.hidden)return;
 const diag=status=>api.runtime.sendMessage({type:'sakura-diagnostic',status}).catch(()=>{});
 let page=location;try{page=window.top.location;}catch(e){}
 const url=page.origin+page.pathname;
 const meta=navigator.mediaSession?.metadata;
 let title=meta?.title||document.querySelector('meta[property="og:title"]')?.content||document.title;
 if(location.hostname==="mangadex.org"){
  if(!/^\/chapter\//.test(location.pathname))return;
  const heading=document.title;
  const part=(heading.match(/(?:chapter|ch\.?)\s*[\d.]+/i)||[])[0];
  if(!part)return;
  title=heading.replace(part,"").replace(/\s*[-|]\s*MangaDex.*$/i,"").trim();
  const page=Number(location.pathname.split("/")[3])||0;
  api.runtime.sendMessage({type:"sakura-media",data:{url,title,episode:part,position:page,duration:0,playing:false}}).catch(()=>{});
  return;
 }
 const v=[...document.querySelectorAll("video")].sort((a,b)=>b.videoWidth*b.videoHeight-a.videoWidth*a.videoHeight)[0];
 if(!v){diag('Miruro detected — no accessible video element; embedded frames: '+document.querySelectorAll('iframe').length);return;}
 if(v.currentTime<3){diag('Video detected — waiting for playback');return;}
 const part=((document.title+' '+(document.querySelector('h1')?.textContent||'')+' '+(document.querySelector('h2')?.textContent||'')).match(/(?:episode|ep\.?)[\s:-]*\d+(?:\.\d+)?/i)||[])[0]|| (new URLSearchParams(page.search).get("episode") ? "Episode "+new URLSearchParams(location.search).get("episode") : "");
 if(!part){diag('Video detected — episode metadata missing');return;}
 title=title.replace(part,"").replace(/\s*[-|]\s*Miruro.*$/i,"").trim();
 api.runtime.sendMessage({type:"sakura-media",data:{url,title,episode:part,playing:!v.paused&&!v.ended,position:Number.isFinite(v.currentTime)?v.currentTime:0,duration:Number.isFinite(v.duration)?v.duration:0}}).catch(()=>{});
}
setInterval(report,2000);
api.runtime.onMessage.addListener(({command})=>{const v=document.querySelector("video");if(!v)return;if(command==="pause"||(command==="toggle"&&!v.paused))v.pause();else if(command==="play"||command==="toggle")v.play().catch(()=>{});});
