const chatLog = document.getElementById("chatLog");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");
const yamlEditor = document.getElementById("yamlEditor");
const yamlActions = document.getElementById("yamlActions");
const saveBtn = document.getElementById("saveBtn");
const revertBtn = document.getElementById("revertBtn");
const dirtyBadge = document.getElementById("dirtyBadge");
const statusBadge = document.getElementById("statusBadge");
const validationList = document.getElementById("validationList");
const warningList = document.getElementById("warningList");
const governancePanel = document.getElementById("governancePanel");
const governanceContent = document.getElementById("governanceContent");
const sessionSelect = document.getElementById("sessionSelect");
const newSessionBtn = document.getElementById("newSessionBtn");
const renameSessionBtn = document.getElementById("renameSessionBtn");
const deleteSessionBtn = document.getElementById("deleteSessionBtn");
const presetSelect = document.getElementById("presetSelect");
const exportBtn = document.getElementById("exportBtn");
const validateBtn = document.getElementById("validateBtn");
const integrityBadge = document.getElementById("integrityBadge");
const integrityPanel = document.getElementById("integrityPanel");

let currentSessionId = null;
let currentSessionTitle = "";
let savedYaml = "";
let exportAllowed = false;

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
  }
  return res.json();
}

function renderMessages(messages) {
  chatLog.innerHTML = "";
  for (const m of messages) {
    const div = document.createElement("div");
    div.className = `msg msg-${m.role}`;
    div.textContent = m.content;
    chatLog.appendChild(div);
  }
  chatLog.scrollTop = chatLog.scrollHeight;
}

function renderGovernance(analysis) {
  if (!analysis) {
    governancePanel.hidden = true;
    governanceContent.innerHTML = "";
    return;
  }
  governancePanel.hidden = false;
  const goal = analysis.goal || {};
  const actions = analysis.action_classes || [];
  const invariants = analysis.invariant_candidates || [];
  const ambiguities = analysis.ambiguities || [];
  const questions = analysis.open_questions || [];

  governanceContent.innerHTML = `
    <div class="gov-section">
      <div class="gov-label">Goal</div>
      <p>${goal.objective || "(not set)"}</p>
    </div>
    <div class="gov-section">
      <div class="gov-label">Actions (${actions.length})</div>
      <ul>${actions.map((a) => `<li>${a.action_type} — ${a.reversibility}${a.linked_limit_key ? ` → ${a.linked_limit_key}` : ""}</li>`).join("") || "<li>none</li>"}</ul>
    </div>
    <div class="gov-section">
      <div class="gov-label">Invariant candidates (${invariants.length})</div>
      <ul>${invariants.map((i) => `<li>${i.invariant_id} [${i.constraint_class}] → ${i.linked_limit_key || "—"}</li>`).join("") || "<li>none</li>"}</ul>
    </div>
    ${ambiguities.length ? `<div class="gov-section"><div class="gov-label">Ambiguities</div><ul>${ambiguities.map((a) => `<li>${a}</li>`).join("")}</ul></div>` : ""}
    ${questions.length ? `<div class="gov-section"><div class="gov-label">Open questions</div><ul>${questions.map((q) => `<li>${q}</li>`).join("")}</ul></div>` : ""}
  `;
}

function isDirty() {
  return yamlEditor.value !== savedYaml;
}

function refreshDirtyState() {
  const dirty = isDirty();
  yamlActions.hidden = !dirty;
  dirtyBadge.hidden = !dirty;
  // Unsaved manual edits must never be exported: the export uses the stored revision.
  exportBtn.disabled = !exportAllowed || dirty;
}

function setEditorContent(text) {
  yamlEditor.value = text;
  savedYaml = text;
  refreshDirtyState();
}

function renderYaml(data) {
  setEditorContent(data.contract_yaml || "# No contract yet");
  const status = data.session?.status || data.status || "drafting";
  statusBadge.textContent = status;
  statusBadge.className = `badge badge-${status === "ready" || status === "exported" ? status === "exported" ? "exported" : "ready" : "draft"}`;

  if (data.session?.title) {
    currentSessionTitle = data.session.title;
  }

  renderValidationLists(data.validation_errors, data.validation_warnings);
  renderGovernance(data.governance_analysis);

  exportAllowed = data.validation_ok ?? false;
  refreshDirtyState();
}

