// Configuració
const PORT = 3000; // Port on corre el backend admin (uvicorn)
const SERVER = `http://localhost:${PORT}`;
// Bases d'API
const API_BASE = `${SERVER}/api`;
const RANKINGS_API = `${API_BASE}/rankings`;
const VALIDATIONS_API = `${API_BASE}/validations`;
const FAVORITES_API = `${API_BASE}/favorites`;
const DIFFICULTIES_API = `${API_BASE}/difficulties`;
const SYNONYMS_API = `${API_BASE}/synonyms`;
const AUTH_ENDPOINT = `${API_BASE}/auth`;
const GENERATE_ENDPOINT = `${API_BASE}/generate`; // alternatiu
const GENERATE_RANDOM_ENDPOINT = `${API_BASE}/generate-random`;
// Page size per a càrrega de fragments
const PAGE_SIZE = 300;
// Diccionari (obertura en nova pestanya). Substituïm [PARAULA]
const DICT_URL_TEMPLATE =
  "https://www.diccionari.cat/cerca/gran-diccionari-de-la-llengua-catalana?search_api_fulltext_cust=[PARAULA]";

let adminToken = null; // guardem la contrasenya (x-admin-token)

async function ensureAuthenticated() {
  if (adminToken) return true;
  const pwd = prompt("Contrasenya admin:", "");
  if (pwd === null) return false;
  try {
    const res = await fetch(AUTH_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pwd }),
    });
    if (!res.ok) throw new Error("Auth failed");
    const data = await res.json();
    if (data.ok) {
      adminToken = pwd; // s'utilitza com a token simple
      return true;
    }
  } catch (_) {
    alert("Contrasenya incorrecta");
  }
  return ensureAuthenticated(); // reintenta fins cancel·lar
}

function authHeaders() {
  return adminToken ? { "x-admin-token": adminToken } : {};
}

// Estat global
let files = [];
let selected = null;
// Nou model: paraules carregades per posició absoluta (sparse)
let wordsByPos = {}; // pos -> {word,pos}
// offset ja no s'utilitza per la finestra lliscant, però el mantenim per compatibilitat amb codi antic (guardat)
let offset = 0; // sempre 0 per al fragment que desem
let total = 0;
let loading = false;
let dirty = false;
let menuIdx = null;
let menuAnchor = null;
let confirmDelete = null;
// Guarda informació de l'últim moviment
let lastMoveInfo = null; // {word, toPos}
let validations = {}; // filename -> 'validated' | 'approved' (empty means not validated)
let favorites = {}; // filename -> true
let difficulties = {}; // filename -> 'facil'|'mitja'|'dificil'
let comments = {}; // Estat dels comentaris del fitxer actual {global: "", words: {}}
let showOnlyPending = false; // filtre de fitxers no validats
let showOnlyFavorites = false; // filtre de fitxers preferits
let autoSaveTimer = null; // temporitzador per auto-desat
const AUTO_SAVE_DELAY = 800; // ms després de l'últim canvi de drag

// Configuració general
let settings = {
  autoScroll: true, // per defecte activat
};

// Carrega configuració del localStorage
function loadSettings() {
  try {
    const saved = localStorage.getItem("rebuscada-admin-settings");
    if (saved) {
      settings = { ...settings, ...JSON.parse(saved) };
    }
  } catch (e) {
    console.warn("Error carregant configuració:", e);
  }
}

// Desa configuració al localStorage
function saveSettings() {
  try {
    localStorage.setItem("rebuscada-admin-settings", JSON.stringify(settings));
  } catch (e) {
    console.warn("Error desant configuració:", e);
  }
}

// Highlight temporal helper (classe configurable)
function tempHighlightElement(el, ms = 1000, cls = "moved") {
  if (!el) return;
  el.classList.add(cls);
  setTimeout(() => {
    if (el.classList) el.classList.remove(cls);
  }, ms);
}

// Color segons posició
function colorPerPos(posicio) {
  if (posicio < 100) return "#4caf50"; // Verd
  if (posicio < 250) return "#ffc107"; // Groc
  if (posicio < 500) return "#ff9800"; // Taronja
  if (posicio < 2000) return "#f44336"; // Vermell
  return "#9e9e9e"; // Gris per la resta
}

// Genera etiqueta de dificultat amb color
function getDifficultyTag(difficulty) {
  const configs = {
    facil: { label: "Fàcil", color: "#28a745", bg: "#d4edda" },
    mitja: { label: "Mitjà", color: "#fd7e14", bg: "#fef3cd" },
    dificil: { label: "Difícil", color: "#dc3545", bg: "#f8d7da" },
  };
  const config = configs[difficulty];
  if (!config) return "";
  return `<span class="difficulty-tag" style="background:${config.bg}; color:${config.color}; font-size:10px; padding:2px 6px; border-radius:8px; margin-left:6px; border:1px solid ${config.color}">${config.label}</span>`;
}

// Obtenir l'estat de validació i configurar el checkbox
function getValidationState(filename) {
  const status = validations[filename] || "";
  if (status === "approved") {
    return {
      checked: true,
      indeterminate: false,
      className: "validated-approved",
      title: "Aprovat per l'Aniol - Fes clic per tornar a no validat",
    };
  } else if (status === "validated") {
    return {
      checked: true,
      indeterminate: false,
      className: "validated-yes",
      title: "Validat - Fes clic per aprovar",
    };
  } else {
    return {
      checked: false,
      indeterminate: false,
      className: "",
      title: "No validat - Fes clic per validar",
    };
  }
}

// Render inicial
document.addEventListener("DOMContentLoaded", async () => {
  loadSettings(); // Carrega la configuració al iniciar
  renderApp();
  const ok = await ensureAuthenticated();
  if (ok) fetchFiles();
});

function renderApp() {
  const app = document.getElementById("app");
  app.innerHTML = `
    <div class="container py-4">
      <div class="row mb-4">
        <div class="col-12 text-center">
          <h2 class="fw-bold mb-2">Rebuscada.cat - Gestió </h2>
          <div class="d-flex justify-content-center">
            <button class="btn btn-outline-secondary btn-sm" id="settings-btn" title="Configuració general">
              <i class="bi bi-gear"></i> Configuració
            </button>
          </div>
        </div>
      </div>
      <div class="row g-4">
        <div class="col-md-4">
          <div class="paper">
            <h5 class="mb-3">Fitxers</h5>
            <div class="d-flex align-items-center gap-3 mb-2 small">
              <div class="d-flex align-items-center gap-2">
                <input type="checkbox" id="filter-pending" class="form-check-input" />
                <label for="filter-pending" id="filter-pending-label" class="form-check-label" style="cursor:pointer;">Només pendents</label>
              </div>
              <div class="d-flex align-items-center gap-2">
                <input type="checkbox" id="filter-favorites" class="form-check-input" />
                <label for="filter-favorites" id="filter-favorites-label" class="form-check-label" style="cursor:pointer;">Només preferits</label>
              </div>
            </div>
            <ul class="file-list" id="file-list"></ul>
            <div class="d-grid mt-3 gap-2">
              <button class="btn btn-primary" id="create-file" type="button">Crear rànquing…</button>
              <button class="btn btn-outline-primary" id="create-random" type="button" title="Genera 10 paraules aleatòries (pot trigar)">Generar 10 aleatòries…</button>
              <small id="random-status" class="text-muted" style="display:none;">Generant... pot trigar uns segons.</small>
            </div>
          </div>
        </div>
        <div class="col-md-8">
          <div class="paper">
            <div class="d-flex align-items-center justify-content-between mb-2">
              <div class="d-flex align-items-center gap-2">
                <h5 class="mb-0" id="words-title">Paraules</h5>
                <select id="difficulty-selector" class="form-select form-select-sm" style="width:140px; display:none;" title="Dificultat del rànquing">
                  <option value="">No categoritzat</option>
                  <option value="facil">Fàcil</option>
                  <option value="mitja">Mitjà</option>
                  <option value="dificil">Difícil</option>
                </select>
              </div>
              <span id="autosave-status" class="text-muted small" style="display:none;">Desant…</span>
            </div>
            <div class="input-group input-group-sm mb-2">
              <input id="search-word" type="text" class="form-control" placeholder="Cerca paraula..." />
              <button class="btn btn-outline-secondary" id="search-btn" type="button" title="Cerca">Cerca</button>
              <button class="btn btn-outline-success" id="add-new-word-btn" type="button" title="Afegeix una paraula nova al rànquing">+Nou</button>
              <button class="btn btn-outline-info" id="show-test" type="button" title="Mostra paraules test">Test</button>
            </div>
            <div id="words-area" style="min-height:120px;"></div>
            <div id="test-overlay" style="display:none; max-height:330px; overflow:auto; border:1px solid #ddd; border-radius:6px; padding:6px; background:#fff; margin-top:8px;"></div>
          </div>
        </div>
      </div>
      <div id="dialog-root"></div>
      <div id="menu-root"></div>
      <!-- Modal de configuració -->
      <div class="modal fade" id="settingsModal" tabindex="-1" aria-labelledby="settingsModalLabel" aria-hidden="true">
        <div class="modal-dialog">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title" id="settingsModalLabel">Configuració General</h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Tanca"></button>
            </div>
            <div class="modal-body">
              <div class="form-check form-switch">
                <input class="form-check-input" type="checkbox" role="switch" id="autoScrollSwitch">
                <label class="form-check-label" for="autoScrollSwitch">
                  Moviment automàtic de la vista
                </label>
                <div class="form-text">
                  Quan està activat, la vista es mourà automàticament cap a la nova posició de les paraules que es mouen.
                </div>
              </div>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Tanca</button>
              <button type="button" class="btn btn-primary" id="saveSettingsBtn">Desa</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
  bindStaticEvents();
}

function bindStaticEvents() {
  document.getElementById("create-file").onclick = createFile;
  const searchBtn = document.getElementById("search-btn");
  const searchInput = document.getElementById("search-word");
  const testBtn = document.getElementById("show-test");
  const addNewBtn = document.getElementById("add-new-word-btn");
  const filterChk = document.getElementById("filter-pending");
  const favoritesChk = document.getElementById("filter-favorites");
  const settingsBtn = document.getElementById("settings-btn");
  const difficultySelector = document.getElementById("difficulty-selector");

  if (filterChk) {
    filterChk.checked = showOnlyPending;
    filterChk.onchange = () => {
      showOnlyPending = filterChk.checked;
      renderFileList();
    };
  }
  if (favoritesChk) {
    favoritesChk.checked = showOnlyFavorites;
    favoritesChk.onchange = () => {
      showOnlyFavorites = favoritesChk.checked;
      renderFileList();
    };
  }
  if (searchBtn) searchBtn.onclick = () => triggerSearch(searchInput.value);
  if (searchInput) {
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") triggerSearch(searchInput.value);
    });
  }
  if (testBtn) testBtn.onclick = toggleTestOverlay;
  if (addNewBtn) addNewBtn.onclick = promptAddNewWord;
  if (settingsBtn) settingsBtn.onclick = openSettingsModal;

  // Event per al selector de dificultat
  if (difficultySelector) {
    difficultySelector.onchange = () => {
      if (!selected) return;
      const newDifficulty = difficultySelector.value;
      fetch(`${DIFFICULTIES_API}/${selected}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ difficulty: newDifficulty }),
      })
        .then((r) => {
          if (!r.ok) throw new Error();
          if (newDifficulty) {
            difficulties[selected] = newDifficulty;
          } else {
            delete difficulties[selected];
          }
          renderFileList(); // Actualitza la llista per mostrar/amagar etiquetes
        })
        .catch(() => {
          alert("Error desant dificultat");
          updateDifficultySelector(); // Reverteix selector
        });
    };
  }
}

