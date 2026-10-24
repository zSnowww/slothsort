const planButton = document.querySelector("#plan-button");
const applyButton = document.querySelector("#apply-button");
const status = document.querySelector("#status");
const results = document.querySelector("#results");
const folders = document.querySelector("#folders");
const decisions = document.querySelector("#chat-decisions");
const analysisMode = document.querySelector("#analysis-mode");
const messageLimit = document.querySelector("#message-limit");
const messageLimitRow = document.querySelector("#message-limit-row");
const analysisEngine = document.querySelector("#analysis-engine");
const remoteConsent = document.querySelector("#remote-consent");
const remoteConsentRow = document.querySelector("#remote-consent-row");
const connectionTitle = document.querySelector("#connection-title");
const connectionDetail = document.querySelector("#connection-detail");
const undoButton = document.querySelector("#undo-button");
const toastRegion = document.querySelector("#toast-region");
const demoBanner = document.querySelector("#demo-banner");
let activePlan = null;
let activeUndoId = null;
let toastTimer = null;
let engineAvailability = {};
let telegramReady = false;
let demoMode = false;

function showToast(message, kind = "info", persistent = false) {
  clearTimeout(toastTimer);
  toastRegion.replaceChildren();
  const item = document.createElement("div");
  item.className = `toast ${kind}`;
  if (kind === "error") item.setAttribute("role", "alert");
  const content = document.createElement("span");
  content.className = "toast-message";
  content.textContent = message;
  const close = document.createElement("button");
  close.className = "toast-close";
  close.type = "button";
  close.setAttribute("aria-label", "Cerrar aviso");
  close.textContent = "×";
  close.addEventListener("click", () => item.remove());
  item.append(content, close);
  toastRegion.append(item);
  if (!persistent) toastTimer = setTimeout(() => item.remove(), kind === "error" ? 9000 : 6000);
}

function setUndoId(id) {
  activeUndoId = id;
  undoButton.classList.toggle("hidden", !id);
}

function refreshEngineChoice() {
  const isRemote = analysisEngine.value !== "ollama";
  remoteConsentRow.classList.toggle("hidden", !isRemote);
  planButton.disabled = !telegramReady || !engineAvailability[analysisEngine.value]
    || (isRemote && !remoteConsent.checked);
}

function refreshMessageLimit() {
  messageLimitRow.classList.toggle("hidden", !analysisMode.value.startsWith("messages_"));
}

function setBusy(button, busy, label) {
  button.disabled = busy;
  button.dataset.original ||= button.textContent;
  button.textContent = busy ? label : button.dataset.original;
}

function showStatus(message, error = false) {
  status.textContent = message;
  status.style.color = error ? "#ff9f96" : "";
}

function addOption(select, value, label) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  select.append(option);
}