function renderValidationLists(errors, warnings) {
  validationList.innerHTML = "";
  for (const e of errors || []) {
    const li = document.createElement("li");
    li.textContent = e;
    validationList.appendChild(li);
  }

  warningList.innerHTML = "";
  for (const w of warnings || []) {
    const li = document.createElement("li");
    li.textContent = w;
    warningList.appendChild(li);
  }
}

function renderIntegrity(result) {
  integrityBadge.hidden = false;
  integrityPanel.hidden = false;

  if (result.integrity_ok) {
    integrityBadge.textContent = "integrity ok";
    integrityBadge.className = "badge badge-integrity-ok";
  } else {
    integrityBadge.textContent = "integrity fail";
    integrityBadge.className = "badge badge-integrity-fail";
  }

  const checks = result.checks || {};
  const rows = Object.entries(checks)
    .map(([name, info]) => {
      const ok = info.ok;
      const cls = ok === true ? "ok" : ok === false ? "fail" : "";
      const mark = ok === true ? "PASS" : ok === false ? "FAIL" : "—";
      return `<li class="${cls}"><strong>${name}</strong> [${mark}] — ${info.detail || ""}</li>`;
    })
    .join("");

  const hash = result.sha256
    ? `<p class="hash">sha256: ${result.sha256}</p>`
    : "";

  const summary = result.contract
    ? `<p>${result.contract.agent_id} · ${result.contract.role} · v${result.contract.version} · ${result.contract.owner}</p>`
    : "";

  integrityPanel.innerHTML = `
    <h3>${result.integrity_ok ? "YAML integrity confirmed" : "YAML integrity check failed"}</h3>
    ${summary}
    <ul>${rows}</ul>
    ${hash}
  `;

  exportAllowed = result.integrity_ok;
  refreshDirtyState();
  if (result.status) {
    statusBadge.textContent = result.status;
    statusBadge.className = `badge badge-${result.status === "exported" ? "exported" : result.status === "ready" ? "ready" : "draft"}`;
  }

  renderValidationLists(
    result.validation_errors || result.errors || [],
    result.validation_warnings || [],
  );
}

async function loadSessions() {
  const data = await api("/api/sessions");
  sessionSelect.innerHTML = "";
  for (const s of data.sessions) {
    const opt = document.createElement("option");
    opt.value = s.id;
    opt.textContent = `${s.title} — ${s.status}`;
    sessionSelect.appendChild(opt);
  }
  if (currentSessionId) {
    sessionSelect.value = currentSessionId;
  }
  return data.sessions;
}

async function loadSession(id) {
  const data = await api(`/api/sessions/${id}`);
  currentSessionId = id;
  sessionSelect.value = id;
  currentSessionTitle = data.session.title || "";
  if (data.session.preset && [...presetSelect.options].some((o) => o.value === data.session.preset)) {
    presetSelect.value = data.session.preset;
  }
  integrityBadge.hidden = true;
  integrityPanel.hidden = true;
  renderMessages(data.messages);
  renderYaml({
    contract_yaml: data.contract_yaml,
    validation_ok: data.validation_ok,
    validation_errors: data.validation_errors,
    validation_warnings: data.validation_warnings,
    governance_analysis: data.governance_analysis,
    session: data.session,
  });
}

async function createSession() {
  const preset = presetSelect.value;
  const defaultTitle = `Contract (${preset})`;
  const title = window.prompt("Session name", defaultTitle);
  if (title === null) return;
  const trimmed = title.trim() || defaultTitle;
  const data = await api("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ title: trimmed, preset }),
  });
  currentSessionId = data.session.id;
  await loadSessions();
  await loadSession(currentSessionId);
}

async function renameSession() {
  if (!currentSessionId) return;
  const next = window.prompt("Rename session", currentSessionTitle || "Untitled");
  if (next === null) return;
  const trimmed = next.trim();
  if (!trimmed) {
    alert("Name cannot be empty");
    return;
  }
  await api(`/api/sessions/${currentSessionId}`, {
    method: "PATCH",
    body: JSON.stringify({ title: trimmed }),
  });
  currentSessionTitle = trimmed;
  await loadSessions();
  await loadSession(currentSessionId);
}

