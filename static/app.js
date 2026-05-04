const form = document.getElementById("check-form");
const requestState = document.getElementById("request-state");
const formMessage = document.getElementById("form-message");
const modelSelect = document.getElementById("model-select");
const modelInput = document.getElementById("model-input");
const toggleKeyButton = document.getElementById("toggle-key");
const apiKeyInput = document.getElementById("api-key");
const baseUrlInput = document.getElementById("base-url");
const timeoutInput = document.getElementById("timeout");
const streamInput = document.getElementById("stream");
const loadModelsButton = document.getElementById("load-models");
const runCheckButton = document.getElementById("run-check");

const heroScore = document.getElementById("hero-score");
const heroVerdict = document.getElementById("hero-verdict");
const heroMeta = document.getElementById("hero-meta");

const summaryScore = document.getElementById("summary-score");
const summaryPercent = document.getElementById("summary-percent");
const summaryVerdict = document.getElementById("summary-verdict");
const summaryTarget = document.getElementById("summary-target");
const summaryModel = document.getElementById("summary-model");
const summaryTimestamp = document.getElementById("summary-timestamp");
const summaryBanner = document.getElementById("summary-banner");

const probeGrid = document.getElementById("probe-grid");
const detailsContent = document.getElementById("details-content");

const PROBE_ORDER = [
  { endpoint: "chat/completions", probe: "success" },
  { endpoint: "chat/completions", probe: "error" },
  { endpoint: "responses", probe: "success" },
  { endpoint: "responses", probe: "error" },
  { endpoint: "chat/completions", probe: "stream" },
  { endpoint: "responses", probe: "stream" },
];

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setRequestState(text) {
  requestState.textContent = text;
}

function setBusy(isBusy, label) {
  loadModelsButton.disabled = isBusy;
  runCheckButton.disabled = isBusy;
  setRequestState(label);
}

function getBasePayload() {
  return {
    base_url: baseUrlInput.value.trim(),
    api_key: apiKeyInput.value.trim(),
  };
}

function getCheckPayload() {
  const chosenModel = modelInput.value.trim() || modelSelect.value.trim();
  return {
    ...getBasePayload(),
    model: chosenModel,
    stream: streamInput.checked,
    timeout: Number(timeoutInput.value || "30"),
  };
}

function setMessage(text, kind = "info") {
  formMessage.textContent = text;
  const palette =
    kind === "error"
      ? ["rgba(180, 35, 24, 0.12)", "#b42318"]
      : kind === "success"
        ? ["rgba(22, 101, 52, 0.10)", "#166534"]
        : ["rgba(15, 118, 110, 0.08)", "#0b5a55"];
  formMessage.style.background = palette[0];
  formMessage.style.color = palette[1];
}

function renderIdleCards(streamEnabled) {
  probeGrid.innerHTML = PROBE_ORDER.map(({ endpoint, probe }) => {
    const notRun = probe === "stream" && !streamEnabled;
    const badgeText = notRun ? "未运行" : "等待结果";
    return `
      <article class="probe-card is-idle">
        <h3>${escapeHtml(endpoint)}</h3>
        <p class="probe-subtitle">${escapeHtml(probe)}</p>
        <div class="probe-stats">
          <div><span>检查项</span><strong>-- / --</strong></div>
          <div><span>得分</span><strong>-- / --</strong></div>
        </div>
        <p class="probe-note">${notRun ? "本次检测没有启用流式探针。" : "运行检测后，这张卡片会显示对应 probe 的结果。"}</p>
        <span class="probe-badge idle">${badgeText}</span>
      </article>
    `;
  }).join("");
}

function probeStatus(result) {
  if (!result) {
    return { cardClass: "is-idle", badgeClass: "idle", badge: "等待结果" };
  }
  if (result.total === 0) {
    return { cardClass: "is-neutral", badgeClass: "neutral", badge: "没有检查项" };
  }
  const ratio = result.passed / result.total;
  if (ratio >= 0.8) {
    return { cardClass: "is-good", badgeClass: "good", badge: "通过占优" };
  }
  if (ratio <= 0.3) {
    return { cardClass: "is-bad", badgeClass: "bad", badge: "失败占优" };
  }
  return { cardClass: "is-neutral", badgeClass: "neutral", badge: "结果混合" };
}

