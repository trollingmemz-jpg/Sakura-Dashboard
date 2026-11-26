const api=typeof browser!=="undefined"?browser:chrome;
function video(){return [...document.querySelectorAll("video")].sort((a,b)=>Number(b.videoWidth*b.videoHeight)-Number(a.videoWidth*a.videoHeight))[0];}
function report(){
 const v=video();if(!v)return;
 const meta=navigator.mediaSession?.metadata;
 const title=meta?.title||document.querySelector('meta[property="og:title"]')?.content||document.title;
 const episode=(document.title.match(/(?:episode|ep\.?)[\s:-]*\d+(?:\.\d+)?/i)||[])[0]||"";
 api.runtime.sendMessage({type:"sakura-media",data:{title,episode,artist:meta?.artist||"",source:"Miruro",playing:!v.paused&&!v.ended,position:Number.isFinite(v.currentTime)?v.currentTime:0,duration:Number.isFinite(v.duration)?v.duration:0}}).catch(()=>{});
}
setInterval(report,2000);
api.runtime.onMessage.addListener(({command})=>{const v=video();if(!v)return;if(command==="pause"||(command==="toggle"&&!v.paused))v.pause();else if(command==="play"||command==="toggle")v.play().catch(()=>{});});
