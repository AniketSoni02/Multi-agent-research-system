/* Pipeline view: maps SSE node events onto the stepper's visual states.

   The cards carry the node's name and nothing else, so every handler here does
   one thing -- move a stage between idle / active / complete / skipped / error.
   The run's substance lives in the report below, not in the stepper. */

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
    iterationChip: document.getElementById("iteration-chip"),
    runChip: document.getElementById("run-chip"),
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

  function setIterationChip(text, variant) {
    el.iterationChip.className = `chip chip-${variant}`;
    el.iterationChip.textContent = text;
  }

  function reset(limits) {
    if (limits && limits.maxIterations) maxIterations = limits.maxIterations;
    iteration = 0;
    expected = 0;
    done = 0;
    Object.keys(stages).forEach((name) => setState(name, "idle"));
    setIterationChip(`Iteration 0 / ${maxIterations}`, "neutral");
  }

  function start(topic, limits) {
    reset(limits);
    setRunChip("Running", "accent");
    setState("router", "active");
  }

  /* On the direct path the four research stages never run, so mark them skipped
     rather than leaving them looking stalled. */
  function routed(mode) {
    setState("router", "complete");
    if (mode === "direct") {
      RESEARCH_STAGES.forEach((name) => setState(name, "skipped"));
    } else {
      setState("planner", "active");
    }
  }

  function directAnswered() {
    setRunChip("Answered directly", "success");
  }

  /* A second planner event after a rejecting critic means we looped back: clear
     the downstream stages so the new round reads as a fresh pass. */
  function beginRound(subtasks, round) {
    iteration = round;
    expected = subtasks.length;
    done = 0;
    setIterationChip(`Iteration ${round} / ${maxIterations}`, "accent");
    setState("planner", "complete");
    setState("synthesizer", "idle");
    setState("critic", "idle");
    setState("researcher", "active");
  }

  function researcherFinished() {
    done += 1;
    if (done >= expected) setState("researcher", "complete");
  }

  function synthesizing() {
    setState("synthesizer", "active");
  }

  function synthesized() {
    setState("synthesizer", "complete");
    setState("critic", "active");
  }

  function criticToolsRan() {
    setState("critic", "active");
  }

  function criticVerdict() {
    setState("critic", "complete");
  }

  function finished(approved) {
    setRunChip(approved ? "Complete" : "Complete (with gaps)", approved ? "success" : "neutral");
  }

  function failed() {
    setRunChip("Failed", "danger");
    Object.keys(stages).forEach((name) => {
      if (stages[name].dataset.state === "active") setState(name, "error");
    });
  }

  function stopped() {
    setRunChip("Stopped", "neutral");
    Object.keys(stages).forEach((name) => {
      if (stages[name].dataset.state === "active") setState(name, "idle");
    });
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
  };
})();