function summarizeProbe(result) {
  if (!result || !Array.isArray(result.checks)) {
    return "运行检测后，这里会显示这组 probe 最关键的一条结论。";
  }
  const failed = result.checks.filter((check) => !check.ok);
  if (failed.length > 0) {
    return failed[0].detail;
  }
  return result.checks[0]?.detail || "这一组检查全部通过。";
}

function renderProbeGrid(results, streamEnabled) {
  const map = new Map(results.map((item) => [`${item.endpoint}::${item.probe}`, item]));
  probeGrid.innerHTML = PROBE_ORDER.map(({ endpoint, probe }) => {
    const key = `${endpoint}::${probe}`;
    const result = map.get(key);
    if (!result && probe === "stream" && !streamEnabled) {
      return `
        <article class="probe-card is-idle">
          <h3>${escapeHtml(endpoint)}</h3>
          <p class="probe-subtitle">${escapeHtml(probe)}</p>
          <div class="probe-stats">
            <div><span>检查项</span><strong>-- / --</strong></div>
            <div><span>得分</span><strong>-- / --</strong></div>
          </div>
          <p class="probe-note">本次检测没有启用流式探针。</p>
          <span class="probe-badge idle">未运行</span>
        </article>
      `;
    }

    const status = probeStatus(result);
    const note = summarizeProbe(result);
    const checksValue = result ? `${result.passed} / ${result.total}` : "-- / --";
    const scoreValue = result ? `${result.earned_score} / ${result.max_score}` : "-- / --";
    return `
      <article class="probe-card ${status.cardClass}">
        <h3>${escapeHtml(endpoint)}</h3>
        <p class="probe-subtitle">${escapeHtml(probe)}</p>
        <div class="probe-stats">
          <div><span>检查项</span><strong>${checksValue}</strong></div>
          <div><span>得分</span><strong>${scoreValue}</strong></div>
        </div>
        <p class="probe-note">${escapeHtml(note)}</p>
        <span class="probe-badge ${status.badgeClass}">${escapeHtml(status.badge)}</span>
      </article>
    `;
  }).join("");
}

function renderDetails(results) {
  if (!results.length) {
    detailsContent.innerHTML = `
      <div class="empty-state">
        <strong>还没有探针结果。</strong>
        <p>检测完成后，这里会按 probe 分组列出每一条通过或失败的检查，以及对应的诊断细节。</p>
      </div>
    `;
    return;
  }

  detailsContent.innerHTML = results.map((result, index) => `
    <details class="detail-group" ${index === 0 ? "open" : ""}>
      <summary>
        <div class="detail-heading">
          <strong>${escapeHtml(result.endpoint)} / ${escapeHtml(result.probe)}</strong>
          <span>通过 ${result.passed} / ${result.total} 项检查，得到 ${result.earned_score} / ${result.max_score} 分</span>
        </div>
        <span class="probe-badge ${probeStatus(result).badgeClass}">${escapeHtml(probeStatus(result).badge)}</span>
      </summary>
      <div class="check-list">
        ${result.checks.map((check) => `
          <article class="check-item ${check.ok ? "pass" : "fail"}">
            <span class="check-state">${check.ok ? "通过" : "失败"}</span>
            <div class="check-copy">
              <strong>${escapeHtml(check.name)}</strong>
              <p>${escapeHtml(check.detail)}</p>
            </div>
          </article>
        `).join("")}
      </div>
    </details>
  `).join("");
}

function renderSummary(report) {
  heroScore.textContent = `${report.total_score} / ${report.max_score}`;
  heroVerdict.textContent = report.verdict;
  heroMeta.textContent = `${report.target} · ${report.model} · ${report.stream_enabled ? "已开启流式" : "未开启流式"}`;

  summaryScore.textContent = `${report.total_score} / ${report.max_score}`;
  summaryPercent.textContent = `${report.percent}% 协议相似度评分`;
  summaryVerdict.textContent = report.verdict;
  summaryTarget.textContent = `目标：${report.target}`;
  summaryModel.textContent = `模型：${report.model}`;
  summaryTimestamp.textContent = `检测时间：${report.checked_at}`;
}

