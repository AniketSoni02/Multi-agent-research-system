/* SSE client: turns the backend's node-update stream into pipeline calls. */

const ResearchStream = (() => {
  let source = null;
  let sawRejectingCritic = false;
  let approved = true;

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
    approved = true;

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
        Pipeline.start(data.topic, {
          maxIterations: data.max_iterations,
          maxToolCalls: data.max_critic_tool_calls,
        });
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
        case "router":
          Pipeline.routed(output.mode || "research", output.route_reason || "");
          break;

        case "direct_answer":
          Pipeline.directAnswered(output.final_report || "");
          Pipeline.finished(true);
          handlers.onReport(output.final_report || "", true);
          break;

        case "planner":
          if (sawRejectingCritic) {
            Pipeline.log("Planner is re-planning around the critic's findings", "warning");
            sawRejectingCritic = false;
          }
          Pipeline.beginRound(output.subtasks || [], output.iteration || 1, output.complexity || "");
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

        /* The critic's own turns carry no payload worth showing -- the evidence
           arrives with critic_tools, and the judgement with critic_feedback. */
        case "critic_tools":
          Pipeline.criticToolsRan(output.tool_evidence || []);
          break;

        case "critic_feedback":
          approved = Boolean(output.critic_approved);
          Pipeline.criticVerdict({
            critic_approved: approved,
            critic_feedback: output.critic_feedback || "",
            missing: output.missing || [],
            unsupported: output.unsupported || [],
          });
          if (!approved) sawRejectingCritic = true;
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
