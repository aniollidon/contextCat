// Configuració
const PORT = 3000; // Port on corre el backend admin (uvicorn)
// Arrel del servidor (es pot sobreescriure abans de carregar aquest script definint window.CONTEXTCAT_SERVER)
const SERVER = `http://5.250.190.223:${PORT}`;
// Bases d'API
const API_BASE = `${SERVER}/api`;
const RANKINGS_API = `${API_BASE}/rankings`;
const VALIDATIONS_API = `${API_BASE}/validations`;
const FAVORITES_API = `${API_BASE}/favorites`;
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
let validations = {}; // filename -> true
let favorites = {}; // filename -> true
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
    const saved = localStorage.getItem("contextcat-admin-settings");
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
    localStorage.setItem("contextcat-admin-settings", JSON.stringify(settings));
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
          <h2 class="fw-bold mb-2">rebuscada.cat - Gestió </h2>
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
              <h5 class="mb-0">Paraules</h5>
              <span id="autosave-status" class="text-muted small" style="display:none;">Desant…</span>
            </div>
            <div class="input-group input-group-sm mb-2">
              <input id="search-word" type="text" class="form-control" placeholder="Cerca paraula..." />
              <button class="btn btn-outline-secondary" id="search-btn" type="button" title="Cerca">Cerca</button>
              <button class="btn btn-outline-info" id="show-test" type="button" title="Mostra paraules test">Test</button>
            </div>
            <div id="words-area" style="min-height:120px;"></div>
            <div id="test-overlay" style="display:none; max-height:220px; overflow:auto; border:1px solid #ddd; border-radius:6px; padding:6px; background:#fff; margin-top:8px;"></div>
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
  const filterChk = document.getElementById("filter-pending");
  const favoritesChk = document.getElementById("filter-favorites");
  const settingsBtn = document.getElementById("settings-btn");

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
  if (settingsBtn) settingsBtn.onclick = openSettingsModal;
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
    const res = await fetch(`${RANKINGS_API}/${selected}/test-words`, {
      headers: { ...authHeaders() },
    });
    if (!res.ok) throw new Error();
    const data = await res.json();
    if (!testVisible) return; // si s'ha tancat mentre carregava
    const rows = data.words
      .map((w) => {
        if (w.found) {
          return `<div class="test-row"><span style="color:${colorPerPos(
            w.pos
          )}">${w.word}</span> <a href="#" data-pos="${
            w.pos
          }" class="jump" title="Ves a posició">(${w.pos})</a></div>`;
        }
        return `<div class="test-row text-muted"><span>${w.word}</span> <span style="font-size:11px">(no)</span></div>`;
      })
      .join("");
    overlay.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
      <strong class="small">Paraules test (${data.count})</strong>
      <div class="btn-group btn-group-sm" role="group">
        <button class="btn btn-outline-success" id="add-test-inside" title="Afegeix paraules al test">+Add</button>
        <button class="btn btn-outline-secondary" id="toggle-test-select" title="Mode selecció">Sel</button>
        <button class="btn btn-outline-danger" id="delete-selected-test" style="display:none;" title="Elimina seleccionades">Del</button>
        <button class="btn btn-outline-secondary" id="close-test" title="Tanca">✕</button>
      </div>
    </div><div class="test-body" id="test-body" style="font-size:13px;display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:4px;">${rows}</div>`;
    const closeBtn = document.getElementById("close-test");
    if (closeBtn) closeBtn.onclick = () => hideTestOverlay();
    initTestWordSelection();
    const addInside = document.getElementById("add-test-inside");
    if (addInside) addInside.onclick = addTestWordsPrompt;
    overlay.querySelectorAll("a.jump").forEach((a) => {
      a.addEventListener("click", async (e) => {
        e.preventDefault();
        const p = parseInt(a.getAttribute("data-pos"), 10);
        await ensureVisible(p, {
          highlight: true,
          special: true,
          force: p >= PAGE_SIZE,
          forceScroll: true, // Sempre fa scroll quan es va des de test
        });
      });
    });
  } catch (e) {
    overlay.innerHTML =
      '<div class="text-danger small">Error carregant test</div>';
  }
}

function refreshTestOverlayIfVisible() {
  if (testVisible) loadTestOverlayData();
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
  // Carrega llistat, validacions i preferits en paral·lel
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
  ]).then(([flist, vals, favs]) => {
    files = flist;
    validations = vals || {};
    favorites = favs || {};
    renderFileList();
  });
}

function renderFileList() {
  const ul = document.getElementById("file-list");
  ul.innerHTML = "";
  files.forEach((f) => {
    const isValidated = !!validations[f];
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
    const checked = !!validations[f];
    span.innerHTML = `
      <input type="checkbox" class="form-check-input me-2 validate-chk" id="${chkId}" ${
      checked ? "checked" : ""
    } title="Marca com a fet" />
      <button class="star-btn ${
        isFavorite ? "favorite" : ""
      }" id="${starId}" title="Marca com a preferit" type="button">
        <i class="bi ${isFavorite ? "bi-star-fill" : "bi-star"}"></i>
      </button>
      <label for="${chkId}" class="form-check-label" style="cursor:pointer;">${f}</label>
    `;
    li.appendChild(span);
    li.onclick = () => loadFile(f);
    // Checkbox toggle (aturar propagació per no carregar el fitxer automàticament)
    const chk = span.querySelector("input");
    if (checked) chk.classList.add("validated-yes");
    chk.addEventListener("click", (e) => {
      e.stopPropagation();
      const newVal = e.target.checked;
      fetch(`${VALIDATIONS_API}/${f}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ validated: newVal }),
      })
        .then((r) => {
          if (!r.ok) throw new Error();
          if (newVal) {
            validations[f] = true;
            chk.classList.add("validated-yes");
          } else {
            delete validations[f];
            chk.classList.remove("validated-yes");
          }
          if (showOnlyPending && newVal) renderFileList();
        })
        .catch(() => {
          e.target.checked = !newVal; // revert
          alert("Error desant validació");
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

function loadFile(filename) {
  selected = filename;
  wordsByPos = {};
  dirty = false;
  loading = true;
  lastMoveInfo = null;
  renderFileList();
  renderWordsArea();
  fetch(`${RANKINGS_API}/${filename}?offset=0&limit=${PAGE_SIZE}`, {
    headers: { ...authHeaders() },
  })
    .then((res) => res.json())
    .then((data) => {
      data.words.forEach((w) => (wordsByPos[w.pos] = w));
      total = data.total;
      loading = false;
      renderWordsArea();
      refreshTestOverlayIfVisible();
    });
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
      menuBtn.innerHTML = '<i class="bi bi-three-dots-vertical"></i>';
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
  if (dragIdx === null || dragIdx === 0 || pos === 0 || dragIdx === pos) return;
  document
    .querySelectorAll(".word-item.drag-over")
    .forEach((el) => el.classList.remove("drag-over"));
  item.classList.add("drag-over");
}
function onDrop(e, pos, item) {
  e.preventDefault();
  if (dragIdx === null || dragIdx === 0 || pos === 0 || dragIdx === pos) return;
  // Construïm bloc contigu inicial
  let contiguousEnd = 0;
  while (wordsByPos[contiguousEnd]) contiguousEnd++;
  const arr = [];
  for (let i = 0; i < contiguousEnd; i++) arr.push(wordsByPos[i]);
  const fromIndex = dragIdx;
  const toIndex = pos;
  const [moved] = arr.splice(fromIndex, 1);
  arr.splice(toIndex, 0, moved);
  for (let i = 0; i < arr.length; i++)
    wordsByPos[i] = { word: arr[i].word, pos: i };
  dirty = true;
  dragIdx = null;
  renderWordsArea();
  setTimeout(() => {
    const wordItems = document.querySelectorAll(".word-item");
    if (wordItems[toIndex]) tempHighlightElement(wordItems[toIndex]);
  }, 0);
  scheduleAutoSave();
  refreshTestOverlayIfVisible();
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
  let html = `
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
  // Esborra bloc inicial anterior
  let i = 0;
  while (wordsByPos[i]) {
    delete wordsByPos[i];
    i++;
  }
  data.words.forEach((w) => (wordsByPos[w.pos] = w));
  total = data.total;
  renderWordsArea();
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
  if (!selected) return;
  // Bloc contigu inicial
  let contiguousEnd = 0;
  while (wordsByPos[contiguousEnd]) contiguousEnd++;
  const ranking = {};
  for (let i = 0; i < contiguousEnd; i++) ranking[wordsByPos[i].word] = i;
  const status = document.getElementById("autosave-status");
  if (status) {
    status.style.display = "inline";
    status.textContent = "Desant…";
  }
  fetch(`${RANKINGS_API}/${selected}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ fragment: ranking, offset: 0 }),
  })
    .then(() => {
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
      await ensureVisible(res.pos, { highlight: true });
    })
    .catch(() => alert("Error en la cerca"));
}