// Funcions per la configuració general
function openSettingsModal() {
  loadSettings(); // Carrega la configuració actual

  // Actualitza l'estat del switch
  const autoScrollSwitch = document.getElementById("autoScrollSwitch");
  if (autoScrollSwitch) {
    autoScrollSwitch.checked = settings.autoScroll;
  }

  // Obre el modal
  const settingsModal = new bootstrap.Modal(
    document.getElementById("settingsModal")
  );
  settingsModal.show();

  // Assigna l'event del botó Desa
  const saveBtn = document.getElementById("saveSettingsBtn");
  if (saveBtn) {
    saveBtn.onclick = saveSettingsFromModal;
  }
}

function saveSettingsFromModal() {
  // Actualitza la configuració amb els valors del modal
  const autoScrollSwitch = document.getElementById("autoScrollSwitch");
  if (autoScrollSwitch) {
    settings.autoScroll = autoScrollSwitch.checked;
  }

  // Desa la configuració
  saveSettings();

  // Tanca el modal
  const settingsModal = bootstrap.Modal.getInstance(
    document.getElementById("settingsModal")
  );
  if (settingsModal) {
    settingsModal.hide();
  }

  // Mostra confirmació
  console.log("Configuració desada:", settings);
}

async function addTestWordsPrompt() {
  const txt = prompt(
    "Paraules a afegir (separa per comes o salts de línia)",
    ""
  );
  if (txt === null) return;
  const parts = txt
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter((s) => s.length);
  if (!parts.length) return;
  try {
    const res = await fetch(`${API_BASE}/test-words`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ words: parts }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Error" }));
      alert(err.detail || "Error afegint");
      return;
    }
    const data = await res.json();
    alert(`Afegides ${data.added.length} (total ${data.total})`);
    refreshTestOverlayIfVisible();
  } catch (e) {
    alert("Error de xarxa");
  }
}

let testVisible = false;
async function toggleTestOverlay() {
  if (!selected) return;
  if (testVisible) {
    hideTestOverlay();
  } else {
    testVisible = true;
    await loadTestOverlayData();
  }
}

function hideTestOverlay() {
  testVisible = false;
  const overlay = document.getElementById("test-overlay");
  if (overlay) {
    overlay.style.display = "none";
    overlay.innerHTML = "";
  }
}

async function loadTestOverlayData() {
  if (!testVisible || !selected) return;
  const overlay = document.getElementById("test-overlay");
  if (!overlay) return;
  overlay.style.display = "block";
  overlay.innerHTML =
    '<div class="text-muted small">Carregant paraules test…</div>';

  try {
    // Carrega tots els tests en paral·lel
    const [commonResponse, aiResponse, synonymsResponse] = await Promise.all([
      fetch(`${RANKINGS_API}/${selected}/test-words`, {
        headers: { ...authHeaders() },
      }),
      fetch(`${RANKINGS_API}/${selected}/test-words-ai`, {
        headers: { ...authHeaders() },
      }).catch(() => null), // No fa error si no existeix el fitxer AI
      fetch(`${RANKINGS_API}/${selected}/test-words-synonyms`, {
        headers: { ...authHeaders() },
      }).catch(() => null), // No fa error si no hi ha sinònims
    ]);

    if (!testVisible) return; // si s'ha tancat mentre carregava

    if (!commonResponse.ok) throw new Error("Error carregant test comú");
    const commonData = await commonResponse.json();

    let aiData = null;
    if (aiResponse && aiResponse.ok) {
      aiData = await aiResponse.json();
    }

    let synonymsData = null;
    if (synonymsResponse && synonymsResponse.ok) {
      synonymsData = await synonymsResponse.json();
    }

    renderTestTabs(commonData, aiData, synonymsData, overlay);
  } catch (e) {
    overlay.innerHTML =
      '<div class="text-danger small">Error carregant test</div>';
  }
}

