(() => {
  'use strict';
  const allowed = new Set(['play','pause','next','previous','play_pause']);
  let polling = false;
  const seen = new Set();
  function pick(action) {
    const choices = [...document.querySelectorAll('button,[role="button"]')].map(button => {
      const rect=button.getBoundingClientRect(), style=getComputedStyle(button);
      if(rect.width<20 || rect.height<20 || style.display==='none' || style.visibility==='hidden' ||
         style.opacity==='0' || button.disabled || button.getAttribute('aria-disabled')==='true') return null;
      const label=[button.getAttribute('aria-label'),button.title,button.getAttribute('data-test-id'),button.innerText,
        ...[...button.querySelectorAll('use')].map(x=>x.getAttribute('href')||x.getAttribute('xlink:href'))].filter(Boolean).join(' ');
      const classes=typeof button.className==='string'?button.className:'';
      const inPlayer=!!button.closest('[class*="PlayerBar"], [data-test-id*="PLAYER"], [class*="MyWave"]');
      const isPause=/(?:пауза|приостанов|остановить|\bpause\b|[#_/-]pause(?:$|[_/-])|PauseButton)/i.test(label);
      const isPlay=/(?:играть|воспроизве|продолжить|\bplay\b|[#_/-]play(?:$|[_/-])|PlayButton)/i.test(label);
      if(action==='next' && !/(?:следующ|\bnext\b|next.?track|next.?button)/i.test(label+' '+classes)) return null;
      if(action==='previous' && !/(?:предыдущ|\bprevious\b|\bprev\b|prev.*button)/i.test(label+' '+classes)) return null;
      if(!['next','previous'].includes(action) && !isPause && !isPlay) return null;
      const control=/(?:play|pause|next|prev).*button|(?:PLAY|PAUSE|NEXT|PREVIOUS).*BUTTON/i.test(label+' '+classes);
      const score=(inPlayer?100:0)+(control?30:0)+(rect.width>=45&&rect.height>=45?10:0);
      return {button,score,playing:isPause};
    }).filter(Boolean).sort((a,b)=>b.score-a.score);
    if(!choices[0] || choices[0].score<30 || (choices[1]&&choices[0].score===choices[1].score)) return null;
    return choices[0];
  }
  async function perform(action) {
    if(!allowed.has(action)) return false;
    const target=pick(action);
    if(!target) return false;
    if(action==='pause' && !target.playing) return true;
    if(action==='play' && target.playing) return true;
    target.button.click();
    if(action==='next'||action==='previous'||action==='play_pause') return true;
    for(let i=0;i<8;i++) {
      await new Promise(resolve=>setTimeout(resolve,200));
      const state=pick(action);
      if(state && state.playing===(action==='play')) return true;
    }
    return false;
  }
  async function poll() {
    if(polling) return;
    polling=true;
    try {
      const state=pick('play');
      const data=await chrome.runtime.sendMessage({type:'jarvis-poll',playing:!!state?.playing});
      if(data?.id && allowed.has(data.action) && !seen.has(data.id)) {
        seen.add(data.id);
        if(seen.size>32) seen.delete(seen.values().next().value);
        const ok=await perform(data.action);
        await chrome.runtime.sendMessage({type:'jarvis-result',id:data.id,ok});
      }
    } catch (_) { /* Assistant stopped or extension was reloaded. */ }
    finally { polling=false; }
  }
  setInterval(poll,400);
  poll();
})();