function renderPlan(plan) {
  folders.replaceChildren();
  decisions.replaceChildren();

  if (!plan.folders.length) {
    const message = document.createElement("p");
    message.className = "reason";
    message.textContent = "No hay carpetas con evidencia suficiente. Puedes dejar estos chats sin clasificar y probar otro modo de análisis.";
    folders.append(message);
  }

  plan.folders.forEach((folder, index) => {
    const article = document.createElement("article");
    article.className = "folder";
    const label = document.createElement("label");
    label.textContent = `Carpeta ${index + 1}`;
    const title = document.createElement("input");
    title.className = "folder-name";
    title.maxLength = 12;
    title.value = folder.title;
    label.append(title);
    const reason = document.createElement("p");
    reason.className = "reason";
    reason.textContent = folder.reason;
    article.append(label, reason);
    folders.append(article);
  });

  plan.decisions.forEach((decision) => {
    const row = document.createElement("article");
    row.className = "decision";
    const detail = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = decision.chat.title;
    const kind = document.createElement("span");
    kind.className = "chat-kind";
    kind.textContent = decision.chat.kind;
    const reason = document.createElement("p");
    reason.className = "reason";
    reason.textContent = decision.reason;
    detail.append(name, kind, reason);

    const controls = document.createElement("div");
    controls.className = "decision-controls";
    const confidence = document.createElement("span");
    confidence.className = `confidence ${decision.review_status}`;
    const label = decision.review_status === "suggested" ? "Propuesta clara"
      : decision.review_status === "review" ? "Revisar" : "Sin clasificar";
    confidence.textContent = `${label} · ${Math.round(decision.confidence * 100)} %`;
    const select = document.createElement("select");
    select.className = "chat-folder";
    select.dataset.chatKey = decision.chat.key;
    select.setAttribute("aria-label", `Carpeta para ${decision.chat.title}`);
    addOption(select, "", "Sin carpeta");
    plan.folders.forEach((folder, index) => addOption(select, String(index), folder.title));
    if (decision.review_status === "suggested" && decision.proposed_folder !== null) {
      select.value = String(decision.proposed_folder);
    }
    controls.append(confidence, select);
    row.append(detail, controls);
    decisions.append(row);
  });

  folders.querySelectorAll(".folder-name").forEach((input, index) => {
    input.addEventListener("input", () => {
      decisions.querySelectorAll(".chat-folder").forEach((select) => {
        select.options[index + 1].textContent = input.value || `Carpeta ${index + 1}`;
      });
    });
  });
  results.classList.remove("hidden");
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status");
    const data = await response.json();
    demoMode = Boolean(data.demo_mode);
    demoBanner.classList.toggle("hidden", !demoMode);
    engineAvailability = Object.fromEntries(data.engines.map((engine) => [engine.id, engine.available]));
    telegramReady = data.telegram_authorized;
    const ready = data.telegram_authorized && engineAvailability[analysisEngine.value];
    connectionTitle.textContent = ready
      ? demoMode ? "Demo sintética y motor listos"
        : analysisEngine.value === "ollama" ? "Telegram y Ollama listos" : "Telegram y CLI instalado"
      : "Falta completar la conexión";
    if (!data.telegram_configured) {
      connectionDetail.textContent = "Añade TELEGRAM_API_ID y TELEGRAM_API_HASH al archivo .env.";
    } else if (!data.telegram_authorized) {
      connectionDetail.textContent = "Ejecuta: uv run python scripts/login.py";
    } else if (!engineAvailability[analysisEngine.value]) {
      connectionDetail.textContent = `El motor ${analysisEngine.selectedOptions[0].textContent} no está disponible.`;
    } else if (demoMode) {
      connectionDetail.textContent = `Chats inventados · ${analysisEngine.selectedOptions[0].textContent} · no se escribirá en Telegram.`;
    } else {
      connectionDetail.textContent = `Sesión MTProto autorizada · ${analysisEngine.selectedOptions[0].textContent} · hasta ${data.max_chats} chats por prueba.${analysisEngine.value === "ollama" ? "" : " La autenticación del CLI se comprobará al analizar."}`;
    }
    refreshEngineChoice();
    setUndoId(data.undo_id);
  } catch {
    connectionTitle.textContent = "La aplicación no responde";
    connectionDetail.textContent = "Comprueba el servidor y vuelve a cargar la página.";
    showToast("No se pudo consultar el estado de la aplicación.", "error");
  }
}

analysisMode.addEventListener("change", () => {
  refreshMessageLimit();
  activePlan = null;
  results.classList.add("hidden");
  showStatus("Modo actualizado. Genera un nuevo plan para usarlo.");
});
messageLimit.addEventListener("change", () => {
  activePlan = null;
  results.classList.add("hidden");
  showStatus("Cantidad de mensajes actualizada. Genera un nuevo plan para usarla.");
});

analysisEngine.addEventListener("change", () => {
  remoteConsent.checked = false;
  activePlan = null;
  results.classList.add("hidden");
  refreshEngineChoice();
  refreshStatus();
});
remoteConsent.addEventListener("change", refreshEngineChoice);