function renderTestTabs(commonData, aiData, synonymsData, overlay) {
  const hasAiTest = aiData && aiData.words && aiData.words.length > 0;
  const hasSynonymsTest =
    synonymsData && synonymsData.groups && synonymsData.groups.length > 0;

  let tabsHtml = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <div class="btn-group btn-group-sm" role="group">
        <button class="btn btn-outline-primary active" id="tab-common" onclick="switchTestTab('common')">Test Comú (${
          commonData.count
        })</button>
        ${
          hasAiTest
            ? `<button class="btn btn-outline-primary" id="tab-ai" onclick="switchTestTab('ai')">Test IA (${aiData.count})</button>`
            : ""
        }
        ${
          hasSynonymsTest
            ? `<button class="btn btn-outline-primary" id="tab-synonyms" onclick="switchTestTab('synonyms')">SC sinònims (${synonymsData.count})</button>`
            : ""
        }
      </div>
      <div class="btn-group btn-group-sm" role="group">
        <button class="btn btn-outline-success" id="add-test-inside" title="Afegeix paraules al test comú">+Add</button>
        <button class="btn btn-outline-secondary" id="toggle-test-select" title="Mode selecció">Sel</button>
        <button class="btn btn-outline-danger" id="delete-selected-test" style="display:none;" title="Elimina seleccionades">Del</button>
        <button class="btn btn-outline-secondary" id="close-test" title="Tanca">✕</button>
      </div>
    </div>
  `;

  // Contingut de les pestanyes
  const commonRows = commonData.words
    .map((w) => {
      if (w.found) {
        return `<div class="test-row" data-word="${
          w.word
        }" draggable="true" style="cursor: grab;"><span style="color:${colorPerPos(
          w.pos
        )}">${w.word}</span> <a href="#" data-pos="${
          w.pos
        }" class="jump" title="Ves a posició"> (${w.pos})</a></div>`;
      }
      return `<div class="test-row" data-word="${w.word}"><span class="text-muted">${w.word}</span> <span class="jump" style="font-size:11px">(no)</span></div>`;
    })
    .join("");

  let aiRows = "";
  if (hasAiTest) {
    aiRows = aiData.words
      .map((w) => {
        if (w.found) {
          return `<div class="test-row-ai" data-word="${
            w.word
          }" draggable="true" style="cursor: grab;"><span style="color:${colorPerPos(
            w.pos
          )}">${w.word}</span> <a href="#" data-pos="${
            w.pos
          }" class="jump" title="Ves a posició"> (${w.pos})</a></div>`;
        }
        return `<div class="test-row-ai"><span class="text-muted">${w.word}</span> <span class="jump" style="font-size:11px">(no)</span></div>`;
      })
      .join("");
  }

  let synonymsRows = "";
  if (hasSynonymsTest) {
    if (synonymsData.groups && synonymsData.groups.length > 0) {
      synonymsRows = synonymsData.groups
        .map((group, groupIndex) => {
          const groupWords = group.words
            .map((w) => {
              if (w.found) {
                return `<div class="test-row-synonyms" data-word="${
                  w.word
                }" draggable="true" style="cursor: grab;"><span style="color:${colorPerPos(
                  w.pos
                )}">${w.word}</span> <a href="#" data-pos="${
                  w.pos
                }" class="jump" title="Ves a posició"> (${w.pos})</a></div>`;
              }
              return `<div class="test-row-synonyms"><span class="text-muted">${w.word}</span> <span class="jump" style="font-size:11px">(no)</span></div>`;
            })
            .join("");

          return `
            <div class="synonym-group" style="margin-bottom: 12px;">
              <div class="synonym-group-header" style="font-size: 11px; color: #666; margin-bottom: 4px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${group.original_line}">
                ${group.original_line}
              </div>
              <div style="font-size:13px;display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:4px;">
                ${groupWords}
              </div>
            </div>
          `;
        })
        .join("");
    } else {
      synonymsRows =
        '<div class="text-muted small">No s\'han trobat sinònims per aquesta paraula</div>';
    }
  }

  overlay.innerHTML = `
    ${tabsHtml}
    <div id="test-common-content" class="test-tab-content" style="display:block;">
      <div class="test-body" id="test-body" style="font-size:13px;display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:4px;">${commonRows}</div>
    </div>
    ${
      hasAiTest
        ? `
    <div id="test-ai-content" class="test-tab-content" style="display:none;">
      <div class="test-body-ai" id="test-body-ai" style="font-size:13px;display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:4px;">${aiRows}</div>
    </div>`
        : ""
    }
    ${
      hasSynonymsTest
        ? `
    <div id="test-synonyms-content" class="test-tab-content" style="display:none;">
      <div class="test-body-synonyms" id="test-body-synonyms" style="font-size:13px;">${synonymsRows}</div>
    </div>`
        : ""
    }
  `;

  // Assigna events
  const closeBtn = document.getElementById("close-test");
  if (closeBtn) closeBtn.onclick = () => hideTestOverlay();

  const addInside = document.getElementById("add-test-inside");
  if (addInside) addInside.onclick = addTestWordsPrompt;

  initTestWordSelection();

  // Assigna events per saltar a posicions
  overlay.querySelectorAll("a.jump").forEach((a) => {
    a.addEventListener("click", async (e) => {
      e.preventDefault();
      const p = parseInt(a.getAttribute("data-pos"), 10);
      await ensureVisible(p, {
        highlight: true,
        special: true,
        force: p >= PAGE_SIZE,
        forceScroll: true,
      });
    });
  });

  // Assigna events de drag & drop per paraules del test amb posició
  overlay.querySelectorAll("[draggable='true']").forEach((draggableEl) => {
    draggableEl.addEventListener("dragstart", (e) => {
      const word = draggableEl.getAttribute("data-word");
      e.dataTransfer.setData("text/plain", word);
      e.dataTransfer.setData("application/x-test-word", word);
      draggableEl.style.opacity = "0.5";
    });

    draggableEl.addEventListener("dragend", (e) => {
      draggableEl.style.opacity = "1";
    });
  });
}

// Canvia entre pestanyes del test
window.switchTestTab = function (tabName) {
  // Guarda scroll actual de l'overlay per al tab actiu
  const overlay = document.getElementById("test-overlay");
  if (overlay) {
    const activeBtn = document.querySelector(
      "#test-overlay .btn-group button.active"
    );
    let currentTab = testState.activeTab;
    if (activeBtn) {
      const id = activeBtn.id;
      if (id === "tab-common") currentTab = "common";
      else if (id === "tab-ai") currentTab = "ai";
      else if (id === "tab-synonyms") currentTab = "synonyms";
    }
    testState.scrollPositions[currentTab] = overlay.scrollTop || 0;
  }

  // Actualitza botons de pestanya
  document
    .querySelectorAll('#test-overlay .btn-group button[id^="tab-"]')
    .forEach((btn) => {
      btn.classList.remove("active");
    });
  document.getElementById(`tab-${tabName}`).classList.add("active");

  // Mostra/amaga contingut (reset de display dels contenidors)
  document.querySelectorAll(".test-tab-content").forEach((content) => {
    content.style.display = "none";
  });
  document.getElementById(`test-${tabName}-content`).style.display = "block";
  // Restaura overlay.scrollTop per aquest tab
  if (overlay) {
    const saved = testState.scrollPositions[tabName];
    if (saved != null) overlay.scrollTop = saved;
  }

  // Actualitza l'estat
  testState.activeTab = tabName;

  // Actualitza botons d'acció (només per test comú)
  const addBtn = document.getElementById("add-test-inside");
  const selectBtn = document.getElementById("toggle-test-select");
  const deleteBtn = document.getElementById("delete-selected-test");

  const isCommonTab = tabName === "common";
  if (addBtn) addBtn.style.display = isCommonTab ? "inline-block" : "none";
  if (selectBtn)
    selectBtn.style.display = isCommonTab ? "inline-block" : "none";
  if (deleteBtn && tabName !== "common") deleteBtn.style.display = "none";

  // Reinicia la selecció si canviem de pestanya
  if (tabName !== "common") {
    testSelectMode = false;
    selectedTestWords.clear();
    updateTestSelectionUI();
  }
};

// Variables per mantenir l'estat del test durant recarregues
let testState = {
  activeTab: "common",
  // scrollPositions guarda el scroll vertical de l'overlay per cada tab
  scrollPositions: {},
  lastScroll: 0,
};
// Config restauració scroll
const TEST_SCROLL_RESTORE_MAX_ATTEMPTS = 20;
const TEST_SCROLL_RESTORE_INTERVAL = 70; // ms
function attemptOverlayScroll(desired, attempt = 1) {
  const overlay = document.getElementById("test-overlay");
  if (!overlay) return;
  // Si overlay encara no té prou height (offsetHeight ~ clientHeight i scrollHeight petit) seguim intentant
  overlay.scrollTop = desired;
  const done = Math.abs((overlay.scrollTop || 0) - desired) < 3;
  if (done) return;
  if (attempt >= TEST_SCROLL_RESTORE_MAX_ATTEMPTS) return;
  setTimeout(
    () => attemptOverlayScroll(desired, attempt + 1),
    TEST_SCROLL_RESTORE_INTERVAL
  );
}

// Guarda l'estat actual del test abans de recarregar
function saveTestState() {
  if (!testVisible) return;
  const overlay = document.getElementById("test-overlay");
  const activeTabBtn = document.querySelector(
    "#test-overlay .btn-group button.active"
  );
  if (activeTabBtn) {
    const tabId = activeTabBtn.id;
    if (tabId === "tab-common") testState.activeTab = "common";
    else if (tabId === "tab-ai") testState.activeTab = "ai";
    else if (tabId === "tab-synonyms") testState.activeTab = "synonyms";
  }
  if (overlay) {
    const current = overlay.scrollTop || 0;
    testState.scrollPositions[testState.activeTab] = current;
    testState.lastScroll = current;
  }
}

// Restaura l'estat del test després de recarregar
function restoreTestState(desiredOverride) {
  if (!testVisible || !testState.activeTab) return;
  const desired =
    desiredOverride ??
    testState.scrollPositions[testState.activeTab] ??
    testState.lastScroll ??
    0;
  switchTestTab(testState.activeTab); // això rehidrata contingut de la pestanya
  // Cadena d'intents: rAF + setTimeout + loop controlat
  requestAnimationFrame(() => {
    attemptOverlayScroll(desired, 1);
  });
}

function refreshTestOverlayIfVisible() {
  if (!testVisible) return;
  saveTestState();
  const prevActive = testState.activeTab;
  const prevScroll = testState.scrollPositions[prevActive];
  // Afegim classe de placeholder mentre carrega per evitar salt visual
  const overlay = document.getElementById("test-overlay");
  if (overlay) overlay.classList.add("loading-test-refresh");
  loadTestOverlayData().then(() => {
    if (overlay) overlay.classList.remove("loading-test-refresh");
    testState.activeTab = prevActive;
    if (prevScroll != null) testState.scrollPositions[prevActive] = prevScroll;
    restoreTestState(prevScroll);
  });
}

