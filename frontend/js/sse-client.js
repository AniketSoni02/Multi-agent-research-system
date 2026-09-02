/* SSE client: turns the backend's node-update stream into pipeline calls. */

const ResearchStream = (() => {
  let source = null;
  let sawRejectingCritic = false;

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
    sawRejectingCritic = false;

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
        Pipeline.start(data.topic, data.max_iterations);
        return;
      }

      if (data.event === "error") {
        Pipeline.failed(data.message || "The research run failed.");
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
        case "planner":
          if (sawRejectingCritic) {
            Pipeline.log("Planner is re-planning around the critic's gaps", "warning");
            sawRejectingCritic = false;
          }
          Pipeline.beginRound(output.subtasks || [], output.iteration || 1);
          break;

        case "researcher": {
          const findings = output.researcher_findings || [];
          findings.forEach((finding) => Pipeline.researcherFinished(finding));
          break;
        }

        case "synthesizer":
          Pipeline.synthesizing();
          Pipeline.synthesized(output.draft_report || "");
          break;

        case "critic":
          Pipeline.criticVerdict({
            critic_approved: Boolean(output.critic_approved),
            critic_feedback: output.critic_feedback || "",
            gaps: output.gaps || [],
          });
          if (!output.critic_approved) sawRejectingCritic = true;
          break;

        case "finalize":
          Pipeline.finished(!sawRejectingCritic);
          handlers.onReport(output.final_report || "");
          break;
      }
    };

    // EventSource auto-reconnects on error, which would silently restart the whole
    // graph; close explicitly instead.
    source.onerror = () => {
      if (source && source.readyState === EventSource.CLOSED) return;
      Pipeline.failed("Lost connection to the server.");
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
