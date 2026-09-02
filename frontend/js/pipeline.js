/* Pipeline view: maps SSE node events onto the stepper's visual states. */

const Pipeline = (() => {
  const stages = {
    planner: document.getElementById("stage-planner"),
    researcher: document.getElementById("stage-researcher"),
    synthesizer: document.getElementById("stage-synthesizer"),
    critic: document.getElementById("stage-critic"),
  };

  const el = {
    plannerDetail: document.getElementById("planner-detail"),
    subtaskList: document.getElementById("subtask-list"),
    researcherCount: document.getElementById("researcher-count"),
    synthesizerDetail: document.getElementById("synthesizer-detail"),
    criticDetail: document.getElementById("critic-detail"),
    iterationChip: document.getElementById("iteration-chip"),
    runChip: document.getElementById("run-chip"),
    loopbackNote: document.getElementById("loopback-note"),
    loopbackText: document.getElementById("loopback-text"),
    log: document.getElementById("activity-log"),
  };

  let maxIterations = 3;
  let iteration = 0;
  let expected = 0; // subtasks planned this round
  let done = 0; // researchers finished this round

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

  function reset(limit) {
    maxIterations = limit || maxIterations;
    iteration = 0;
    expected = 0;
    done = 0;
    Object.keys(stages).forEach((name) => setState(name, "idle"));
    el.plannerDetail.textContent = "Waiting";
    el.synthesizerDetail.textContent = "Waiting";
    el.criticDetail.textContent = "Waiting";
    el.subtaskList.innerHTML = '<p class="body-md text-text-secondary">Waiting</p>';
    el.researcherCount.className = "chip chip-neutral ml-auto";
    el.researcherCount.textContent = "0 running";
    el.iterationChip.textContent = `Iteration 0 / ${maxIterations}`;
    el.loopbackNote.classList.add("hidden");
    el.loopbackNote.classList.remove("flex");
    el.log.innerHTML = "";
  }

  function start(topic, limit) {
    reset(limit);
    setRunChip("Running", "accent");
    setState("planner", "active");
    el.plannerDetail.textContent = "Splitting the topic…";
    log("Run started — web search");
    log(`Topic: ${topic}`);
  }

  /* A second planner event after a rejecting critic means we looped back:
     clear the downstream stages so the new round reads as a fresh pass. */
  function beginRound(subtasks, round) {
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
    el.criticDetail.textContent = "Reviewing the draft…";
  }

  function criticVerdict(output) {
    setState("critic", "complete");
    if (output.critic_approved) {
      el.criticDetail.textContent = "Approved";
      el.loopbackNote.classList.add("hidden");
      el.loopbackNote.classList.remove("flex");
      log("Critic approved the report", "success");
    } else {
      el.criticDetail.textContent = `${output.gaps.length} gap${output.gaps.length === 1 ? "" : "s"} found`;
      el.loopbackNote.classList.remove("hidden");
      el.loopbackNote.classList.add("flex");
      el.loopbackText.textContent =
        iteration >= maxIterations
          ? "Review limit reached — finalizing with the gaps noted in the report."
          : `Looping back to the Planner: ${output.gaps.join(" · ")}`;
      log(`Critic rejected the draft: ${output.critic_feedback}`, "warning");
    }
  }

  function finished(approved) {
    setRunChip(approved ? "Complete" : "Complete (with gaps)", approved ? "success" : "neutral");
    log("Run complete", "success");
  }

  function failed(message) {
    setRunChip("Failed", "danger");
    ["planner", "researcher", "synthesizer", "critic"].forEach((name) => {
      if (stages[name].dataset.state === "active") setState(name, "error");
    });
    log(message, "danger");
  }

  function stopped() {
    setRunChip("Stopped", "neutral");
    ["planner", "researcher", "synthesizer", "critic"].forEach((name) => {
      if (stages[name].dataset.state === "active") setState(name, "idle");
    });
    log("Run stopped by user", "warning");
  }

  return {
    reset,
    start,
    beginRound,
    researcherFinished,
    synthesizing,
    synthesized,
    criticVerdict,
    finished,
    failed,
    stopped,
    log,
  };
})();