// --- Selecció discreta per eliminar paraules test ---
let testSelectMode = false;
let selectedTestWords = new Set();
function initTestWordSelection() {
  const toggleBtn = document.getElementById("toggle-test-select");
  const delBtn = document.getElementById("delete-selected-test");
  const body = document.getElementById("test-body");
  if (!toggleBtn || !delBtn || !body) return;
  toggleBtn.onclick = () => {
    testSelectMode = !testSelectMode;
    selectedTestWords.clear();
    updateTestSelectionUI();
  };
  delBtn.onclick = async () => {
    if (!selectedTestWords.size) return;
    if (
      !confirm(
        `Eliminar ${selectedTestWords.size} paraules del test? s'esborraran per totes les paraules`
      )
    )
      return;
    try {
      const res = await fetch(`${API_BASE}/test-words/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ words: Array.from(selectedTestWords) }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Error" }));
        alert(err.detail || "Error eliminant");
        return;
      }
      selectedTestWords.clear();
      testSelectMode = false;
      await loadTestOverlayData();
    } catch (e) {
      alert("Error de xarxa");
    }
  };
  body.querySelectorAll(".test-row").forEach((row) => {
    row.addEventListener("click", (e) => {
      if (!testSelectMode) return;
      const text = row.querySelector("span");
      if (!text) return;
      const raw = text.textContent.trim();
      const w = raw.split(/\s+/)[0].replace(/\.$/, "");
      if (selectedTestWords.has(w)) selectedTestWords.delete(w);
      else selectedTestWords.add(w);
      updateTestSelectionUI();
    });
  });
  updateTestSelectionUI();
}
function updateTestSelectionUI() {
  const body = document.getElementById("test-body");
  const toggleBtn = document.getElementById("toggle-test-select");
  const delBtn = document.getElementById("delete-selected-test");
  if (!body || !toggleBtn || !delBtn) return;
  if (!testSelectMode) {
    body.classList.remove("select-mode");
    delBtn.style.display = "none";
    toggleBtn.classList.remove("active");
    body
      .querySelectorAll(".test-row")
      .forEach((r) => r.classList.remove("selected"));
    return;
  }
  toggleBtn.classList.add("active");
  body.classList.add("select-mode");
  delBtn.style.display = selectedTestWords.size ? "inline-block" : "none";
  body.querySelectorAll(".test-row").forEach((r) => {
    const text = r.querySelector("span");
    if (!text) return;
    const w = text.textContent.trim().split(/\s+/)[0].replace(/\.$/, "");
    if (selectedTestWords.has(w)) r.classList.add("selected");
    else r.classList.remove("selected");
  });
}

function fetchFiles() {
  // Carrega llistat, validacions, preferits i dificultats en paral·lel
  Promise.all([
    fetch(RANKINGS_API, { headers: { ...authHeaders() } }).then((r) =>
      r.json()
    ),
    fetch(VALIDATIONS_API, {
      headers: { ...authHeaders() },
    }).then((r) => r.json()),
    fetch(FAVORITES_API, {
      headers: { ...authHeaders() },
    }).then((r) => r.json()),
    fetch(DIFFICULTIES_API, {
      headers: { ...authHeaders() },
    }).then((r) => r.json()),
  ]).then(([flist, vals, favs, diffs]) => {
    files = flist;
    validations = vals || {};
    favorites = favs || {};
    difficulties = diffs || {};
    renderFileList();
  });
}

function renderFileList() {
  const ul = document.getElementById("file-list");
  ul.innerHTML = "";
  files.forEach((f) => {
    const validationStatus = validations[f] || "";
    const isValidated = !!validationStatus; // true if 'validated' or 'approved'
    const isFavorite = !!favorites[f];
    if (showOnlyPending && isValidated) return;
    if (showOnlyFavorites && !isFavorite) return;
    const li = document.createElement("li");
    li.className = "list-item" + (selected === f ? " selected" : "");
    // Nom del fitxer
    const span = document.createElement("span");
    span.style.flex = "1";
    const chkId = `val-${f}`;
    const starId = `fav-${f}`;
    const valState = getValidationState(f);
    const difficulty = difficulties[f] || "";
    const difficultyTag = difficulty ? getDifficultyTag(difficulty) : "";
    span.innerHTML = `
      <input type="checkbox" class="form-check-input me-2 validate-chk ${
        valState.className
      }" id="${chkId}" ${valState.checked ? "checked" : ""} title="${
      valState.title
    }" />
      <button class="star-btn ${
        isFavorite ? "favorite" : ""
      }" id="${starId}" title="Marca com a preferit" type="button">
        <i class="bi ${isFavorite ? "bi-star-fill" : "bi-star"}"></i>
      </button>
      <label for="${chkId}" class="form-check-label" style="cursor:pointer;">${f}</label>
      ${difficultyTag}
    `;
    li.appendChild(span);
    li.onclick = () => loadFile(f);
    // Checkbox toggle amb tres estats (aturar propagació per no carregar el fitxer automàticament)
    const chk = span.querySelector("input");
    chk.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault(); // Prevenim el comportament per defecte per controlar manualment els estats

      const currentStatus = validations[f] || "";
      let newStatus = "";

      // Cicle dels tres estats: no validat -> validat -> aprovat -> no validat
      if (currentStatus === "") {
        newStatus = "validated";
      } else if (currentStatus === "validated") {
        newStatus = "approved";
      } else if (currentStatus === "approved") {
        newStatus = "";
      }

      fetch(`${VALIDATIONS_API}/${f}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ validated: newStatus }),
      })
        .then((r) => {
          if (!r.ok) throw new Error();
          if (newStatus) {
            validations[f] = newStatus;
          } else {
            delete validations[f];
          }
          // Re-renderitza la llista per actualitzar l'aparença
          renderFileList();
          if (showOnlyPending && newStatus) renderFileList();
        })
        .catch(() => {
          alert("Error desant validació");
          renderFileList(); // Reverteix en cas d'error
        });
    });

    // Star button toggle (aturar propagació per no carregar el fitxer automàticament)
    const starBtn = span.querySelector(".star-btn");
    starBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const newVal = !favorites[f];
      fetch(`${FAVORITES_API}/${f}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ favorite: newVal }),
      })
        .then((r) => {
          if (!r.ok) throw new Error();
          if (newVal) {
            favorites[f] = true;
            starBtn.classList.add("favorite");
            starBtn.querySelector("i").className = "bi bi-star-fill";
          } else {
            delete favorites[f];
            starBtn.classList.remove("favorite");
            starBtn.querySelector("i").className = "bi bi-star";
          }
        })
        .catch(() => {
          alert("Error desant preferit");
        });
    });

    // Play button amb icona Bootstrap
    const play = document.createElement("button");
    play.className = "icon-btn";
    play.title = "Juga amb aquesta paraula";
    play.innerHTML = '<i class="bi bi-play-circle"></i>';
    play.onclick = (e) => {
      e.stopPropagation();
      // Extreu la paraula sense l'extensió .json i la codifica en Base64
      const word = f.replace(/\.json$/, "");
      const wordBase64 = btoa(word);
      const gameUrl = `http://5.250.190.223/?word=${wordBase64}`;
      window.open(gameUrl, "_blank", "noopener");
    };
    li.appendChild(play);

    // Delete button amb icona Bootstrap
    const del = document.createElement("button");
    del.className = "icon-btn";
    del.title = "Esborra";
    del.innerHTML = '<i class="bi bi-trash"></i>';
    del.onclick = (e) => {
      e.stopPropagation();
      showDeleteDialog(f);
    };
    li.appendChild(del);
    ul.appendChild(li);
  });
}

// ==================== FUNCIONS DE COMENTARIS ====================

// Carrega els comentaris d'un fitxer
async function loadComments(filename) {
  try {
    const res = await fetch(`${RANKINGS_API}/${filename}/comments`, {
      headers: { ...authHeaders() },
    });
    if (!res.ok) throw new Error();
    comments = await res.json();
  } catch (e) {
    comments = { global: "", words: {} };
  }
  updateCommentIndicators();
}

// Actualitza els indicadors de comentaris a la UI
function updateCommentIndicators() {
  updateGlobalCommentIcon();
  renderWordsArea(); // Re-renderitza per mostrar indicadors de paraules
}

// Actualitza la icona de comentari global
function updateGlobalCommentIcon() {
  const selector = document.getElementById("difficulty-selector");
  if (!selector) return;

  // Elimina icona existent si n'hi ha
  let icon = document.getElementById("global-comment-icon");
  if (icon) icon.remove();

  if (!selected) return;

  // Comprova si hi ha qualsevol comentari (global o de paraules)
  const hasGlobalComment = comments.global && comments.global.trim() !== "";
  const hasWordComments =
    comments.words && Object.keys(comments.words).length > 0;
  const hasAnyComment = hasGlobalComment || hasWordComments;

  // Crea la icona
  icon = document.createElement("button");
  icon.id = "global-comment-icon";
  icon.className = "icon-btn comment-icon-btn";

  // Actualitza el títol segons el tipus de comentaris
  if (hasGlobalComment && hasWordComments) {
    icon.title = "Comentari global i comentaris de paraules (clic per veure)";
  } else if (hasGlobalComment) {
    icon.title = "Comentari global (clic per editar)";
  } else if (hasWordComments) {
    icon.title = "Comentaris de paraules (clic per veure)";
  } else {
    icon.title = "Afegir comentari global";
  }

  icon.innerHTML = hasAnyComment
    ? '<i class="bi bi-chat-left-text-fill" style="color:#ff6800;"></i>'
    : '<i class="bi bi-chat-left"><span class="plus-sign">+</span></i>';

  icon.onclick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    openCommentModal("global", null);
  };

  // Insereix després del selector
  selector.parentNode.insertBefore(icon, selector.nextSibling);
}

