const $ = id => document.getElementById(id);

const worker = new Worker("worker.js");
const waiting = new Map();

let requestId = 0;
let ready = false;
let busy = false;
let state = null;
let paused = false;
let pausedAt = 0;

let timerKey = "";
let due = 0;
let selected = new Set();

function cardKey(card) {
  return card.join(",");
}

function selectedCards() {
  return [...selected].map(key => key.split(",").map(Number));
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function rpc(request) {
  return new Promise((resolve, reject) => {
    const id = ++requestId;
    waiting.set(id, {resolve, reject});
    worker.postMessage({id, request});
  });
}

worker.onmessage = event => {
  const message = event.data;

  if (message.type === "ready") {
    ready = true;
    $("loading").textContent = "Đã sẵn sàng. Chọn trò và bấm Bắt đầu.";
    $("start").disabled = false;
    return;
  }

  if (message.type === "fatal") {
    $("error").textContent = message.error;
    $("loading").textContent = "Không khởi động được Python.";
    return;
  }

  const pending = waiting.get(message.id);
  if (!pending) return;

  waiting.delete(message.id);

  if (message.ok) pending.resolve(message.result);
  else pending.reject(new Error(message.error));
};

worker.onerror = event => {
  $("error").textContent = event.message || "Worker gặp lỗi.";
  $("loading").textContent = "Worker đã dừng.";

  for (const pending of waiting.values()) {
    pending.reject(new Error("Worker đã dừng."));
  }

  waiting.clear();
};

function scheduleState() {
  if (!state) return;

  const key = state.key + ":" + state.mode;

  if (timerKey === key) return;
  timerKey = key;

  let delay = 0;

  if (state.mode === "reaction") delay = 4000;
  if (state.mode === "bot") delay = Number($("speed").value);
  if (state.mode === "next") delay = 500;

  due = performance.now() + delay;

  // Mốc pause mới nếu trạng thái thay đổi trong lúc đang dừng.
  if (paused) pausedAt = performance.now();
}

async function command(request) {
  if (!ready || busy) return;

  busy = true;
  $("error").textContent = "";
  updateControls();

  try {
    const result = await rpc(request);

    state = result.state;

    if (request.op === "new") {
      selected.clear();
      timerKey = "";
      paused = false;
      $("analysis").textContent = "Bấm Phân tích AI để xem gợi ý.";
    }

    if (["action", "bot", "next"].includes(request.op)) {
      selected.clear();
    }

    if (result.text !== null) {
      $("analysis").textContent = result.text;
    }

    if (result.cards !== null) {
      selected = new Set(result.cards.map(cardKey));
    }

    scheduleState();
    render();

  } catch (error) {
    $("error").textContent = String(error.message || error);

    // Lệnh người chơi không hợp lệ không dừng đồng hồ rình.
    // Lỗi bot/chuyển ván thì dừng tự động để tránh lặp lỗi.
    if (["bot", "next"].includes(request.op) && !paused) {
      setPause(true);
    }

  } finally {
    busy = false;
    updateControls();
  }
}

function setPause(value) {
  if (!state || value === paused) return;

  const now = performance.now();

  if (value) {
    pausedAt = now;
  } else {
    due += now - pausedAt;
  }

  paused = value;
  updateControls();
}

function makeCard(card, selectable = false, compact = false) {
  const node = element("button", "card");

  if (card === null) {
    node.classList.add("back");
    node.textContent = "♠";
    node.disabled = true;
    node.setAttribute("aria-label", "Bài úp");
    return node;
  }

  const [rank, suit] = card;
  const ranks = {11: "J", 12: "Q", 13: "K", 14: "A"};
  const suits = ["♠", "♣", "♦", "♥"];

  node.textContent = `${ranks[rank] || rank}${suits[suit]}`;

  if (suit >= 2) node.classList.add("red");

  const key = cardKey(card);

  if (!compact && selected.has(key)) {
    node.classList.add("selected");
  }

  node.disabled = !selectable;
  node.dataset.playable = selectable ? "1" : "0";

  node.onclick = () => {
    if (paused || busy || !selectable) return;

    if (state.kind === "Tá lả") {
      if (selected.has(key)) selected.clear();
      else selected = new Set([key]);
    } else {
      if (selected.has(key)) selected.delete(key);
      else selected.add(key);
    }

    render();
  };

  return node;
}

function cardRow(cards, playable = [], compact = false) {
  const row = element("div", "cards");
  const allowed = new Set(playable.map(cardKey));

  // Bài úp chỉ cần vài lưng bài; số lá ghi trong thông tin ghế.
  const visibleCards = (
    compact && cards.length > 3 && cards.every(card => card === null)
  ) ? cards.slice(0, 3) : cards;

  for (const card of visibleCards) {
    row.appendChild(makeCard(
      card,
      card !== null && allowed.has(cardKey(card)),
      compact
    ));
  }

  return row;
}

function playerPanel(player) {
  const human = player.pid === 0;
  const panel = element(
    "section",
    "player" + (player.active ? " active" : "")
  );

  panel.appendChild(element(
    "h3",
    "",
    (player.active ? "▶ " : "") + player.name
  ));

  panel.appendChild(element("div", "detail", player.detail));

  if (player.cards.length) {
    panel.appendChild(cardRow(
      player.cards,
      human ? player.playable : [],
      !human
    ));
  }

  if (player.melds.length) {
    panel.appendChild(element("div", "detail", "PHỎM"));

    for (const group of player.melds) {
      const meld = cardRow(group, [], !human);
      meld.classList.add("meld");
      panel.appendChild(meld);
    }
  }

  return panel;
}

function render() {
  if (!state) return;

  $("session").textContent = `${state.kind} • ${state.label}`;
  $("status").textContent = state.status;
  $("summary").textContent = state.summary;

  $("opponents").replaceChildren();
  $("human").replaceChildren();

  for (const player of state.players) {
    const target = player.pid === 0 ? $("human") : $("opponents");
    target.appendChild(playerPanel(player));
  }

  $("centerCards").replaceChildren();

  for (const card of state.center) {
    $("centerCards").appendChild(makeCard(card));
  }

  $("bcBoard").replaceChildren();

  if (state.bc) {
    const bc = state.bc;

    $("centerCards").textContent = (
      bc.dice.length ? "🎲 " + bc.dice.join(" • ") : "XÚC XẮC CHƯA LẮC"
    );

    bc.faces.forEach((name, index) => {
      const button = element(
        "button",
        "face" + (bc.selected === index ? " chosen" : ""),
        `${name.toUpperCase()}\nBạn cược: ${bc.wagers[index].toLocaleString()}`
      );

      button.dataset.action = "1";
      button.onclick = () => humanAction(`face:${index}`);
      $("bcBoard").appendChild(button);
    });

    if (state.mode === "human") {
      $("summary").textContent += (
        `\nChưa phân bổ: ${bc.available.toLocaleString()} xu`
      );
    }
  }

  $("actions").replaceChildren();

  for (const [label, action] of state.options) {
    const button = element("button", "", label);
    button.dataset.action = "1";
    button.onclick = () => humanAction(action);
    $("actions").appendChild(button);
  }

  if (state.kind === "Bầu cua" && state.mode === "human") {
    const custom = element("button", "", "Nhập xu…");
    custom.dataset.action = "1";

    custom.onclick = () => {
      if (paused || busy) return;

      const value = window.prompt(
        `Nhập số xu, tối đa ${state.bc.available}:`
      );

      if (value === null) return;

      const amount = Number(value);

      if (!Number.isSafeInteger(amount) || amount <= 0) {
        $("error").textContent = "Cần nhập số nguyên dương.";
        return;
      }

      humanAction(`add:${amount}`);
    };

    $("actions").appendChild(custom);
  }

  const logs = $("logs");
  const text = state.logs.join("\n");

  if (logs.textContent !== text) {
    logs.textContent = text;
    logs.scrollTop = logs.scrollHeight;
  }

  updateControls();
}

function updateControls() {
  const running = Boolean(state);
  const humanTurn = (
    running && ["human", "reaction"].includes(state.mode)
  );

  $("start").disabled = !ready || busy;
  $("pause").disabled = !running || state.complete;
  $("pause").textContent = paused ? "Tiếp tục" : "Tạm dừng";

  $("hint").disabled = !running || busy;
  $("report").disabled = !running || busy;
  $("clear").disabled = !running || busy || paused;

  $("next").disabled = (
    !running || busy || paused || !state.done || state.complete
  );

  for (const button of document.querySelectorAll("[data-action]")) {
    button.disabled = !humanTurn || paused || busy;
  }

  for (const button of document.querySelectorAll('[data-playable="1"]')) {
    button.disabled = paused || busy;
  }

  $("loading").textContent = busy
    ? "Đang xử lý…"
    : ready
      ? "Python đã sẵn sàng • Tính toán trên thiết bị của bạn"
      : "Đang tải Python cho trình duyệt…";
}

function humanAction(action) {
  if (!state || paused || busy) return;

  command({
    op: "action",
    action,
    selected: selectedCards()
  });
}

function settingsChanged() {
  const flexible = (
    $("mode").value === "quick"
    && ["Poker", "Ba cào", "Bầu cua"].includes($("kind").value)
  );

  $("seats").disabled = !flexible;

  if (!flexible) $("seats").value = "4";
}

$("kind").onchange = settingsChanged;
$("mode").onchange = settingsChanged;

$("start").onclick = () => {
  if (busy) return;

  if (state && !window.confirm("Bỏ phiên hiện tại và bắt đầu lại?")) {
    return;
  }

  command({
    op: "new",
    kind: $("kind").value,
    tournament: $("mode").value === "tournament",
    seats: Number($("seats").value)
  });
};

$("pause").onclick = () => setPause(!paused);
$("hint").onclick = () => command({op: "hint"});
$("report").onclick = () => command({op: "report"});
$("next").onclick = () => command({op: "next"});

$("clear").onclick = () => {
  selected.clear();
  render();
};

document.addEventListener("visibilitychange", () => {
  if (document.hidden && state && !state.complete) {
    setPause(true);
  }
});

setInterval(() => {
  if (!state) return;

  if (paused) {
    $("countdown").textContent = "TẠM DỪNG";
    return;
  }

  if (state.mode === "reaction") {
    const seconds = Math.max(0, (due - performance.now()) / 1000);
    $("countdown").textContent = `CƠ HỘI RÌNH: ${seconds.toFixed(1)} giây`;
  } else {
    $("countdown").textContent = "";
  }

  if (busy || performance.now() < due) return;

  if (state.mode === "bot") {
    command({op: "bot"});
  } else if (state.mode === "next") {
    command({op: "next"});
  } else if (state.mode === "reaction") {
    humanAction("skip_cut");
  }
}, 100);

settingsChanged();
