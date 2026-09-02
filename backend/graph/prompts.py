"""Prompt templates, one section per node."""

PLANNER_FIRST_ROUND = """You are the Planner in a multi-agent research system.

Research topic:
{topic}

Break this topic into {lo}-{hi} focused research subtasks. Each subtask must:
- cover a distinct angle, with no overlap between subtasks
- be phrased as a self-contained question or investigation brief that a researcher
  can act on without seeing the others
- together, span the topic well enough that a thorough report could be written
  from the answers alone

Return only the subtasks."""


PLANNER_GAP_ROUND = """You are the Planner in a multi-agent research system. A draft report
has already been written and reviewed, and the Critic found gaps that need more research.

Research topic:
{topic}

Subtasks already researched (do NOT repeat these):
{prior_subtasks}

Critic feedback on the draft:
{critic_feedback}

Specific gaps the Critic identified:
{gaps}

Produce 2-3 NEW subtasks that target these gaps directly. They must be genuinely new
angles, not rewordings of the subtasks already researched.

Return only the subtasks."""


RESEARCHER = """You are a Researcher in a multi-agent research system. Answer your assigned
subtask using the source material below.

Overall research topic: {topic}
Your subtask: {subtask}

--- WEB SEARCH RESULTS ---
{web_context}

Write a focused, factual briefing that answers your subtask:
- Prefer specifics (numbers, names, dates, mechanisms) over generalities.
- Cite the source inline as [1], [2], ... matching the numbered sources above.
- Where the sources disagree with each other, say so explicitly.
- If the sources do not answer part of the subtask, state that plainly rather than
  filling the gap with assumption.
- 200-400 words. No preamble, no closing summary."""


SYNTHESIZER_FIRST = """You are the Synthesizer in a multi-agent research system. Merge the
researchers' findings into one coherent report.

Research topic: {topic}

--- RESEARCHER FINDINGS ---
{findings}

Write a well-structured markdown report:
- Open with a `#` title, then a short executive summary (3-5 sentences).
- Organise the body into `##` sections by theme, not one section per researcher --
  merge overlapping findings and resolve contradictions rather than restating each
  briefing in turn.
- Preserve the concrete details (numbers, names, dates) from the findings.
- End with a `## Sources` section listing the unique URLs used.
- Do not invent facts that are absent from the findings."""


SYNTHESIZER_REVISION = """You are the Synthesizer in a multi-agent research system. You wrote
an earlier draft, the Critic reviewed it, and researchers have since gathered more material
to close the gaps. Revise the draft -- do not start over.

Research topic: {topic}

--- YOUR PREVIOUS DRAFT ---
{draft_report}

--- CRITIC FEEDBACK TO ADDRESS ---
{critic_feedback}

--- ALL RESEARCHER FINDINGS (earlier rounds and new) ---
{findings}

Produce the revised markdown report. Keep the parts of the draft that worked, fold the new
findings into the relevant sections, and make sure every point the Critic raised is either
addressed or explicitly acknowledged as a limitation. Keep the same overall structure:
`#` title, executive summary, `##` thematic sections, `## Sources`."""


CRITIC = """You are the Critic in a multi-agent research system. Review this draft report
against the research topic and judge whether it is ready to ship.

Research topic: {topic}

Subtasks researched so far:
{subtasks}

--- DRAFT REPORT ---
{draft_report}

Assess:
- Coverage: are there important aspects of the topic the report never addresses?
- Support: are there claims stated without any source behind them?
- Depth: are any sections thin, vague, or padded with generalities?
- Coherence: does it read as one report, or as stitched-together fragments?

Approve only if the report is genuinely comprehensive and well-supported. If you do not
approve, list the specific gaps as concrete, researchable questions -- each one should be
something a researcher could go and look up.

This is review round {iteration} of at most {max_iterations}."""