// Obre el modal de comentaris
function openCommentModal(type, word = null) {
  const isGlobal = type === "global";
  const currentComment = isGlobal
    ? comments.global
    : (comments.words && comments.words[word]) || "";
  const title = isGlobal ? "Comentari Global del Fitxer" : `Comentari: ${word}`;

  // Genera el resum de comentaris de paraules (només per al modal global)
  let wordCommentsSection = "";
  if (isGlobal && comments.words && Object.keys(comments.words).length > 0) {
    const wordCommentsHtml = Object.entries(comments.words)
      .map(([wordKey, commentText]) => {
        // Troba la posició de la paraula en wordsByPos
        let pos = null;
        for (const [p, w] of Object.entries(wordsByPos)) {
          if (w.word === wordKey) {
            pos = parseInt(p);
            break;
          }
        }

        const color = pos !== null ? colorPerPos(pos) : "#999";
        const posLabel = pos !== null ? `${pos}. ` : "";

        return `
          <div class="word-comment-item" data-word="${wordKey}">
            <span class="word-comment-label" style="color: ${color}; font-weight: 500; cursor: pointer;">
              ${posLabel}${wordKey}
            </span>
            <span class="word-comment-text" style="cursor: pointer;">
              ${commentText}
            </span>
          </div>
        `;
      })
      .join("");

    wordCommentsSection = `
      <div class="word-comments-summary">
        <h6 class="word-comments-title">Comentaris de paraules</h6>
        <div class="word-comments-list">
          ${wordCommentsHtml}
        </div>
      </div>
    `;
  }

  const modalHtml = `
    <div class="modal fade" id="commentModal" tabindex="-1" aria-labelledby="commentModalLabel" aria-hidden="true">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title" id="commentModalLabel">${title}</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Tanca"></button>
          </div>
          <div class="modal-body">
            <textarea class="form-control" id="comment-textarea" rows="5" placeholder="Escriu el comentari aquí...">${currentComment}</textarea>
          </div>
          <div class="modal-footer">
            ${
              currentComment
                ? '<button type="button" class="btn btn-danger me-auto" id="delete-comment-btn">Esborra</button>'
                : ""
            }
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel·la</button>
            <button type="button" class="btn btn-primary" id="save-comment-btn">Desa</button>
          </div>
          ${wordCommentsSection}
        </div>
      </div>
    </div>
  `;

  // Elimina modal anterior si existeix
  const oldModal = document.getElementById("commentModal");
  if (oldModal) oldModal.remove();

  // Afegeix modal al DOM
  document.body.insertAdjacentHTML("beforeend", modalHtml);

  const modalEl = document.getElementById("commentModal");
  const modal = new bootstrap.Modal(modalEl);

  // Event per desar
  document.getElementById("save-comment-btn").onclick = async () => {
    const textarea = document.getElementById("comment-textarea");
    const newComment = textarea.value.trim();
    await saveComment(isGlobal, word, newComment);
    modal.hide();
  };

  // Event per esborrar (si hi ha comentari)
  const deleteBtn = document.getElementById("delete-comment-btn");
  if (deleteBtn) {
    deleteBtn.onclick = async () => {
      if (!confirm("Segur que vols esborrar aquest comentari?")) return;
      await deleteComment(isGlobal, word);
      modal.hide();
    };
  }

  // Event listeners per als comentaris de paraules (només en modal global)
  if (isGlobal) {
    const wordCommentItems = modalEl.querySelectorAll(".word-comment-item");
    wordCommentItems.forEach((item) => {
      item.addEventListener("click", (e) => {
        e.preventDefault();
        const wordKey = item.getAttribute("data-word");
        modal.hide(); // Tanca el modal actual
        // Espera a que el modal es tanqui abans d'obrir el nou
        setTimeout(() => {
          openCommentModal("word", wordKey);
        }, 300);
      });
    });
  }

  // Neteja el modal del DOM quan es tanca
  modalEl.addEventListener("hidden.bs.modal", () => {
    modalEl.remove();
  });

  modal.show();
}

// Desa un comentari (global o de paraula)
async function saveComment(isGlobal, word, comment) {
  if (!selected) return;

  try {
    let endpoint, body;
    if (isGlobal) {
      endpoint = `${RANKINGS_API}/${selected}/comments/global`;
      body = { comment };
    } else {
      endpoint = `${RANKINGS_API}/${selected}/comments/word`;
      body = { word, comment };
    }

    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
    });

    if (!res.ok) throw new Error();

    // Actualitza l'estat local
    if (isGlobal) {
      comments.global = comment;
    } else {
      if (!comments.words) comments.words = {};
      if (comment) {
        comments.words[word] = comment;
      } else {
        delete comments.words[word];
      }
    }

    updateCommentIndicators();
  } catch (e) {
    alert("Error desant el comentari");
  }
}

// Esborra un comentari (global o de paraula)
async function deleteComment(isGlobal, word) {
  if (!selected) return;

  try {
    let endpoint;
    if (isGlobal) {
      endpoint = `${RANKINGS_API}/${selected}/comments/global`;
    } else {
      endpoint = `${RANKINGS_API}/${selected}/comments/word/${encodeURIComponent(
        word
      )}`;
    }

    const res = await fetch(endpoint, {
      method: "DELETE",
      headers: { ...authHeaders() },
    });

    if (!res.ok) throw new Error();

    // Actualitza l'estat local
    if (isGlobal) {
      comments.global = "";
    } else {
      if (comments.words) {
        delete comments.words[word];
      }
    }

    updateCommentIndicators();
  } catch (e) {
    alert("Error esborrant el comentari");
  }
}

// ==================== FI FUNCIONS DE COMENTARIS ====================

function loadFile(filename) {
  selected = filename;
  wordsByPos = {};
  dirty = false;
  loading = true;
  lastMoveInfo = null;
  renderFileList();
  renderWordsArea();
  updateWordsTitle(); // Actualitza títol en carregar fitxer
  updateDifficultySelector(); // Actualitza selector de dificultat
  loadComments(filename); // Carrega comentaris del fitxer
  fetch(`${RANKINGS_API}/${filename}?offset=0&limit=${PAGE_SIZE}`, {
    headers: { ...authHeaders() },
  })
    .then((res) => res.json())
    .then((data) => {
      data.words.forEach((w) => (wordsByPos[w.pos] = w));
      total = data.total;
      loading = false;
      renderWordsArea();
      updateWordsTitle(); // Actualitza títol després de carregar dades
      updateDifficultySelector(); // Actualitza selector després de carregar dades
      refreshTestOverlayIfVisible();
    });
}

// Actualitza el títul amb la paraula en posició 0
function updateWordsTitle() {
  const titleEl = document.getElementById("words-title");
  if (!titleEl) return;

  if (!selected) {
    titleEl.textContent = "Paraules";
    return;
  }

  // Si tenim la paraula en posició 0 carregada, l'utilitzem
  if (wordsByPos[0] && wordsByPos[0].word) {
    titleEl.textContent = `Paraules - ${wordsByPos[0].word}`;
  } else {
    titleEl.textContent = "Paraules";
  }
}

// Actualitza el selector de dificultat
function updateDifficultySelector() {
  const selector = document.getElementById("difficulty-selector");
  if (!selector) return;

  if (!selected) {
    selector.style.display = "none";
    return;
  }

  selector.style.display = "block";
  const currentDifficulty = difficulties[selected] || "";
  selector.value = currentDifficulty;
}

