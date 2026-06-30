(function () {
  "use strict";

  // ── Session management ──────────────────────────────────────────────────
  const SESSION_KEY = "jc_session_id";
  const API = "/api";

  function getSessionId() {
    let sid = localStorage.getItem(SESSION_KEY);
    if (!sid) {
      sid = crypto.randomUUID();
      localStorage.setItem(SESSION_KEY, sid);
    }
    return sid;
  }

  function resetSession() {
    localStorage.removeItem(SESSION_KEY);
    location.reload();
  }

  let sessionId = getSessionId();
  let isAnalyzing = false;
  let isChatting = false;
  let uploadedFile = null;

  // ── Fetch helper ────────────────────────────────────────────────────────
  async function apiFetch(path, options) {
    options = options || {};
    const headers = Object.assign({ "X-Session-ID": sessionId }, options.headers || {});
    return fetch(API + path, Object.assign({}, options, { headers: headers }));
  }

  // ── DOM refs ────────────────────────────────────────────────────────────
  const dropZone = document.getElementById("drop-zone");
  const resumeInput = document.getElementById("resume-input");
  const jdInput = document.getElementById("jd-url-input");
  const analyzeBtn = document.getElementById("analyze-btn");
  const chatInput = document.getElementById("chat-input");
  const sendBtn = document.getElementById("send-btn");

  // ── File upload ─────────────────────────────────────────────────────────
  dropZone.addEventListener("click", function () { resumeInput.click(); });

  dropZone.addEventListener("dragover", function (e) {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });

  dropZone.addEventListener("dragleave", function () {
    dropZone.classList.remove("dragover");
  });

  dropZone.addEventListener("drop", function (e) {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    var file = e.dataTransfer.files[0];
    if (file) handleFileSelect(file);
  });

  resumeInput.addEventListener("change", function () {
    if (resumeInput.files[0]) handleFileSelect(resumeInput.files[0]);
  });

  function handleFileSelect(file) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      showInputError("Please upload a PDF file.");
      return;
    }
    uploadedFile = file;
    document.getElementById("drop-zone-content").style.display = "none";
    document.getElementById("drop-zone-uploaded").style.display = "flex";
    document.getElementById("filename-display").textContent = file.name;
    checkFormReady();
  }

  jdInput.addEventListener("input", checkFormReady);

  function checkFormReady() {
    var ready = uploadedFile && jdInput.value.trim().startsWith("http");
    analyzeBtn.disabled = !ready;
  }

  // ── Analyze ─────────────────────────────────────────────────────────────
  analyzeBtn.addEventListener("click", startAnalysis);

  async function startAnalysis() {
    if (isAnalyzing) return;
    isAnalyzing = true;
    hideInputError();

    document.getElementById("analyze-btn-text").style.display = "none";
    document.getElementById("analyze-spinner").style.display = "inline-block";
    analyzeBtn.disabled = true;

    var fd = new FormData();
    fd.append("resume", uploadedFile);
    fd.append("jd_url", jdInput.value.trim());

    try {
      var res = await apiFetch("/analyze", { method: "POST", body: fd });
      var data = await res.json();

      if (!res.ok) {
        showInputError(data.detail || "Analysis failed. Check your inputs.");
        return;
      }

      document.getElementById("role-badge").textContent =
        (data.jd_title || "Role") + " @ " + (data.jd_company || "Company") +
        (data.resume_pages ? " \u2014 " + data.resume_pages + " page resume" : "");
      document.getElementById("new-session-btn").style.display = "inline-block";

      document.getElementById("chat-section").style.display = "block";
      document.getElementById("chat-section").scrollIntoView({ behavior: "smooth" });

      renderChatHistory(data.chat_history || []);

      if (data.status === "chatting" && data.next_question) {
        addAIBubble(data.next_question);
        enableChatInput();
      } else if (data.status === "done") {
        showResults(data);
      }

    } catch (err) {
      showInputError("Connection error. Is the backend running?");
    } finally {
      isAnalyzing = false;
      document.getElementById("analyze-btn-text").style.display = "inline";
      document.getElementById("analyze-spinner").style.display = "none";
      analyzeBtn.disabled = false;
    }
  }

  // ── Chat ────────────────────────────────────────────────────────────────
  function enableChatInput() {
    isChatting = true;
    chatInput.disabled = false;
    sendBtn.disabled = false;
    chatInput.focus();
  }

  function disableChatInput() {
    chatInput.disabled = true;
    sendBtn.disabled = true;
  }

  sendBtn.addEventListener("click", sendMessage);
  chatInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  async function sendMessage() {
    var msg = chatInput.value.trim();
    if (!msg || !isChatting) return;

    chatInput.value = "";
    addUserBubble(msg);
    disableChatInput();
    showTypingIndicator();

    try {
      var res = await apiFetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg })
      });
      var data = await res.json();
      removeTypingIndicator();

      if (!res.ok) {
        addAIBubble("Sorry, something went wrong. Please try again.");
        enableChatInput();
        return;
      }

      renderChatHistory(data.chat_history || []);

      if (data.status === "chatting" && data.next_question) {
        addAIBubble(data.next_question);
        enableChatInput();
      } else if (data.status === "done") {
        showResults(data);
      }

    } catch (err) {
      removeTypingIndicator();
      addAIBubble("Connection error. Please try again.");
      enableChatInput();
    }
  }

  // ── Chat UI helpers ─────────────────────────────────────────────────────
  function addAIBubble(text) {
    var container = document.getElementById("chat-messages");
    var div = document.createElement("div");
    div.className = "chat-bubble ai";
    div.innerHTML = markdownToHtml(text);
    container.appendChild(div);
    div.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  function addUserBubble(text) {
    var container = document.getElementById("chat-messages");
    var div = document.createElement("div");
    div.className = "chat-bubble user";
    div.textContent = text;
    container.appendChild(div);
    div.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  function renderChatHistory(history) {
    var container = document.getElementById("chat-messages");
    var existingCount = container.querySelectorAll(".chat-bubble").length;
    var newMessages = history.slice(existingCount);
    newMessages.forEach(function (msg) {
      if (msg.role === "assistant") addAIBubble(msg.content);
      else addUserBubble(msg.content);
    });
  }

  function showTypingIndicator() {
    var container = document.getElementById("chat-messages");
    var div = document.createElement("div");
    div.id = "typing-indicator";
    div.className = "typing-indicator";
    div.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
    container.appendChild(div);
    div.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  function removeTypingIndicator() {
    var el = document.getElementById("typing-indicator");
    if (el) el.remove();
  }

  function markdownToHtml(text) {
    if (!text) return "";
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.*?)\*/g, "<em>$1</em>")
      .replace(/\n/g, "<br>");
  }

  // ── Results ─────────────────────────────────────────────────────────────
  function showResults(data) {
    isChatting = false;
    disableChatInput();

    var rec = data.fit_recommendation || "Good Fit";
    var score = data.fit_score || 0;
    var color = score >= 8 ? "#3fb950" : score >= 6 ? "#d29922" : "#f85149";
    var bd = data.fit_breakdown || {};

    var breakdownHtml = Object.keys(bd).map(function (k) {
      return '<span class="score-item">' +
        k.replace(/_/g, " ") + ': <span>' + bd[k] + '/10</span></span>';
    }).join("");

    document.getElementById("score-card").innerHTML =
      '<div class="score-circle"><span class="score-number" style="color:' + color + '">' + score + '</span></div>' +
      '<div><div style="font-size:20px;font-weight:600;color:var(--text-bright)">' + escapeHtml(rec) + '</div>' +
      '<div class="score-breakdown">' + breakdownHtml + '</div></div>';

    document.getElementById("resume-content").textContent = data.resume_output || "";
    document.getElementById("cover-content").textContent = data.cover_letter_output || "";

    document.getElementById("download-resume-btn").onclick = function () { downloadDoc("resume"); };
    document.getElementById("download-cover-btn").onclick = function () { downloadDoc("cover-letter"); };

    document.getElementById("results-section").style.display = "block";
    document.getElementById("results-section").scrollIntoView({ behavior: "smooth" });
  }

  async function downloadDoc(type) {
    try {
      var res = await apiFetch("/export/" + sessionId + "/" + type);
      if (!res.ok) {
        showToast("Download failed. Please try again.");
        return;
      }
      var blob = await res.blob();
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = type + "-" + Date.now() + ".docx";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      showToast("Download failed.");
    }
  }

  // ── Copy buttons ────────────────────────────────────────────────────────
  document.querySelectorAll(".copy-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var targetId = btn.getAttribute("data-target");
      var text = document.getElementById(targetId).textContent;
      navigator.clipboard.writeText(text).then(function () {
        showToast("Copied to clipboard");
      });
    });
  });

  // ── Toast ───────────────────────────────────────────────────────────────
  function showToast(msg) {
    var t = document.createElement("div");
    t.className = "toast";
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 3000);
  }

  // ── Error display ───────────────────────────────────────────────────────
  function showInputError(msg) {
    var el = document.getElementById("input-error");
    el.textContent = msg;
    el.style.display = "block";
  }

  function hideInputError() {
    document.getElementById("input-error").style.display = "none";
  }

  // ── Helpers ─────────────────────────────────────────────────────────────
  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str || "";
    return div.innerHTML;
  }

  // ── New session button ──────────────────────────────────────────────────
  document.getElementById("new-session-btn").addEventListener("click", resetSession);
})();
