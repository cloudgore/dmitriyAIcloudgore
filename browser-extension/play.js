(() => {
  'use strict';
  const url = new URL(location.href);
  if (url.searchParams.get('jarvis_play') !== '1') return;
  // One attempt per explicitly marked navigation. No network, storage, or bridge.
  url.searchParams.delete('jarvis_play');
  url.searchParams.delete('jarvis_request');
  history.replaceState(history.state, '', url.href);

  const playText = /(?:воспроизвести|играть|включить|запустить|\bplay\b)/i;
  const pauseText = /(?:приостановить|пауза|остановить|\bpause\b)/i;
  let done = false;
  let tries = 0;
  let clicked = false;
  const notice = (text) => {
    const node = document.createElement('div');
    node.textContent = 'Джарвис: ' + text;
    Object.assign(node.style, {position:'fixed', bottom:'18px', right:'18px', zIndex:'2147483647',
      background:'#162737', color:'#fff', padding:'14px 18px', borderRadius:'12px',
      maxWidth:'360px', font:'15px sans-serif', boxShadow:'0 4px 24px #0008'});
    document.documentElement.append(node);
    setTimeout(() => node.remove(), 12000);
  };
  function candidate(button) {
    const rect = button.getBoundingClientRect();
    const style = getComputedStyle(button);
    if (rect.width < 25 || rect.height < 25 || style.visibility === 'hidden' ||
        style.display === 'none' || style.opacity === '0' || button.disabled ||
        button.getAttribute('aria-disabled') === 'true') return null;
    const label = [button.getAttribute('aria-label'), button.title,
      button.getAttribute('data-test-id'), button.innerText].filter(Boolean).join(' ');
    const icons = [...button.querySelectorAll('use')].map(x => x.getAttribute('href') ||
      x.getAttribute('xlink:href') || '').join(' ');
    const inPlayer = !!button.closest('[class*="PlayerBar"], [data-test-id*="PLAYER"], [class*="MyWave"]');
    const className = typeof button.className === 'string' ? button.className : '';
    const isControl = /play.?button|pause.?button/i.test(className) ||
      /(?:PLAY|PAUSE).*BUTTON/i.test(button.getAttribute('data-test-id') || '');
    const pausedIcon = /(?:^|[#_/-])pause(?:$|[_/-])/i.test(icons);
    const playing = pauseText.test(label) || pausedIcon;
    const playable = playText.test(label) || /(?:^|[#_/-])play(?:$|[_/-])/i.test(icons);
    if (!playing && !playable) return null; // Never guess a button from coordinates.
    let score = inPlayer ? 100 : 0;
    if (isControl) score += 30;
    if (rect.width >= 45 && rect.height >= 45) score += 10;
    return {button, score, playing};
  }
  function attempt() {
    if (done) return;
    tries++;
    const controls = [...document.querySelectorAll('button,[role="button"]')]
      .map(candidate).filter(Boolean).sort((a,b) => b.score-a.score);
    const best = controls[0];
    if (best && best.score >= 30 && (!controls[1] || best.score > controls[1].score)) {
      if (best.playing) {
        done = true;
        clearInterval(timer);
        notice(clicked ? 'музыка включена.' : 'музыка уже играет.');
      } else if (!clicked) {
        clicked = true;
        best.button.click();
      }
    }
    if (tries >= 50) {
      done = true;
      clearInterval(timer);
      notice(clicked ? 'кнопка нажата. Если звука нет, проверьте разрешение воспроизведения в браузере.' :
        'не удалось однозначно найти кнопку «Играть». Нажмите её вручную.');
    }
  }
  const timer = setInterval(attempt, 500);
  attempt();
})();