function renderError(message) {
  summaryBanner.textContent = message;
  summaryBanner.style.background = "rgba(180, 35, 24, 0.12)";
  summaryBanner.style.color = "#b42318";
}

function renderSuccessBanner(message) {
  summaryBanner.textContent = message;
  summaryBanner.style.background = "rgba(15, 118, 110, 0.08)";
  summaryBanner.style.color = "#0b5a55";
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    const error = new Error(data.detail || data.error || "请求失败");
    error.payload = data;
    throw error;
  }
  return data;
}

function validateBaseInputs(payload) {
  if (!payload.base_url || !payload.api_key) {
    throw new Error("基础地址和 API 密钥不能为空。");
  }
  if (!payload.base_url.startsWith("http://") && !payload.base_url.startsWith("https://")) {
    throw new Error("基础地址必须以 http:// 或 https:// 开头。");
  }
}

async function loadModels() {
  const payload = getBasePayload();
  validateBaseInputs(payload);
  setBusy(true, "正在获取模型");
  setMessage("正在从中转站拉取模型列表...");
  try {
    const data = await postJson("/api/models", payload);
    const currentManualValue = modelInput.value.trim();
    modelSelect.innerHTML = `<option value="">选择已发现的模型</option>` + data.models
      .map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.id)}</option>`)
      .join("");
    if (!currentManualValue && data.models.length > 0) {
      modelInput.value = data.models[0].id;
    }
    setMessage(`已加载 ${data.models.length} 个模型。你仍然可以手动覆盖模型名。`, "success");
  } catch (error) {
    setMessage(error.message, "error");
  } finally {
    setBusy(false, "空闲");
  }
}

async function runCheck(event) {
  event.preventDefault();
  const payload = getCheckPayload();
  validateBaseInputs(payload);
  if (!payload.model) {
    throw new Error("模型不能为空。");
  }
  if (!Number.isFinite(payload.timeout) || payload.timeout <= 0) {
    throw new Error("超时必须是大于 0 的数字。");
  }

  setBusy(true, "正在检测");
  renderSuccessBanner("正在同时探测 chat/completions 和 responses ...");
  renderIdleCards(payload.stream);
  detailsContent.innerHTML = `
    <div class="empty-state">
      <strong>检测进行中。</strong>
      <p>中转站响应后，仪表盘会一次性刷新所有结果。</p>
    </div>
  `;

  try {
    const data = await postJson("/api/check", payload);
    renderSummary(data);
    renderSuccessBanner(`检测完成，当前结论：${data.verdict}。`);
    renderProbeGrid(data.results, data.stream_enabled);
    renderDetails(data.results);
    setMessage("检测完成。你可以调整参数后再次运行。", "success");
  } catch (error) {
    renderError(error.message);
    renderIdleCards(payload.stream);
    renderDetails([]);
    setMessage(error.message, "error");
  } finally {
    setBusy(false, "空闲");
  }
}

toggleKeyButton.addEventListener("click", () => {
  const nextType = apiKeyInput.type === "password" ? "text" : "password";
  apiKeyInput.type = nextType;
  toggleKeyButton.textContent = nextType === "password" ? "显示" : "隐藏";
});

modelSelect.addEventListener("change", () => {
  if (modelSelect.value) {
    modelInput.value = modelSelect.value;
  }
});

loadModelsButton.addEventListener("click", async () => {
  try {
    await loadModels();
  } catch (error) {
    setMessage(error.message, "error");
  }
});

form.addEventListener("submit", async (event) => {
  try {
    await runCheck(event);
  } catch (error) {
    event.preventDefault();
    setMessage(error.message, "error");
    renderError(error.message);
    setBusy(false, "空闲");
  }
});

renderIdleCards(true);
