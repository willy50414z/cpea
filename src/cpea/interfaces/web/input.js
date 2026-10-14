() => {
  const ERROR = "執行錯誤請再試一次";
  let composing = false;
  let busy = false;
  let latestQuestion = "";
  const question = (target) => target?.closest?.("#cpea-question");
  const panel = document.querySelector("#cpea-transport");

  function transportError() {
    busy = false;
    panel.hidden = false;
    panel.querySelector(".question").textContent = latestQuestion;
    panel.querySelector(".question").hidden = !("cpeaPending" in document.documentElement.dataset);
    panel.querySelector(".error").textContent = ERROR;
    const input = document.querySelector("#cpea-question textarea");
    if (input) input.disabled = false;
    const submit = document.querySelector("#cpea-submit");
    if (submit) submit.disabled = false;
  }

  // Observe Gradio's transport without taking over its event protocol.
  const fetchOriginal = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const url = new URL(args[0]?.url ?? args[0], window.location.href);
    const queued = url.pathname.includes("/gradio_api/queue/");
    let response;
    try {
      response = await fetchOriginal(...args);
    } catch (error) {
      if (queued && busy) transportError();
      throw error;
    }
    if (queued && !response.ok && busy) transportError();
    if (!queued || !url.pathname.endsWith("/data") || !response.body) return response;

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let completed = false;
    const body = new ReadableStream({
      async pull(controller) {
        try {
          const { value, done } = await reader.read();
          if (done) {
            if (busy && !completed) transportError();
            controller.close();
            return;
          }
          buffer += decoder.decode(value, { stream: true });
          let boundary;
          while ((boundary = buffer.indexOf("\n\n")) !== -1) {
            const frame = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            const data = frame.match(/^data: ?(.+)$/m);
            if (!data) continue;
            const message = JSON.parse(data[1]);
            if (message.msg === "process_starts") completed = false;
            if (message.msg === "process_completed") {
              completed = true;
              if (message.success === false && busy) transportError();
              busy = false;
            }
          }
          controller.enqueue(value);
        } catch (error) {
          if (busy) transportError();
          controller.error(error);
        }
      },
      cancel(reason) { return reader.cancel(reason); }
    });
    return new Response(body, { status: response.status, headers: response.headers });
  };

  document.addEventListener("compositionstart", (event) => {
    if (question(event.target)) composing = true;
  }, true);
  document.addEventListener("compositionend", (event) => {
    if (question(event.target)) composing = false;
  }, true);
  document.addEventListener("keydown", (event) => {
    if (!question(event.target) || event.key !== "Enter") return;
    event.stopImmediatePropagation();
    if (composing || event.isComposing || event.keyCode === 229 || event.shiftKey) return;
    event.preventDefault();
    if (!event.target.disabled && event.target.value.trim())
      document.querySelector("#cpea-submit")?.click();
  }, true);
  document.addEventListener("click", (event) => {
    if (!event.target.closest?.("#cpea-submit")) return;
    const input = document.querySelector("#cpea-question textarea");
    if (!input || busy || input.disabled || !input.value.trim()) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    busy = true;
    latestQuestion = input.value;
    panel.hidden = false;
    panel.querySelector(".question").textContent = latestQuestion;
    panel.querySelector(".question").hidden = false;
    panel.querySelector(".error").textContent = "產生 SQL 中…";
    document.documentElement.dataset.cpeaPending = "";
  }, true);

  const chat = document.querySelector("#cpea-chat");
  chat?.setAttribute("aria-live", "polite");
  chat?.setAttribute("aria-relevant", "additions text");
  // Clear stale content immediately; reveal Gradio's new question when it arrives.
  new MutationObserver(() => {
    const current = chat?.querySelector("[data-testid=user] .message-content")?.textContent;
    if (current?.trim() === latestQuestion.trim()) {
      delete document.documentElement.dataset.cpeaPending;
      if (panel.querySelector(".error").textContent !== ERROR) panel.hidden = true;
    }
  }).observe(chat, { childList: true, subtree: true, characterData: true });
}
