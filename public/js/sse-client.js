/* SSE client: turns the backend's node-update stream into pipeline calls. */

const ResearchStream = (() => {
  let source = null;

  function close() {
    if (source) {
      source.close();
      source = null;
    }
  }

  function isRunning() {
    return source !== null;
  }

  function start(sessionId, topic, handlers) {
    close();

    const url = `/api/research/stream?session_id=${encodeURIComponent(sessionId)}&topic=${encodeURIComponent(topic)}`;
    source = new EventSource(url);

    source.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (err) {
        return;
      }

      if (data.event === "start") {
        Pipeline.start(data.topic, { maxIterations: data.max_iterations });
        return;
      }

      if (data.event === "error") {
        Pipeline.failed();
        close();
        handlers.onEnd();
        return;
      }

      if (data.event === "done") {
        close();
        handlers.onEnd();
        return;
      }

      const output = data.output || {};

      switch (data.node) {
        case "router":
          Pipeline.routed(output.mode || "research");
          break;

        case "direct_answer":
          Pipeline.directAnswered();
          Pipeline.finished(true);
          handlers.onReport(output.final_report || "", true);
          break;

        case "planner":
          Pipeline.beginRound(output.subtasks || [], output.iteration || 1);
          break;

        case "researcher":
          (output.researcher_findings || []).forEach(() => Pipeline.researcherFinished());
          break;

        case "synthesizer":
          Pipeline.synthesizing();
          Pipeline.synthesized();
          break;

        /* The critic's own turns carry nothing the stepper shows; its tool calls
           only keep the stage marked active while the loop runs. */
        case "critic_tools":
          Pipeline.criticToolsRan();
          break;

        case "critic_feedback":
          Pipeline.criticVerdict();
          break;

        case "finalize":
          Pipeline.finished(Boolean(output.approved));
          handlers.onReport(output.final_report || "", Boolean(output.approved));
          break;
      }
    };

    // EventSource auto-reconnects on error, which would silently restart the whole
    // graph; close explicitly instead.
    source.onerror = () => {
      if (source && source.readyState === EventSource.CLOSED) return;
      Pipeline.failed();
      close();
      handlers.onEnd();
    };
  }

  function stop() {
    if (!source) return;
    close();
    Pipeline.stopped();
  }

  return { start, stop, isRunning };
})();