function renderWordsArea() {
  const area = document.getElementById("words-area");
  // Guarda scroll actual (si existeix llista) per evitar saltar a l'esquerra en re-render
  let prevScrollLeft = 0;
  let prevScrollTop = 0;
  const existingList = area.querySelector(".word-list");
  if (existingList) {
    prevScrollLeft = existingList.scrollLeft;
    prevScrollTop = existingList.scrollTop;
  }
  area.innerHTML = "";
  updateWordsTitle(); // Actualitza títol sempre que es renderitza
  updateDifficultySelector(); // Actualitza selector sempre que es renderitza
  if (!selected) {
    area.innerHTML =
      '<div style="color:#888">Selecciona un fitxer per veure les paraules.</div>';
    return;
  }
  if (loading) {
    area.innerHTML =
      '<div style="text-align:center;padding:32px"><span>Carregant...</span></div>';
    return;
  }
  const wordList = document.createElement("div");
  wordList.className = "word-list";
  const positions = Object.keys(wordsByPos)
    .map(Number)
    .sort((a, b) => a - b);
  let contiguousEnd = 0; // primer index no carregat començant per 0
  while (wordsByPos[contiguousEnd]) contiguousEnd++;

  const createWordItem = (pos) => {
    const w = wordsByPos[pos];
    const item = document.createElement("div");
    const isFirst = pos === 0;
    const draggableAllowed = !isFirst && pos < contiguousEnd;
    item.className = "word-item" + (draggableAllowed ? " draggable" : "");
    const txt = document.createElement("span");
    txt.className = "word-text";
    txt.textContent = `${pos}. ${w.word}`;
    txt.title = `${pos}. ${w.word}`;
    txt.style.color = colorPerPos(pos);
    item.appendChild(txt);

    if (!isFirst) {
      const menuBtn = document.createElement("button");
      menuBtn.className = "icon-btn";

      // Afegeix indicador de comentari si la paraula té comentari
      const hasWordComment = comments.words && comments.words[w.word];
      let menuBtnHtml = "";

      if (hasWordComment) {
        menuBtnHtml =
          '<span class="word-comment-indicator" title="Aquesta paraula té comentari"><i class="bi bi-chat-left-text-fill" style="color: #818181;font-size:10px;"></i></span> ';
      }

      menuBtnHtml += '<i class="bi bi-three-dots-vertical"></i>';
      menuBtn.innerHTML = menuBtnHtml;

      menuBtn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        showMenu(e, pos);
      };
      menuBtn.onmousedown = (e) => e.stopPropagation();
      item.appendChild(menuBtn);
    }
    if (draggableAllowed) {
      item.draggable = true;
      item.addEventListener("dragstart", (e) => onDragStart(e, pos, item));
      item.addEventListener("dragend", (e) => onDragEnd(e, item));
      item.addEventListener("dragover", (e) => onDragOver(e, pos, item));
      item.addEventListener("drop", (e) => onDrop(e, pos, item));
    } else if (isFirst) {
      item.style.height = "38px";
      item.style.minHeight = "38px";
      item.style.display = "flex";
    }
    return item;
  };
  const appendGapButton = (start, endKnown) => {
    const item = document.createElement("div");
    item.className = "word-item";
    const btn = document.createElement("button");
    btn.className = "btn btn-outline-secondary btn-sm w-100";
    btn.textContent =
      endKnown !== null ? `més [${start}-${endKnown}]` : `més [${start}...]`;
    btn.onclick = (e) => {
      e.preventDefault();
      loadMoreGap(start, endKnown);
    };
    item.appendChild(btn);
    wordList.appendChild(item);
  };
  let cursor = 0;
  while (cursor < total) {
    if (wordsByPos[cursor]) {
      wordList.appendChild(createWordItem(cursor));
      cursor++;
      continue;
    }
    let nextLoaded = null;
    for (let p of positions) {
      if (p > cursor) {
        nextLoaded = p;
        break;
      }
    }
    const endKnown = nextLoaded !== null ? nextLoaded - 1 : null;
    appendGapButton(cursor, endKnown);
    if (nextLoaded === null) break;
    cursor = nextLoaded;
  }
  area.appendChild(wordList);
  // Restaura scroll
  wordList.scrollLeft = prevScrollLeft;
  wordList.scrollTop = prevScrollTop;
  // Indicador d'últim moviment si la posició no està carregada
  if (lastMoveInfo && selected && !wordsByPos[lastMoveInfo.toPos]) {
    const indicator = document.createElement("div");
    indicator.className = "move-indicator";
    indicator.innerHTML = `
      <div class="alert alert-info p-2 mt-2 mb-0" style="cursor:pointer;">
        Paraula moguda a posició ${lastMoveInfo.toPos}. Fes clic per mostrar-la.
      </div>`;
    indicator.onclick = () =>
      ensureVisible(lastMoveInfo.toPos, { highlight: true, special: true });
    area.appendChild(indicator);
  }
  // Botó de desar
  // ja no cal botó; auto-save
}

// Drag & drop
let dragIdx = null;
function onDragStart(e, pos, item) {
  dragIdx = pos;
  e.dataTransfer.effectAllowed = "move";
  setTimeout(() => item.classList.add("dragging"), 0);
}
function onDragEnd(e, item) {
  dragIdx = null;
  item.classList.remove("dragging");
  // Eliminar qualsevol drag-over restant
  document
    .querySelectorAll(".word-item.drag-over")
    .forEach((el) => el.classList.remove("drag-over"));
}
function onDragOver(e, pos, item) {
  e.preventDefault();

  // Permet drop de paraules del test o drag & drop normal
  const testWord = e.dataTransfer.getData("application/x-test-word");
  if (
    testWord ||
    (dragIdx !== null && dragIdx !== 0 && pos !== 0 && dragIdx !== pos)
  ) {
    document
      .querySelectorAll(".word-item.drag-over")
      .forEach((el) => el.classList.remove("drag-over"));
    item.classList.add("drag-over");
  }
}
function onDrop(e, pos, item) {
  e.preventDefault();

  // Comprova si és una paraula del test
  const testWord = e.dataTransfer.getData("application/x-test-word");
  if (testWord) {
    // És una paraula arrossegada des d'un test
    insertWordFromTest(testWord, pos);
    return;
  }

  // Drag & drop normal dins de la llista
  if (dragIdx === null || dragIdx === 0 || pos === 0 || dragIdx === pos) return;

  const fromIndex = dragIdx;
  const toIndex = pos;
  dragIdx = null;

  // Paraula a moure (pot no estar carregada si s'ha mogut prèviament), obtenim del bloc si existeix
  const wObj = wordsByPos[fromIndex];
  if (!wObj) {
    // Fallback: recarrega bloc inicial i surt
    reloadInitialBlock();
    return;
  }
  // Desa estat (scroll test) abans d'actualitzar
  saveTestState();
  unifiedInsertOrMove(wObj.word, toIndex, {
    highlight: true,
    fromPos: fromIndex,
  });
}

// Insereix una paraula del test a una posició específica
async function insertWordFromTest(word, targetPos) {
  if (!word || targetPos === 0) return;
  saveTestState();
  unifiedInsertOrMove(word, targetPos, { highlight: true });
}

// Funció unificada per inserir o moure una paraula al rànquing
async function unifiedInsertOrMove(word, toPos, options = {}) {
  if (!selected) return;
  const { highlight = false, fromPos = null } = options;
  try {
    const res = await fetch(`${RANKINGS_API}/${selected}/insert-or-move`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ word, to_pos: toPos }),
    });
    if (!res.ok) throw new Error("Error inserint/movent");
    const data = await res.json();
    total = data.total;
    // Recarrega bloc inicial per mantenir coherència (no marquem dirty: backend ja és font de veritat)
    const changedPos = fromPos != null ? Math.min(fromPos, data.to) : data.to;
    await reloadInitialBlock();
    // Recarrega les posicions carregades superiors afectades pel desplaçament
    await refreshLoadedAfter(changedPos + 1);
    if (highlight) highlightMovedWord(data.to, data.action === "inserted");
    refreshTestOverlayIfVisible();
  } catch (e) {
    console.error("unifiedInsertOrMove error", e);
    alert("No s'ha pogut actualitzar el rànquing");
  }
}