async function deleteSession() {
  if (!currentSessionId) return;
  const label = currentSessionTitle || currentSessionId;
  if (!window.confirm(`Delete session "${label}"?\nMessages and revisions will be removed.`)) {
    return;
  }
  const deletedId = currentSessionId;
  await api(`/api/sessions/${deletedId}`, { method: "DELETE" });
  currentSessionId = null;
  const sessions = await loadSessions();
  if (sessions.length > 0) {
    await loadSession(sessions[0].id);
  } else {
    await createSession();
  }
}

function confirmDiscardEdits() {
  if (!isDirty()) return true;
  return window.confirm("Discard unsaved YAML edits?");
}

async function saveContract() {
  if (!currentSessionId) return;
  saveBtn.disabled = true;
  try {
    const data = await api(`/api/sessions/${currentSessionId}/contract`, {
      method: "PUT",
      body: JSON.stringify({ yaml: yamlEditor.value }),
    });
    integrityBadge.hidden = true;
    integrityPanel.hidden = true;

    if (data.saved) {
      // Server returns re-rendered canonical YAML, so the editor stays in sync.
      renderYaml(data);
      await loadSessions();
    } else {
      renderValidationLists(data.validation_errors, data.validation_warnings);
      exportAllowed = false;
      refreshDirtyState();
      statusBadge.textContent = "invalid";
      statusBadge.className = "badge badge-draft";
    }
  } catch (err) {
    alert(err.message);
  } finally {
    saveBtn.disabled = false;
  }
}

yamlEditor.addEventListener("input", refreshDirtyState);

yamlEditor.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    if (isDirty()) saveContract();
  }
});

saveBtn.addEventListener("click", () => saveContract());

revertBtn.addEventListener("click", () => {
  if (!confirmDiscardEdits()) return;
  yamlEditor.value = savedYaml;
  refreshDirtyState();
});

window.addEventListener("beforeunload", (e) => {
  if (isDirty()) {
    e.preventDefault();
    e.returnValue = "";
  }
});

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!currentSessionId) return;
  const message = chatInput.value.trim();
  if (!message) return;
  if (!confirmDiscardEdits()) return;

  sendBtn.disabled = true;
  try {
    const data = await api(`/api/sessions/${currentSessionId}/chat`, {
      method: "POST",
      body: JSON.stringify({ message }),
    });
    chatInput.value = "";
    await loadSessions();
    await loadSession(currentSessionId);
    renderYaml(data);
  } catch (err) {
    alert(err.message);
  } finally {
    sendBtn.disabled = false;
  }
});

newSessionBtn.addEventListener("click", () => createSession().catch((e) => alert(e.message)));
renameSessionBtn.addEventListener("click", () => renameSession().catch((e) => alert(e.message)));
deleteSessionBtn.addEventListener("click", () => deleteSession().catch((e) => alert(e.message)));

sessionSelect.addEventListener("change", () => {
  if (!confirmDiscardEdits()) {
    sessionSelect.value = currentSessionId;
    return;
  }
  loadSession(sessionSelect.value).catch((e) => alert(e.message));
});

exportBtn.addEventListener("click", async () => {
  if (!currentSessionId) return;
  exportBtn.disabled = true;
  try {
    const data = await api(`/api/sessions/${currentSessionId}/export`, {
      method: "POST",
      body: JSON.stringify({ emit: "both" }),
    });
    alert(`Exported:\n${data.paths.join("\n")}`);
    await loadSessions();
    await loadSession(currentSessionId);
  } catch (err) {
    alert(err.message);
  } finally {
    exportBtn.disabled = false;
  }
});

validateBtn.addEventListener("click", async () => {
  if (!currentSessionId) return;
  validateBtn.disabled = true;
  try {
    const yaml = yamlEditor.value || "";
    const data = await api(`/api/sessions/${currentSessionId}/validate`, {
      method: "POST",
      body: JSON.stringify({ yaml }),
    });
    renderIntegrity(data);
  } catch (err) {
    integrityBadge.hidden = false;
    integrityBadge.textContent = "integrity fail";
    integrityBadge.className = "badge badge-integrity-fail";
    integrityPanel.hidden = false;
    integrityPanel.innerHTML = `<h3>Validation request failed</h3><p class="fail">${err.message}</p>`;
  } finally {
    validateBtn.disabled = false;
  }
});

(async function boot() {
  try {
    const sessions = await loadSessions();
    if (sessions.length > 0) {
      await loadSession(sessions[0].id);
    } else {
      await createSession();
    }
  } catch (e) {
    alert(e.message);
  }
})();
