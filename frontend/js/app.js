/* Wiring: session id, form submit, report rendering. */

(() => {
  const SESSION_KEY = "research-agent-session";

  function newSessionId() {
    // crypto.randomUUID needs a secure context; localhost qualifies, but keep a
    // fallback so the page still works if it is served some other way.
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return `s-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  let sessionId;
  try {
    sessionId = sessionStorage.getItem(SESSION_KEY) || newSessionId();
    sessionStorage.setItem(SESSION_KEY, sessionId);
  } catch (err) {
    sessionId = newSessionId(); // private mode / storage blocked
  }

  const el = {
    sessionLabel: document.getElementById("session-label"),
    modelChip: document.getElementById("model-chip"),
    resetBtn: document.getElementById("reset-btn"),
    form: document.getElementById("research-form"),
    topic: document.getElementById("topic"),
    topicError: document.getElementById("topic-error"),
    startBtn: document.getElementById("start-btn"),
    stopBtn: document.getElementById("stop-btn"),
    reportSection: document.getElementById("report-section"),
    reportBody: document.getElementById("report-body"),
    reportStatus: document.getElementById("report-status"),
    copyBtn: document.getElementById("copy-btn"),
    downloadBtn: document.getElementById("download-btn"),
  };

  el.sessionLabel.textContent = sessionId.slice(0, 8);

  let lastReport = "";
  let currentTopic = "";

  /* ---------------------------------------------------------------- health */

  fetch("/api/health")
    .then((r) => r.json())
    .then((data) => {
      el.modelChip.className = data.api_key_configured ? "chip chip-accent" : "chip chip-danger";
      el.modelChip.textContent = data.api_key_configured ? data.chat_model : "No API key";
    })
    .catch(() => {
      el.modelChip.className = "chip chip-danger";
      el.modelChip.textContent = "Backend offline";
    });

  /* ---------------------------------------------------------------- report */

  /* `approved` comes from the graph rather than being inferred from the report's
     text, so a report that merely happens to open with a blockquote is not
     mislabelled. */
  function showReport(markdown, approved, scroll) {
    lastReport = markdown;
    el.reportBody.innerHTML = marked.parse(markdown);
    el.reportStatus.textContent = approved ? "Approved by the Critic" : "Finalized with open gaps";
    el.reportSection.classList.remove("hidden");
    if (scroll) el.reportSection.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderReport(markdown, approved) {
    showReport(markdown, approved, true);
    SessionHistory.upsert({ id: sessionId, topic: currentTopic, report: markdown, approved });
  }

  el.copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(lastReport);
      el.copyBtn.textContent = "Copied";
      setTimeout(() => (el.copyBtn.textContent = "Copy markdown"), 1600);
    } catch (err) {
      el.copyBtn.textContent = "Copy failed";
      setTimeout(() => (el.copyBtn.textContent = "Copy markdown"), 1600);
    }
  });

  el.downloadBtn.addEventListener("click", () => {
    const blob = new Blob([lastReport], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "research-report.md";
    a.click();
    URL.revokeObjectURL(url);
  });

  /* ------------------------------------------------------------------- run */

  /* The topic box grows with what is typed instead of scrolling inside a fixed
     four-row well, capped at half the viewport so it never pushes the button
     off screen. */
  function autosizeTopic() {
    el.topic.style.height = "auto";
    const cap = Math.round(window.innerHeight * 0.5);
    const wanted = el.topic.scrollHeight;
    el.topic.style.height = `${Math.min(wanted, cap)}px`;
    el.topic.style.overflowY = wanted > cap ? "auto" : "hidden";
  }

  el.topic.addEventListener("input", autosizeTopic);
  window.addEventListener("resize", autosizeTopic);
  autosizeTopic();

  function setRunning(running) {
    el.startBtn.disabled = running;
    el.startBtn.textContent = running ? "Researching…" : "Start research";
    el.stopBtn.classList.toggle("hidden", !running);
    el.topic.disabled = running;
  }

  el.form.addEventListener("submit", (e) => {
    e.preventDefault();
    const topic = el.topic.value.trim();
    if (!topic) {
      el.topicError.textContent = "Enter a topic to research.";
      el.topicError.classList.remove("hidden");
      return;
    }
    el.topicError.classList.add("hidden");
    el.reportSection.classList.add("hidden");

    // Recorded at the start so an interrupted or failed run is still in history.
    currentTopic = topic;
    SessionHistory.upsert({ id: sessionId, topic });

    setRunning(true);
    ResearchStream.start(sessionId, topic, {
      onReport: renderReport,
      onEnd: () => setRunning(false),
    });
  });

  el.stopBtn.addEventListener("click", () => {
    ResearchStream.stop();
    setRunning(false);
  });

  function useSession(id) {
    sessionId = id;
    try {
      sessionStorage.setItem(SESSION_KEY, sessionId);
    } catch (err) {
      /* storage blocked — the in-memory id still works for this page */
    }
    el.sessionLabel.textContent = sessionId.slice(0, 8);
    SessionHistory.setCurrent(sessionId);
  }

  el.resetBtn.addEventListener("click", () => {
    if (ResearchStream.isRunning()) ResearchStream.stop();
    useSession(newSessionId());
    currentTopic = "";
    el.reportSection.classList.add("hidden");
    el.topic.value = "";
    autosizeTopic();
    setRunning(false);
    Pipeline.reset();
    Pipeline.log("New session started");
  });

  /* ---------------------------------------------------------------- history */

  /* Opening a past session restores its topic and report. The live pipeline is
     not replayed -- the stepper only ever shows the run happening right now. */
  function openSession(record) {
    if (ResearchStream.isRunning()) ResearchStream.stop();
    useSession(record.id);
    currentTopic = record.topic || "";
    el.topic.value = currentTopic;
    autosizeTopic();
    el.topicError.classList.add("hidden");
    setRunning(false);
    Pipeline.reset();

    if (record.report) {
      // Older history entries predate the flag; they were saved with the note
      // prefix, so fall back to reading it.
      const approved =
        record.approved === undefined ? !record.report.startsWith(">") : record.approved;
      showReport(record.report, approved, true);
      Pipeline.log(`Loaded from history: ${currentTopic}`);
    } else {
      el.reportSection.classList.add("hidden");
      Pipeline.log(`Loaded from history (no report was saved): ${currentTopic}`, "warning");
    }
  }

  SessionHistory.init({ currentId: sessionId, onOpen: openSession });
})();
