'use strict';
const base = 'http://127.0.0.1:17843';
const headers = {'X-Jarvis-Client': chrome.runtime.id};
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (!sender.tab || !sender.url?.startsWith('https://music.yandex.ru/') ||
      message?.type !== 'jarvis-poll') return;
  (async () => {
    try {
      const query = new URLSearchParams({tab:String(sender.tab.id),
        playing:message.playing ? '1':'0',active:sender.tab.active ? '1':'0'});
      const r = await fetch(base+'/poll?'+query,{headers,signal:AbortSignal.timeout(1500)});
      if (!r.ok) return respond({});
      const data = await r.json();
      respond(data);
    } catch (_) { respond({}); }
  })();
  return true;
});
chrome.runtime.onMessage.addListener((message,sender,respond) => {
  if (!sender.tab || !sender.url?.startsWith('https://music.yandex.ru/') ||
      message?.type !== 'jarvis-result') return;
  fetch(base+'/result',{method:'POST',headers:{...headers,'Content-Type':'application/json'},
    body:JSON.stringify({id:message.id,tab:String(sender.tab.id),ok:message.ok===true}),
    signal:AbortSignal.timeout(1500)}).then(()=>respond({})).catch(()=>respond({}));
  return true;
});
