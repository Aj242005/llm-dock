
// Presentation shell only. Screenshot runs load the page without ?present so the
// slides stay in plain document flow and element captures line up exactly.
const PRESENT = location.search.includes('present');
const slides=[...document.querySelectorAll('.slide')];
let i=0;
function fit(){
  if(!PRESENT) return;
  const s=Math.min(innerWidth/1920,(innerHeight-0)/1080);
  slides.forEach(el=>{el.style.transform=`translate(-50%,-50%) scale(${s})`;});
}
function show(n){
  if(!PRESENT) return;
  i=Math.max(0,Math.min(slides.length-1,n));
  slides.forEach((el,k)=>el.classList.toggle('on',k===i));
  location.hash=String(i+1);
}
if(PRESENT){
document.body.classList.add('app');
addEventListener('resize',fit);
addEventListener('keydown',e=>{
  if(['ArrowRight','ArrowDown',' ','PageDown','n'].includes(e.key)){show(i+1);e.preventDefault();}
  if(['ArrowLeft','ArrowUp','PageUp','p'].includes(e.key)){show(i-1);e.preventDefault();}
  if(e.key==='f'){document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen();}
  if(e.key==='Home'){show(0);} if(e.key==='End'){show(slides.length-1);}
});
fit();
show((parseInt(location.hash.replace('#',''))||1)-1);
}