function highlightMovedWord(pos, special) {
  setTimeout(() => {
    const wordItems = document.querySelectorAll(".word-item");
    wordItems.forEach((el) => {
      if (
        el.firstChild &&
        el.firstChild.textContent &&
        el.firstChild.textContent.startsWith(`${pos}.`)
      ) {
        tempHighlightElement(el, 1500, special ? "moved-special" : "moved");
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
  }, 0);
}

// Recarrega (refetch) els trams contigus ja carregats amb posició >= startPos
async function refreshLoadedAfter(startPos) {
  // Detecta rangs contigus de posicions carregades >= startPos (excloent les < PAGE_SIZE perquè ja s'han refrescat)
  const loaded = Object.keys(wordsByPos)
    .map(Number)
    .filter((p) => p >= startPos)
    .sort((a, b) => a - b);
  if (!loaded.length) return;
  const ranges = [];
  let rangeStart = loaded[0];
  let prev = loaded[0];
  for (let i = 1; i < loaded.length; i++) {
    const p = loaded[i];
    if (p === prev + 1) {
      prev = p;
      continue;
    }
    ranges.push([rangeStart, prev]);
    rangeStart = p;
    prev = p;
  }
  ranges.push([rangeStart, prev]);
  for (const [a, b] of ranges) {
    const len = b - a + 1;
    try {
      const res = await fetch(
        `${RANKINGS_API}/${selected}?offset=${a}&limit=${len}`,
        { headers: { ...authHeaders() } }
      );
      const data = await res.json();
      if (data.words) data.words.forEach((w) => (wordsByPos[w.pos] = w));
    } catch (_) {
      // ignore errors individuals
    }
  }
  renderWordsArea();
}

// Menú contextual
function showMenu(e, pos) {
  e.preventDefault();
  closeMenu();
  menuIdx = pos; // posició absoluta
  menuAnchor = { x: e.clientX, y: e.clientY };
  const menuRoot = document.getElementById("menu-root");
  const menu = document.createElement("div");
  menu.className = "menu";
  menu.style.left = menuAnchor.x + "px";
  menu.style.top = menuAnchor.y + "px";
  // Construïm menú amb opcions bàsiques + moviments ràpids
  const quickTargets = [300, 1500, 3000];
  const w = wordsByPos[pos];
  const hasComment = w && comments.words && comments.words[w.word];

  let html = `
    <div class="menu-item" id="comment-word">${
      hasComment ? "Comentar-ho amb el company" : "Afegir comentari"
    }</div>
    <div class="menu-item" id="move-to">Mou a posició…</div>
    <div class="menu-item" id="move-end">Mou al final</div>
  `;
  quickTargets.forEach((t) => {
    if (total > t) {
      html += `<div class="menu-item quick-move" data-target="${t}">Mou a ${t}</div>`;
    }
  });
  html += `<div class=\"menu-item\" id=\"open-dict\">Cerca al diccionari</div>`;
  html += `<div class="menu-item" id="delete-word" style="color:#c62828;">Elimina paraula…</div>`;
  menu.innerHTML = html;
  menuRoot.appendChild(menu);

  document.getElementById("comment-word").onclick = (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    if (menuIdx != null) {
      const wObj = wordsByPos[menuIdx];
      if (wObj && wObj.word) {
        openCommentModal("word", wObj.word);
      }
    }
    closeMenu();
  };

  document.getElementById("move-to").onclick = (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    handleMoveToPrompt();
    closeMenu();
  };
  document.getElementById("move-end").onclick = (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    handleSendToEndMenu();
    closeMenu();
  };
  document.getElementById("delete-word").onclick = (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    handleDeleteWord();
    closeMenu();
  };
  const openDict = document.getElementById("open-dict");
  if (openDict) {
    openDict.onclick = (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      if (menuIdx != null) {
        const wObj = wordsByPos[menuIdx];
        if (wObj && wObj.word) {
          const url = DICT_URL_TEMPLATE.replace(
            "[PARAULA]",
            encodeURIComponent(wObj.word)
          );
          window.open(url, "_blank", "noopener");
        }
      }
      closeMenu();
    };
  }
  // Enllaça moviments ràpids
  menu.querySelectorAll(".quick-move").forEach((el) => {
    el.addEventListener("click", async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const targetRaw = parseInt(el.getAttribute("data-target"), 10);
      const target = Math.min(total - 1, targetRaw);
      if (menuIdx === null || target === menuIdx) {
        closeMenu();
        return;
      }
      await moveAbsolute(menuIdx, target);
      closeMenu();
      await reloadInitialBlock();
      await ensureVisible(target, {
        highlight: true,
        special: true,
        force: target >= PAGE_SIZE,
      });
      refreshTestOverlayIfVisible();
    });
  });
  // Només tanca el menú si es fa clic fora
  setTimeout(() => {
    // Abans era 'mousedown' i es tancava el menú abans que es disparessin els onClick dels ítems.
    // Amb 'click' el listener del document s'executa DESPRÉS del click sobre l'element de menú,
    // permetent que les accions (moure / enviar al final) funcionin.
    document.addEventListener("click", closeMenu, { once: true });
  }, 0);
}
function closeMenu() {
  const menuRoot = document.getElementById("menu-root");
  menuRoot.innerHTML = "";
  menuIdx = null;
  menuAnchor = null;
}
async function handleMoveToPrompt() {
  if (menuIdx === null) return closeMenu();
  const absoluteFrom = menuIdx;
  let posStr = prompt(
    `A quina posició vols moure aquesta paraula? (0 - ${total - 1})`,
    ""
  );
  if (posStr === null) return closeMenu();
  let target = parseInt(posStr, 10);
  if (isNaN(target) || target < 0) target = 0;
  if (target >= total) target = total - 1;
  if (target === absoluteFrom) return closeMenu();
  await moveAbsolute(absoluteFrom, target);
  closeMenu();
  await reloadInitialBlock();
  await ensureVisible(target, {
    highlight: true,
    special: true,
    force: target >= PAGE_SIZE,
  });
  refreshTestOverlayIfVisible();
}
async function handleSendToEndMenu() {
  if (menuIdx === null) return closeMenu();
  const absoluteFrom = menuIdx;
  const target = total - 1;
  if (target === absoluteFrom) return closeMenu();
  await moveAbsolute(absoluteFrom, target);
  closeMenu();
  await reloadInitialBlock();
  await ensureVisible(target, {
    highlight: true,
    special: true,
    force: target >= PAGE_SIZE,
  });
  refreshTestOverlayIfVisible();
}

async function handleDeleteWord() {
  if (menuIdx === null) return;
  const pos = menuIdx;
  if (!selected) return;
  const wordObj = wordsByPos[pos];
  const wordLabel = wordObj ? wordObj.word : `posició ${pos}`;
  const confirmMsg = `Segur que vols eliminar la paraula '${wordLabel}' de la llista? en cercar aquesta paraula aquell dia sortirà com a no present al diccionari.`;
  if (!confirm(confirmMsg)) return;
  try {
    const res = await fetch(`${RANKINGS_API}/${selected}/word/${pos}`, {
      method: "DELETE",
      headers: { ...authHeaders() },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Error eliminant paraula");
    }
    const data = await res.json();
    // Actualitza estat local: elimina la paraula i reindexa si cal el bloc inicial carregat
    // Eliminem totes les posicions carregades >= pos fins trobar un forat i refetch fragment inicial
    // Estratègia simple: recarregar bloc inicial i mantenir la resta (es podria optimitzar)
    await reloadInitialBlock();
    total = data.total;
    // Si la paraula eliminada era part de lastMoveInfo, neteja
    if (lastMoveInfo && lastMoveInfo.toPos === pos) lastMoveInfo = null;
    renderWordsArea();
    // Una eliminació no necessita desat addicional (ja està persistit), però marquem estat
    showAutoSaveDone();
    refreshTestOverlayIfVisible();
  } catch (e) {
    alert(e.message);
  }
}

async function moveAbsolute(fromPos, toPos) {
  const res = await fetch(`${RANKINGS_API}/${selected}/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ from_pos: fromPos, to_pos: toPos }),
  });
  try {
    const data = await res.json();
    if (data && data.word !== undefined && data.to !== undefined) {
      lastMoveInfo = { word: data.word, toPos: data.to };
    }
  } catch (_) {
    // ignore JSON parse errors
  }
  // Elimina la paraula de la posició antiga si la tenim carregada per evitar duplicats visuals
  if (fromPos !== toPos && wordsByPos[fromPos]) {
    delete wordsByPos[fromPos];
  }
  // El moviment ja s'ha desat al backend; no cal marcar dirty.
}

async function reloadInitialBlock() {
  const res = await fetch(
    `${RANKINGS_API}/${selected}?offset=0&limit=${PAGE_SIZE}`,
    {
      headers: { ...authHeaders() },
    }
  );
  const data = await res.json();
  // REFRESH PARCIAL: Només actualitzem el primer bloc (0..PAGE_SIZE-1)
  // Abans eliminàvem TOT el tram contigu començant per 0 fins trobar un forat, cosa que
  // podia incloure posicions > PAGE_SIZE si l'usuari havia carregat més blocs (ex: 0..599).
  // Això feia desaparèixer les paraules >300 després de moure'n una i forçar reload.
  // Ara només eliminem i substituïm les posicions < PAGE_SIZE i preservem la resta.
  Object.keys(wordsByPos).forEach((k) => {
    const p = parseInt(k, 10);
    if (p < PAGE_SIZE) delete wordsByPos[p];
  });
  data.words.forEach((w) => (wordsByPos[w.pos] = w));
  total = data.total;
  renderWordsArea();
  updateWordsTitle(); // Actualitza títol després de recarregar
  refreshTestOverlayIfVisible();
}

// options: {highlight, force, special, forceScroll}
async function ensureVisible(pos, options = {}) {
  const {
    highlight = false,
    force = false,
    special = false,
    forceScroll = false,
  } = options;

  // Comprova si el moviment automàtic està desactivat, però permet forceScroll
  if (!settings.autoScroll && !forceScroll) {
    return; // No fa res si el moviment automàtic està desactivat i no és un forceScroll
  }

  if (force && wordsByPos[pos]) delete wordsByPos[pos];
  const applyHighlight = () => {
    if (!highlight) return;
    setTimeout(() => {
      const wordItems = document.querySelectorAll(".word-item");
      wordItems.forEach((el) => {
        if (
          el.firstChild &&
          el.firstChild.textContent &&
          el.firstChild.textContent.startsWith(`${pos}.`)
        ) {
          tempHighlightElement(el, 1500, special ? "moved-special" : "moved");
          el.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      });
    }, 0);
  };
  if (wordsByPos[pos]) {
    applyHighlight();
    return;
  }
  const res = await fetch(`${RANKINGS_API}/${selected}?offset=${pos}&limit=1`, {
    headers: { ...authHeaders() },
  });
  const data = await res.json();
  if (data.words && data.words[0])
    wordsByPos[data.words[0].pos] = data.words[0];
  renderWordsArea();
  if (highlight && !force)
    await ensureVisible(pos, { highlight: true, special, forceScroll });
  else applyHighlight();
}

// Crear fitxer
function createFile() {
  const paraula = prompt(
    "Paraula per generar rànquing (pot tardar una estona):",
    ""
  );
  if (paraula === null) return; // cancel·lat

  // Desactivat el server per falta de ram
  alert("Uoops... ara mateix no és possible parla amb l'Aniol");
  return;

  const cleaned = paraula.trim().toLowerCase();
  if (!cleaned) return;
  // Crida endpoint de generació
  // Fem servir endpoint alternatiu per evitar confusions amb path params
  fetch(GENERATE_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ word: cleaned }),
  })
    .then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Error generant rànquing");
      }
      return res.json();
    })
    .then((data) => {
      const filename = data.filename;
      if (!files.includes(filename)) files.push(filename);
      renderFileList();
    })
    .catch((e) => alert(e.message));
}

function createRandom() {
  if (
    !confirm(
      "Generar 10 rànquings pot trigar força (fastText). Vols continuar?"
    )
  )
    return;

  // Desactivat el server per falta de ram
  alert("Uoops... ara mateix no és possible parla amb l'Aniol");
  return;

  const statusEl = document.getElementById("random-status");
  statusEl.style.display = "block";
  statusEl.textContent = "Generant 10 paraules aleatòries...";
  fetch(GENERATE_RANDOM_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ count: 10 }),
  })
    .then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Error generant rànquings aleatoris");
      }
      return res.json();
    })
    .then((data) => {
      data.generated.forEach((g) => {
        if (!files.includes(g.filename)) files.push(g.filename);
      });
      renderFileList();
      statusEl.textContent = `Generats ${data.count} fitxers.`;
      setTimeout(() => (statusEl.style.display = "none"), 4000);
    })
    .catch((e) => {
      statusEl.textContent = e.message;
      setTimeout(() => (statusEl.style.display = "none"), 4000);
    });
}

// Assignem l'event després de renderitzar
document.addEventListener("DOMContentLoaded", () => {
  const rndBtn = document.getElementById("create-random");
  if (rndBtn) rndBtn.onclick = createRandom;
  const searchBtn = document.getElementById("search-btn");
  const searchInput = document.getElementById("search-word");
  if (searchBtn && searchInput)
    searchBtn.onclick = () => triggerSearch(searchInput.value);
  if (searchInput) {
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") triggerSearch(searchInput.value);
    });
  }
});

// Esborrar fitxer
function showDeleteDialog(filename) {
  confirmDelete = filename;
  renderDialog();
}
function renderDialog() {
  const root = document.getElementById("dialog-root");
  if (!confirmDelete) {
    root.innerHTML = "";
    return;
  }
  root.innerHTML = `
		<div class="dialog-backdrop">
			<div class="dialog">
				<div style="margin-bottom:16px;">Segur que vols esborrar el fitxer?</div>
				<div style="display:flex;justify-content:flex-end;gap:8px;">
					<button class="button" id="cancel-del">Cancel·la</button>
					<button class="button warning" id="confirm-del">Esborra</button>
				</div>
			</div>
		</div>
	`;
  document.getElementById("cancel-del").onclick = () => {
    confirmDelete = null;
    renderDialog();
  };
  document.getElementById("confirm-del").onclick = () =>
    deleteFile(confirmDelete);
}
function deleteFile(filename) {
  fetch(`${RANKINGS_API}/${filename}`, {
    method: "DELETE",
    headers: { ...authHeaders() },
  }).then(() => {
    files = files.filter((f) => f !== filename);
    if (selected === filename) {
      selected = null;
      words = [];
    }
    confirmDelete = null;
    renderFileList();
    renderWordsArea();
    renderDialog();
  });
}

// Guardar fitxer
function saveFile() {
  // NOMÉS desa si hi ha canvis i un fitxer seleccionat
  if (!selected || !dirty) return;

  // Detecta el bloc contigu inicial carregat (0..contiguousEnd-1)
  let contiguousEnd = 0;
  while (wordsByPos[contiguousEnd]) contiguousEnd++;

  // IMPORTANT: No podem sobreescriure tot el fitxer només amb aquest bloc
  // perquè perdríem la resta de paraules. Usem el mode "fragment" del backend
  // que actualitza només aquest tram mantenint la resta intacta.
  // L'endpoint interpreta l'ordre de les CLAUS del fragment; els valors s'ignoren.
  const fragment = {};
  for (let i = 0; i < contiguousEnd; i++) {
    fragment[wordsByPos[i].word] = i; // valor informatiu (no utilitzat pel backend)
  }

  const status = document.getElementById("autosave-status");
  if (status) {
    status.style.display = "inline";
    status.textContent = "Desant…";
  }

  fetch(`${RANKINGS_API}/${selected}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ fragment, offset: 0 }),
  })
    .then((r) => {
      if (!r.ok) throw new Error();
      dirty = false;
      showAutoSaveDone();
      refreshTestOverlayIfVisible();
    })
    .catch(() => {
      if (status) {
        status.style.display = "inline";
        status.textContent = "Error desant";
      }
    });
}

