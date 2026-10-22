() => {
  let composing = false;
  let epoch = 0;
  let busy = false;
  let outcomeUnknown = false;
  const versions = new Map();
  const mainEvents = new Set();
  let submitIntent = false;
  const question = target => target?.closest?.('#cpea-question');
  const panel = document.querySelector('#cpea-transport');
  function unknown() {
    outcomeUnknown = true;
    document.documentElement.dataset.cpeaUnknown = '';
    panel.dataset.outcome = 'unknown';
    const abandon = document.querySelector('#cpea-abandon');
    if (abandon) { abandon.style.setProperty('display', 'block', 'important'); abandon.disabled = false; }
    panel.hidden = false;
    panel.querySelector('.error').textContent = '無法確認處理結果；舊請求可能仍完成。請勿重送確認。';
    document.querySelectorAll('#cpea-conversation button, #cpea-question textarea, #cpea-project input, #cpea-assistant-confirmation input')
      .forEach(element => { if (!element.closest('#cpea-abandon')) element.disabled = true; });
  }
  const original = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const url = new URL(args[0]?.url ?? args[0], location.href);
    const queued = url.pathname.includes('/gradio_api/queue/');
    const submittedEpoch = epoch;
    const mainJoin = queued && url.pathname.endsWith("/join") && submitIntent;
    if (mainJoin) submitIntent = false;
    let response;
    try { response = await original(...args); }
    catch (error) { if (queued && busy && submittedEpoch === epoch) unknown(); throw error; }
    if (queued && !response.ok && busy && submittedEpoch === epoch) unknown();
    if (queued && url.pathname.endsWith('/join') && response.ok) {
      const data = await response.clone().json();
      if (data.event_id) {
        versions.set(data.event_id, submittedEpoch);
        if (mainJoin) mainEvents.add(data.event_id);
      }
    }
    if (!queued || !url.pathname.endsWith('/data') || !response.body) return response;
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    const encoder = new TextEncoder();
    let buffer = '';
    const body = new ReadableStream({
      async pull(controller) {
        try {
          const {value, done} = await reader.read();
          if (done) {
            if (busy) unknown();
            controller.close();
            return;
          }
          buffer += decoder.decode(value, {stream: true});
          let boundary;
          let deliver = '';
          while ((boundary = buffer.indexOf('\n\n')) !== -1) {
            const frame = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            const data = frame.match(/^data: ?(.+)$/m);
            if (!data) { deliver += frame + '\n\n'; continue; }
            const message = JSON.parse(data[1]);
            const version = versions.get(message.event_id);
            if (version !== undefined && version !== epoch) {
              if (message.msg === 'process_completed') { versions.delete(message.event_id); mainEvents.delete(message.event_id); }
              continue;
            }
            if (message.msg === 'process_completed') {
              if (message.success === false && busy) unknown();
              if (mainEvents.has(message.event_id)) busy = false;
              mainEvents.delete(message.event_id);
              versions.delete(message.event_id);
            }
            // Once outcome is unknown, only a new explicitly detached epoch may
            // update the screen. Never replay a confirmation automatically.
            if (outcomeUnknown) continue;
            deliver += frame + '\n\n';
          }
          controller.enqueue(encoder.encode(deliver));
        } catch (error) {
          if (busy) unknown();
          controller.error(error);
        }
      },
      cancel(reason) { return reader.cancel(reason); }
    });
    return new Response(body, {status: response.status, headers: response.headers});
  };
  document.addEventListener('compositionstart', event => { if (question(event.target)) composing = true; }, true);
  document.addEventListener('compositionend', event => { if (question(event.target)) composing = false; }, true);
  document.addEventListener('keydown', event => {
    const radio = event.target.closest?.('#cpea-assistant-confirmation input[type=radio]');
    if (radio && ['ArrowDown', 'ArrowRight', 'ArrowUp', 'ArrowLeft', 'Home', 'End'].includes(event.key)) {
      if (outcomeUnknown || radio.disabled) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const radios = [...radio.closest('fieldset').querySelectorAll('input[type=radio]')].filter(e => !e.disabled);
      const index = radios.indexOf(radio);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? radios.length - 1 :
        (index + (['ArrowDown', 'ArrowRight'].includes(event.key) ? 1 : -1) + radios.length) % radios.length;
      radios[next]?.focus();
      radios[next]?.click();
      return;
    }
    if (!question(event.target) || event.key !== 'Enter') return;
    event.stopImmediatePropagation();
    if (composing || event.isComposing || event.keyCode === 229 || event.shiftKey) return;
    event.preventDefault();
    if (!event.target.disabled && event.target.value.trim()) document.querySelector('#cpea-submit')?.click();
  }, true);
  document.addEventListener('click', event => {
    if (event.target.closest?.('#cpea-abandon')) {
      epoch += 1;
      busy = true;
      submitIntent = true;
      // This button was disabled directly during transport failure; Gradio's
      // unchanged interactive prop would otherwise leave its DOM disabled.
      const newQuestion = document.querySelector('#cpea-new');
      if (newQuestion) newQuestion.disabled = false;
      outcomeUnknown = false;
      delete panel.dataset.outcome;
      document.querySelector('#cpea-abandon').style.removeProperty('display');
      delete document.documentElement.dataset.cpeaUnknown;
      panel.hidden = true;
      return;
    }
    const submit = event.target.closest?.('#cpea-submit');
    const confirm = event.target.closest?.('.cpea-confirm, .cpea-cancel, #cpea-new');
    if (!submit && !confirm) return;
    const input = document.querySelector('#cpea-question textarea');
    if (busy || outcomeUnknown || (submit && (!input?.value.trim() || input.disabled))) {
      event.preventDefault(); event.stopImmediatePropagation(); return;
    }
    if (submit) epoch += 1;
    busy = true;
    submitIntent = true;
  }, true);
  const chat = document.querySelector('#cpea-chat');
  chat?.setAttribute('aria-live', 'polite');
  const thread = document.querySelector('#cpea-thread');
  let followProgress = true;
  thread?.addEventListener('scroll', () => {
    followProgress = thread.scrollHeight - thread.clientHeight - thread.scrollTop < 72;
  }, {passive: true});
  let previous = 'idle';
  let pendingFocus = false;
  new MutationObserver(() => {
    const state = document.querySelector('[data-cpea-state]')?.dataset.cpeaState;
    if (state !== previous) {
      if (state === 'generating' || state === 'resuming') followProgress = true;
      previous = state;
      pendingFocus = state === 'waiting_confirmation';
      if (state === 'editing' && !outcomeUnknown) {
        document.querySelector('#cpea-question textarea')?.focus();
      }
    }
    document.querySelectorAll('#cpea-assistant-confirmation fieldset').forEach(group => {
      const radios = [...group.querySelectorAll('input[type=radio]')];
      if (!radios.length) return;
      if (group.getAttribute('role') !== 'radiogroup') group.setAttribute('role', 'radiogroup');
      const label = group.querySelector('[data-testid=block-info]')?.textContent?.trim() || '欄位對應確認';
      if (group.getAttribute('aria-label') !== label) group.setAttribute('aria-label', label);
      const current = radios.find(radio => radio.checked) || radios[0];
      radios.forEach(radio => {
        const tabIndex = radio === current ? 0 : -1;
        if (radio.tabIndex !== tabIndex) radio.tabIndex = tabIndex;
      });
    });
    if (pendingFocus && !outcomeUnknown) {
      const first = document.querySelector('#cpea-assistant-confirmation input[type=radio]');
      if (first) { pendingFocus = false; first.focus(); }
    }
    if (followProgress && !outcomeUnknown && ['generating', 'resuming', 'executing', 'completed'].includes(state)) {
      thread.scrollTop = thread.scrollHeight;
    }
  }).observe(document.querySelector('#cpea-conversation'), {subtree: true, childList: true, attributes: true});
}
