/* Session history: past runs kept in localStorage, listed in a navbar popover. */

const SessionHistory = (() => {
  const KEY = "research-agent-history";
  const LIMIT = 50;

  const el = {
    button: document.getElementById("history-btn"),
    count: document.getElementById("history-count"),
    panel: document.getElementById("history-panel"),
    search: document.getElementById("history-search"),
    list: document.getElementById("history-list"),
    empty: document.getElementById("history-empty"),
  };

  let records = [];
  let currentId = null;
  let filter = "";
  let onOpen = () => {};

  /* localStorage is per-browser and can be blocked (private mode) or full.
     History is a convenience, so every access degrades to "no history" rather
     than throwing and taking the rest of the page down with it. */
  function load() {
    try {
      const parsed = JSON.parse(localStorage.getItem(KEY) || "[]");
      records = Array.isArray(parsed) ? parsed.filter((r) => r && r.id) : [];
    } catch (err) {
      records = [];
    }
  }

  function persist() {
    try {
      localStorage.setItem(KEY, JSON.stringify(records));
    } catch (err) {
      /* quota exceeded or storage blocked — the in-memory list still works */
    }
  }

  function relativeTime(ts) {
    const mins = Math.floor((Date.now() - ts) / 60000);
    if (!ts || mins < 1) return "now";
    if (mins < 60) return `${mins}m`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days}d`;
    return new Date(ts).toLocaleDateString();
  }

  const PENCIL_ICON =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4L20 8a2.8 2.8 0 0 0-4-4L4 16v4Z"/><path d="m14 6 4 4"/></svg>';

  const TRASH_ICON =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4h8v2m-9 0 1 14h8l1-14"/></svg>';

  function iconButton(className, label, icon, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.title = label;
    button.setAttribute("aria-label", label);
    button.innerHTML = icon;
    button.addEventListener("click", (e) => {
      e.stopPropagation();
      handler();
    });
    return button;
  }

  /* Swap the whole title button for an input -- an <input> nested inside a
     <button> would never take focus. Enter or blur commits, Escape reverts; the
     keydown never reaches the document listener that closes the panel. */
  function startRename(record, titleButton) {
    const input = document.createElement("input");
    input.type = "text";
    input.className = "history-rename-input";
    input.value = record.topic || "";

    let settled = false;
    function settle(save) {
      if (settled) return;
      settled = true;
      const next = input.value.trim();
      if (save && next && next !== record.topic) rename(record.id, next);
      else render();
    }

    input.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Enter") {
        e.preventDefault();
        settle(true);
      } else if (e.key === "Escape") {
        e.preventDefault();
        settle(false);
      }
    });
    input.addEventListener("click", (e) => e.stopPropagation());
    input.addEventListener("blur", () => settle(true));

    titleButton.replaceWith(input);
    input.focus();
    input.select();
  }

  function buildRow(record) {
    const item = document.createElement("div");
    item.className = "history-row";
    if (record.id === currentId) item.dataset.current = "true";

    const open = document.createElement("button");
    open.type = "button";
    open.className = "history-open";

    const title = document.createElement("span");
    title.className = "history-title";
    // Topics are user input, so never interpolate them into markup.
    title.textContent = record.topic || "Untitled session";
    open.append(title);
    open.addEventListener("click", () => {
      close();
      onOpen(record);
    });

    // The timestamp and the actions share one grid cell: the row cross-fades
    // from the age to the buttons on hover, so a resting list reads as titles.
    const meta = document.createElement("div");
    meta.className = "history-meta";

    const time = document.createElement("span");
    time.className = "history-time";
    time.textContent = relativeTime(record.updatedAt);

    const actions = document.createElement("div");
    actions.className = "history-actions";
    actions.append(
      iconButton("history-action", "Rename session", PENCIL_ICON, () =>
        startRename(record, open)
      ),
      iconButton("history-action history-action-danger", "Delete session", TRASH_ICON, () =>
        remove(record.id)
      )
    );

    meta.append(time, actions);
    item.append(open, meta);
    return item;
  }

  function render() {
    const query = filter.trim().toLowerCase();
    const shown = query
      ? records.filter((r) => (r.topic || "").toLowerCase().includes(query))
      : records;

    el.list.innerHTML = "";
    shown.forEach((record) => el.list.appendChild(buildRow(record)));

    el.empty.textContent = records.length
      ? "No sessions match that search."
      : "No saved sessions yet — start a run and it lands here.";
    el.empty.classList.toggle("hidden", shown.length > 0);

    el.count.textContent = records.length ? String(records.length) : "";
    el.count.classList.toggle("hidden", records.length === 0);
  }

  /* Merge into the existing record for this id and move it to the front, so a
     run that starts (topic only) and later finishes (report) is one entry. */
  function upsert(patch) {
    if (!patch || !patch.id) return;
    const existing = records.find((r) => r.id === patch.id) || {};
    const merged = { ...existing, ...patch, updatedAt: Date.now() };
    records = [merged, ...records.filter((r) => r.id !== patch.id)].slice(0, LIMIT);
    persist();
    render();
  }

  function remove(id) {
    records = records.filter((r) => r.id !== id);
    persist();
    render();
  }

  /* Renaming is a relabel, not activity: it must not reorder the list or reset
     the row's age the way upsert() does. */
  function rename(id, topic) {
    const record = records.find((r) => r.id === id);
    if (!record) return;
    record.topic = topic;
    persist();
    render();
  }

  function setCurrent(id) {
    currentId = id;
    render();
  }

  function isOpen() {
    return !el.panel.classList.contains("hidden");
  }

  function open() {
    filter = "";
    el.search.value = "";
    render();
    el.panel.classList.remove("hidden");
    el.button.setAttribute("aria-expanded", "true");
    el.search.focus();
  }

  function close() {
    el.panel.classList.add("hidden");
    el.button.setAttribute("aria-expanded", "false");
  }

  function init(options) {
    currentId = options.currentId || null;
    onOpen = options.onOpen || onOpen;
    load();
    render();

    el.button.addEventListener("click", (e) => {
      e.stopPropagation();
      if (isOpen()) close();
      else open();
    });

    el.search.addEventListener("input", (e) => {
      filter = e.target.value;
      render();
    });

    document.addEventListener("click", (e) => {
      if (!isOpen()) return;
      if (el.panel.contains(e.target) || el.button.contains(e.target)) return;
      close();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && isOpen()) {
        close();
        el.button.focus();
      }
    });
  }

  return { init, upsert, remove, rename, setCurrent, close };
})();