function scheduleAutoSave() {
  if (!dirty) return; // res a desar
  if (autoSaveTimer) clearTimeout(autoSaveTimer);
  autoSaveTimer = setTimeout(() => {
    saveFile();
  }, AUTO_SAVE_DELAY);
  const status = document.getElementById("autosave-status");
  if (status) {
    status.style.display = "inline";
    status.textContent = "Pendents de desar…";
  }
}

function showAutoSaveDone() {
  const status = document.getElementById("autosave-status");
  if (status) {
    status.style.display = "inline";
    status.textContent = "Desat";
    setTimeout(() => {
      if (status.textContent === "Desat") status.style.display = "none";
    }, 2000);
  }
}

// Carregar més paraules
function loadMoreGap(start, endKnown) {
  if (!selected) return;
  let limit = PAGE_SIZE;
  if (endKnown !== null) {
    const gapSize = endKnown - start + 1;
    if (gapSize > 0 && gapSize < PAGE_SIZE) limit = gapSize; // només carrega el necessari
  }
  // Registra fins on arribava el bloc contigu abans de carregar
  let oldContiguousEnd = 0;
  while (wordsByPos[oldContiguousEnd]) oldContiguousEnd++;
  fetch(`${RANKINGS_API}/${selected}?offset=${start}&limit=${limit}`, {
    headers: { ...authHeaders() },
  })
    .then((res) => res.json())
    .then((data) => {
      data.words.forEach((w) => {
        if (!wordsByPos[w.pos]) wordsByPos[w.pos] = w;
      });
      total = data.total;
      renderWordsArea();
      // Actualitza títol si s'ha carregat la posició 0
      if (start === 0 && data.words.some((w) => w.pos === 0)) {
        updateWordsTitle();
      }
      // Després de renderitzar, calculem nou límit contigu i marquem nous ítems
      let newContiguousEnd = 0;
      while (wordsByPos[newContiguousEnd]) newContiguousEnd++;
      if (newContiguousEnd > oldContiguousEnd) {
        setTimeout(() => {
          const wordItems = document.querySelectorAll(".word-item");
          for (let pos = oldContiguousEnd; pos < newContiguousEnd; pos++) {
            wordItems.forEach((el) => {
              if (
                el.firstChild &&
                el.firstChild.textContent &&
                el.firstChild.textContent.startsWith(`${pos}.`)
              ) {
                tempHighlightElement(el);
              }
            });
          }
        }, 0);
      }
    });
  refreshTestOverlayIfVisible();
}

function triggerSearch(term) {
  if (!selected) return;
  const t = term.trim().toLowerCase();
  if (!t) return;
  fetch(`${RANKINGS_API}/${selected}/find?word=${encodeURIComponent(t)}`, {
    headers: { ...authHeaders() },
  })
    .then((r) => r.json())
    .then(async (res) => {
      if (!res.found) {
        alert("No trobada");
        return;
      }
      await ensureVisible(res.pos, { highlight: true, forceScroll: true });
    })
    .catch(() => alert("Error en la cerca"));
}

// --- Afegir paraula nova al rànquing ---
async function promptAddNewWord() {
  if (!selected) return alert("Cal seleccionar un rànquing");
  const raw = prompt(
    "Escriu la paraula (nom o verb en forma canònica, sense flexió).\nAbans d'afegir recorda: només lemes (ex: 'anar', 'casa', no 'anant', 'cases').",
    ""
  );
  if (raw === null) return; // cancel·lat
  const word = (raw || "").trim().toLowerCase();
  if (!word) return;
  // Consulta info de lema
  let lemmaInfo = null;
  try {
    const r = await fetch(
      `${API_BASE}/lemma-info/${encodeURIComponent(word)}`,
      {
        headers: { ...authHeaders() },
      }
    );
    if (r.ok) lemmaInfo = await r.json();
  } catch (_) {}
  let warning = "Segur que vols afegir '" + word + "'?\n";
  if (lemmaInfo) {
    if (!lemmaInfo.is_known) {
      warning +=
        "No s'ha trobat al diccionari; comprova bé que sigui un lema.\n";
    } else if (lemmaInfo.is_inflection) {
      warning += `ATENCIÓ: sembla una flexió del lema '${lemmaInfo.lemma}'.\n`;
    } else if (lemmaInfo.lemma && lemmaInfo.lemma === word) {
      warning += "Detectat com a lema vàlid.\n";
    }
  }
  warning +=
    "Confirma per afegir-la al final (o escriu una posició concreta).\n\nIntrodueix posició numèrica o deixa en blanc per posar-la al final.";
  const posStr = prompt(warning, "");
  if (posStr === null) return; // cancel
  let toPos = null;
  if (posStr.trim()) {
    const n = parseInt(posStr.trim(), 10);
    if (!isNaN(n) && n >= 0) toPos = n;
  }
  try {
    const res = await fetch(`${RANKINGS_API}/${selected}/add-new`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ word, to_pos: toPos }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Error" }));
      alert(err.detail || "Error afegint paraula");
      return;
    }
    const data = await res.json();
    // Recarrega primer bloc i assegura visibilitat de la nova posició
    await reloadInitialBlock();
    await ensureVisible(data.to, {
      highlight: true,
      special: true,
      force: data.to >= PAGE_SIZE,
    });
    alert(
      `Afegida '${data.word}' a posició ${data.to}.` +
        (data.is_inflection
          ? `\nNota: sembla flexió del lema '${data.lemma}'.`
          : data.lemma
          ? "\nConfirmat com a lema."
          : "")
    );
  } catch (e) {
    alert("Error de xarxa");
  }
}