planButton.addEventListener("click", async () => {
  setBusy(planButton, true, "Analizando chats…");
  analysisMode.disabled = true;
  messageLimit.disabled = true;
  analysisEngine.disabled = true;
  remoteConsent.disabled = true;
  showStatus("Preparando el análisis…");
  showToast("Preparando el análisis…", "loading", true);
  try {
    const response = await fetch("/api/plan-jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: analysisMode.value,
        message_limit: Number(messageLimit.value),
        engine: analysisEngine.value,
        remote_consent: analysisEngine.value !== "ollama" && remoteConsent.checked,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "No se pudo crear el plan.");
    let lastStage = "";
    while (true) {
      await new Promise((resolve) => setTimeout(resolve, 1200));
      const progressResponse = await fetch(`/api/plan-jobs/${data.job_id}`);
      const progress = await progressResponse.json();
      if (!progressResponse.ok) throw new Error(progress.detail || "Se perdió el estado del análisis.");
      if (progress.stage !== lastStage) {
        lastStage = progress.stage;
        showStatus(lastStage);
        showToast(lastStage, "loading", true);
      }
      if (progress.status === "failed") throw new Error(progress.error || "El análisis falló.");
      if (progress.status === "completed") {
        activePlan = progress.result;
        renderPlan(activePlan);
        const clear = activePlan.decisions.filter((item) => item.review_status === "suggested").length;
        const message = `${activePlan.analyzed_chats} chats analizados; ${clear} ${clear === 1 ? "preseleccionado" : "preseleccionados"}. Revisa antes de crear carpetas.`;
        showStatus(message);
        showToast(message, "success");
        break;
      }
    }
  } catch (error) {
    showStatus(error.message, true);
    showToast(error.message, "error");
  } finally {
    setBusy(planButton, false, "");
    analysisMode.disabled = false;
    messageLimit.disabled = false;
    analysisEngine.disabled = false;
    remoteConsent.disabled = false;
    refreshEngineChoice();
  }
});

applyButton.addEventListener("click", async () => {
  if (!activePlan) return;
  const choices = activePlan.folders.map((_, index) => ({
    index,
    title: folders.querySelectorAll(".folder-name")[index].value.trim(),
    chat_keys: [],
  }));
  decisions.querySelectorAll(".chat-folder").forEach((select) => {
    if (select.value !== "") choices[Number(select.value)].chat_keys.push(select.dataset.chatKey);
  });
  const selected = choices.filter((choice) => choice.chat_keys.length);
  if (!selected.length) {
    showStatus("Asigna al menos un chat a una carpeta.", true);
    return showToast("Asigna al menos un chat a una carpeta.", "error");
  }
  if (selected.some((choice) => !choice.title || choice.title.length > 12)) {
    showStatus("Cada carpeta seleccionada necesita un nombre de hasta 12 caracteres.", true);
    return showToast("Cada carpeta seleccionada necesita un nombre de hasta 12 caracteres.", "error");
  }

  setBusy(applyButton, true, demoMode ? "Creando en demo…" : "Creando en Telegram…");
  showToast(demoMode ? "Creando carpetas de demostración…" : "Creando carpetas en Telegram…", "loading", true);
  try {
    const response = await fetch(`/api/plans/${activePlan.plan_id}/apply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folders: selected }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "No se pudieron crear las carpetas.");
    results.classList.add("hidden");
    activePlan = null;
    setUndoId(data.undo_id);
    const location = demoMode ? "la demo" : "Telegram";
    const message = `${data.created.length} carpetas creadas en ${location}.${data.skipped.length ? ` ${data.skipped.length} omitidas: ${data.skipped.join("; ")}` : ""}`;
    showStatus(message);
    showToast(message, "success");
  } catch (error) {
    showStatus(error.message, true);
    showToast(error.message, "error");
  } finally {
    setBusy(applyButton, false, "");
  }
});

undoButton.addEventListener("click", async () => {
  if (!activeUndoId) return;
  if (!window.confirm("¿Deshacer la última creación de carpetas? Las carpetas modificadas después no se borrarán.")) return;
  setBusy(undoButton, true, "Revirtiendo…");
  showToast("Comprobando y revirtiendo las carpetas creadas…", "loading", true);
  try {
    const response = await fetch("/api/undo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ undo_id: activeUndoId }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "No se pudo revertir el cambio.");
    setUndoId(null);
    const message = `${data.deleted.length} carpetas revertidas.${data.skipped.length ? ` ${data.skipped.join("; ")}` : ""}`;
    showStatus(message);
    showToast(message, data.skipped.length ? "error" : "success");
  } catch (error) {
    showStatus(error.message, true);
    showToast(error.message, "error");
  } finally {
    setBusy(undoButton, false, "");
  }
});

refreshMessageLimit();
refreshStatus();
