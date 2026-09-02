/* Pipeline view: maps SSE node events onto the stepper's visual states. */

const Pipeline = (() => {
  const stages = {
    router: document.getElementById("stage-router"),
    planner: document.getElementById("stage-planner"),
    researcher: document.getElementById("stage-researcher"),
    synthesizer: document.getElementById("stage-synthesizer"),
    critic: document.getElementById("stage-critic"),
  };

  const RESEARCH_STAGES = ["planner", "researcher", "synthesizer", "critic"];

  const el = {
    routerDetail: document.getElementById("router-detail"),
    plannerDetail: document.getElementById("planner-detail"),
    subtaskList: document.getElementById("subtask-list"),
    researcherCount: document.getElementById("researcher-count"),
    synthesizerDetail: document.getElementById("synthesizer-detail"),
    criticDetail: document.getElementById("critic-detail"),
    criticToolList: document.getElementById("critic-tool-list"),
    criticToolCount: document.getElementById("critic-tool-count"),
    iterationChip: document.getElementById("iteration-chip"),
    runChip: document.getElementById("run-chip"),
    loopbackNote: document.getElementById("loopback-note"),
    loopbackText: document.getElementById("loopback-text"),
    log: document.getElementById("activity-log"),
  };

  const TOOL_LABELS = {
    CheckCoverage: "Coverage",
    VerifyClaim: "Verify",
    CheckGrounding: "Grounding",
  };

  let maxIterations = 3;
  let maxToolCalls = 5;
  let iteration = 0;
  let expected = 0; // subtasks planned this round
  let done = 0; // researchers finished this round
  let toolCalls = 0; // critic tool calls this round

  function setState(name, state) {
    if (stages[name]) stages[name].dataset.state = state;
  }

  function setRunChip(text, variant) {
    el.runChip.className = `chip chip-${variant}`;
    el.runChip.textContent = text;
  }

  function log(message, variant = "muted") {
    const color = variant === "muted" ? "text-text-muted" : `text-${variant}`;
    const row = document.createElement("p");
    row.className = `body-md ${color}`;
    row.textContent = `${new Date().toLocaleTimeString()}  ${message}`;
    el.log.appendChild(row);
    el.log.scrollTop = el.log.scrollHeight;
  }

  function clearCriticTools() {
    toolCalls = 0;
    el.criticToolList.innerHTML = "";
    el.criticToolCount.className = "chip chip-neutral ml-auto";
    el.criticToolCount.textContent = "0 checks";
  }

  function reset(limits) {
    if (limits && limits.maxIterations) maxIterations = limits.maxIterations;
    if (limits && limits.maxToolCalls) maxToolCalls = limits.maxToolCalls;
    iteration = 0;
    expected = 0;
    done = 0;
    Object.keys(stages).forEach((name) => setState(name, "idle"));
    el.routerDetail.textContent = "Waiting";
    el.plannerDetail.textContent = "Waiting";
    el.synthesizerDetail.textContent = "Waiting";
    el.criticDetail.textContent = "Waiting";
    el.subtaskList.innerHTML = '<p class="body-md text-text-secondary">Waiting</p>';
    el.researcherCount.className = "chip chip-neutral ml-auto";
    el.researcherCount.textContent = "0 running";
    el.iterationChip.textContent = `Iteration 0 / ${maxIterations}`;
    el.iterationChip.className = "chip chip-neutral";
    el.loopbackNote.classList.add("hidden");
    el.loopbackNote.classList.remove("flex");
    clearCriticTools();
    el.log.innerHTML = "";
  }

  function start(topic, limits) {
    reset(limits);
    setRunChip("Running", "accent");
    setState("router", "active");
    el.routerDetail.textContent = "Judging the question…";
    log("Run started");
    log(`Topic: ${topic}`);
  }

  /* The router decides whether any of the research machinery runs at all. On the
     direct path the four research stages never fire, so mark them skipped rather
     than leaving them looking stuck. */
  function routed(mode, reason) {
    setState("router", "complete");
    el.routerDetail.textContent = mode === "direct" ? "Direct answer" : "Full research";
    log(`Router chose ${mode}: ${reason}`, mode === "direct" ? "accent" : "muted");

    if (mode === "direct") {
      RESEARCH_STAGES.forEach((name) => setState(name, "skipped"));
      el.plannerDetail.textContent = "Skipped";
      el.synthesizerDetail.textContent = "Skipped";
      el.criticDetail.textContent = "Skipped";
      el.subtaskList.innerHTML = '<p class="body-md text-text-muted">Skipped</p>';
      el.researcherCount.textContent = "none needed";
    } else {
      setState("planner", "active");
      el.plannerDetail.textContent = "Judging scope…";
    }
  }

  function directAnswered(report) {
    setRunChip("Answered directly", "success");
    log(`Direct answer produced (${report.length.toLocaleString()} chars)`, "success");
  }

  /* A second planner event after a rejecting critic means we looped back:
     clear the downstream stages so the new round reads as a fresh pass. */
  function beginRound(subtasks, round, complexity) {
    iteration = round;
    expected = subtasks.length;
    done = 0;
    el.iterationChip.className = "chip chip-accent";
    el.iterationChip.textContent = `Iteration ${round} / ${maxIterations}`;
    setState("planner", "complete");
    el.plannerDetail.textContent = `${subtasks.length} subtask${subtasks.length === 1 ? "" : "s"} planned`;

    setState("synthesizer", "idle");
    setState("critic", "idle");
    el.synthesizerDetail.textContent = "Waiting";
    el.criticDetail.textContent = "Waiting";
    clearCriticTools();

    setState("researcher", "active");
    el.subtaskList.innerHTML = "";
    subtasks.forEach((subtask) => {
      const row = document.createElement("div");
      row.className = "flex items-start gap-2";
      row.dataset.subtask = subtask;
      row.innerHTML = `<span class="spinner mt-0.5"></span><span class="body-md text-text-secondary"></span>`;
      row.querySelector("span:last-child").textContent = subtask;
      el.subtaskList.appendChild(row);
    });
    el.researcherCount.className = "chip chip-accent ml-auto";
    el.researcherCount.textContent = `${subtasks.length} running`;
    if (complexity) log(`Planner: ${complexity}`);
    subtasks.forEach((s) => log(`Planned: ${s}`));
  }

  function researcherFinished(finding) {
    done += 1;
    const rows = el.subtaskList.querySelectorAll("[data-subtask]");
    let matched = null;
    rows.forEach((row) => {
      if (!matched && row.dataset.subtask === finding.subtask) matched = row;
    });
    // Fall back to the first still-spinning row when the planner's wording and
    // the finding's wording drift apart.
    if (!matched) {
      rows.forEach((row) => {
        if (!matched && row.querySelector(".spinner")) matched = row;
      });
    }
    if (matched) {
      const spinner = matched.querySelector(".spinner");
      if (spinner) {
        const check = document.createElement("span");
        check.innerHTML =
          '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#50C58D" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';
        check.className = "mt-0.5 flex-none";
        spinner.replaceWith(check);
      }
    }
    el.researcherCount.textContent = `${done} / ${expected} done`;
    if (done >= expected) {
      el.researcherCount.className = "chip chip-success ml-auto";
      setState("researcher", "complete");
    }
    log(`Researcher finished (${finding.sources.length} sources): ${finding.subtask}`, "muted");
  }

  function synthesizing() {
    setState("synthesizer", "active");
    el.synthesizerDetail.textContent = "Merging findings…";
  }

  function synthesized(draft) {
    setState("synthesizer", "complete");
    el.synthesizerDetail.textContent = `Draft: ${draft.length.toLocaleString()} chars`;
    log("Synthesizer produced a draft report");
    setState("critic", "active");
    el.criticDetail.textContent = "Gathering evidence…";
    clearCriticTools();
  }

  /* One row per tool the critic ran. This is the part of the run that used to be
     invisible: the evidence behind the verdict, as it is gathered. */
  function criticToolsRan(evidence) {
    evidence.slice(toolCalls).forEach((row) => {
      const item = document.createElement("div");
      item.className = "flex items-start gap-2";
      const label = TOOL_LABELS[row.tool] || row.tool;
      const arg = Object.values(row.args || {})[0] || "";
      const summary = String(row.result || "").split(/\s+--\s+|\n/)[0].slice(0, 40);
      item.innerHTML =
        '<span class="chip chip-neutral flex-none"></span><span class="body-md text-text-secondary"></span>';
      item.querySelector(".chip").textContent = label;
      item.querySelector("span:last-child").textContent = summary
        ? `${summary} — ${arg}`
        : String(arg);
      el.criticToolList.appendChild(item);
      log(`Critic ran ${label}: ${String(arg).slice(0, 80)}`, "muted");
    });

    toolCalls = evidence.length;
    el.criticToolCount.className = "chip chip-accent ml-auto";
    el.criticToolCount.textContent = `${toolCalls} / ${maxToolCalls} checks`;
  }

  function criticVerdict(output) {
    setState("critic", "complete");
    const missing = output.missing || [];
    const unsupported = output.unsupported || [];

    if (output.critic_approved) {
      el.criticDetail.textContent = "Approved";
      el.criticToolCount.className = "chip chip-success ml-auto";
      el.loopbackNote.classList.add("hidden");
      el.loopbackNote.classList.remove("flex");
      log("Critic approved the report", "success");
      return;
    }

    const parts = [];
    if (missing.length) parts.push(`${missing.length} missing`);
    if (unsupported.length) parts.push(`${unsupported.length} unsupported`);
    el.criticDetail.textContent = parts.join(", ") || "Rejected";

    el.loopbackNote.classList.remove("hidden");
    el.loopbackNote.classList.add("flex");
    el.loopbackText.textContent =
      iteration >= maxIterations
        ? "Review limit reached — finalizing with the open points noted in the report."
        : `Looping back to the Planner: ${[...missing, ...unsupported].join(" · ")}`;

    log(`Critic rejected the draft: ${output.critic_feedback}`, "warning");
    missing.forEach((m) => log(`Missing: ${m}`, "warning"));
    unsupported.forEach((u) => log(`Unsupported: ${u}`, "warning"));
  }

  function finished(approved) {
    setRunChip(approved ? "Complete" : "Complete (with gaps)", approved ? "success" : "neutral");
    log("Run complete", "success");
  }

  function failed(message) {
    setRunChip("Failed", "danger");
    Object.keys(stages).forEach((name) => {
      if (stages[name].dataset.state === "active") setState(name, "error");
    });
    log(message, "danger");
  }

  function stopped() {
    setRunChip("Stopped", "neutral");
    Object.keys(stages).forEach((name) => {
      if (stages[name].dataset.state === "active") setState(name, "idle");
    });
    log("Run stopped by user", "warning");
  }

  return {
    reset,
    start,
    routed,
    directAnswered,
    beginRound,
    researcherFinished,
    synthesizing,
    synthesized,
    criticToolsRan,
    criticVerdict,
    finished,
    failed,
    stopped,
    log,
  };
})();
