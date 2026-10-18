(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  function stored(key) {
    try { return localStorage.getItem(key) || ""; } catch (e) { return ""; }
  }
  function keep(key, value) {
    try { localStorage.setItem(key, value); } catch (e) {}
  }

  // text always goes in with textContent, never innerHTML, so nothing typed or written by the model can run as code
  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  let api = "";
  let token = stored("token");
  let me = "";
  let ready = false;
  let timer = null;
  let statustimer = null;
  const blobs = new Map();

  // ---------- which server to talk to ----------

    function pickserver() {
    // the python server serves this page, so the api is always the same site
    api = "";
    $("server").textContent = "";
  }

  async function call(path, opts) {
    opts = opts || {};
    const headers = Object.assign({ "ngrok-skip-browser-warning": "1" }, opts.headers || {});
    if (token) headers["Authorization"] = "Bearer " + token;
    if (typeof opts.body === "string") headers["Content-Type"] = "application/json";
    let res;
    try {
      res = await fetch(api + path, Object.assign({}, opts, { headers: headers }));
    } catch (e) {
      const err = new Error("cannot reach the server");
      err.status = 0;
      throw err;
    }
    if (res.status === 401 && token && path !== "/api/login") {
      leave();
      const err = new Error("please log in again");
      err.status = 401;
      throw err;
    }
    if (!res.ok) {
      let text = "something went wrong";
      try {
        const j = await res.json();
        text = typeof j.detail === "string" ? j.detail : "please check what you typed";
      } catch (e) {}
      const err = new Error(text);
      err.status = res.status;
      throw err;
    }
    return res;
  }

  async function json(path, opts) {
    const res = await call(path, opts);
    try { return await res.json(); } catch (e) { throw new Error("cannot reach the server"); }
  }

  async function bloburl(path) {
    if (blobs.has(path)) return blobs.get(path);
    const res = await call(path);
    const url = URL.createObjectURL(await res.blob());
    blobs.set(path, url);
    return url;
  }

  function loadimg(img, path) {
    bloburl(path)
      .then((url) => { img.src = url; img.classList.remove("shimmer"); })
      .catch(() => { img.classList.remove("shimmer"); img.alt = "the picture could not load"; });
  }

  function msg(id, text, good) {
    const node = $(id);
    node.textContent = text;
    node.classList.toggle("ok", !!good);
  }

  // ---------- views ----------

  const views = ["auth", "studio", "library", "detail"];

  function go(name) {
    views.forEach((v) => { $(v).hidden = v !== name; });
    document.querySelectorAll("nav button").forEach((b) => {
      b.classList.toggle("on", b.dataset.view === (name === "detail" ? "library" : name));
    });
    window.scrollTo(0, 0);
    if (name === "library") loadlibrary();
  }

  function enter(name) {
    me = name;
    $("username").textContent = name;
    $("who").hidden = false;
    $("nav").hidden = false;
    go("studio");
    const old = stored("job");
    if (old) watch(old);
  }

  function leave() {
    token = "";
    me = "";
    keep("token", "");
    keep("job", "");
    clearTimeout(timer);
    $("who").hidden = true;
    $("nav").hidden = true;
    blobs.forEach((url) => URL.revokeObjectURL(url));
    blobs.clear();
    showtab("login");
    go("auth");
  }

  // ---------- server status ----------

  function banner(text, bad) {
    const b = $("banner");
    b.hidden = !text;
    b.textContent = text || "";
    b.classList.toggle("bad", !!bad);
  }

  async function checkstatus() {
    clearTimeout(statustimer);
    try {
      const s = await json("/api/status");
      if (s.error) {
        banner(s.error, true);
        ready = false;
      } else if (!s.ready) {
        banner("the server is getting ready (" + s.note + "). generating will work in a few minutes.");
        ready = false;
        statustimer = setTimeout(checkstatus, 5000);
      } else {
        banner("");
        ready = true;
      }
    } catch (e) {
      ready = false;
      banner("cannot reach the server. check that the kaggle session is still running and open the link from the server cell again.", true);
      statustimer = setTimeout(checkstatus, 8000);
    }
    $("makebtn").disabled = !ready || !!$("progress").offsetParent;
  }

  // ---------- log in and sign up ----------

  function showtab(which) {
    $("loginform").hidden = which !== "login";
    $("signupform").hidden = which !== "signup";
    $("tablogin").classList.toggle("on", which === "login");
    $("tabsignup").classList.toggle("on", which === "signup");
    msg("authmsg", "");
  }

  async function dologin(name, pass) {
    const r = await json("/api/login", { method: "POST", body: JSON.stringify({ name: name, password: pass }) });
    token = r.token;
    keep("token", token);
    enter(r.name);
  }

  async function onlogin(e) {
    e.preventDefault();
    msg("authmsg", "");
    try {
      await dologin($("lname").value, $("lpass").value);
      $("lpass").value = "";
    } catch (err) {
      msg("authmsg", err.message);
    }
  }

  async function onsignup(e) {
    e.preventDefault();
    msg("authmsg", "");
    if ($("spass").value !== $("spass2").value) {
      msg("authmsg", "the two passwords are not the same");
      return;
    }
    try {
      await json("/api/signup", {
        method: "POST",
        body: JSON.stringify({ name: $("sname").value, email: $("semail").value, password: $("spass").value }),
      });
      await dologin($("sname").value, $("spass").value);
      $("spass").value = "";
      $("spass2").value = "";
    } catch (err) {
      msg("authmsg", err.message);
    }
  }

  async function onlogout() {
    try { await call("/api/logout", { method: "POST" }); } catch (e) {}
    leave();
  }

  // ---------- making a storyboard ----------

  function chosen(name) {
    const picked = document.querySelector('input[name="' + name + '"]:checked');
    return picked ? picked.value : "";
  }

  function buildoptions(opts) {
    const styles = $("styles");
    styles.replaceChildren();
    opts.styles.forEach((name, i) => {
      const label = el("label", "chip");
      label.style.margin = "0";
      const input = el("input");
      input.type = "radio";
      input.name = "style";
      input.value = name;
      input.checked = i === 0;
      label.append(input, el("span", "", name));
      styles.append(label);
    });
    const levels = $("levels");
    levels.replaceChildren();
    opts.levels.forEach((name, i) => {
      const label = el("label", "seg");
      label.style.margin = "0";
      const input = el("input");
      input.type = "radio";
      input.name = "level";
      input.value = name;
      input.checked = i === 0;
      label.append(input, el("span", "", name));
      levels.append(label);
    });
    $("scenes").min = opts.mincount;
    $("scenes").max = opts.maxcount;
  }

  async function generate(e) {
    e.preventDefault();
    msg("genmsg", "");
    const body = {
      idea: $("idea").value.trim(),
      count: Number($("scenes").value),
      style: chosen("style"),
      level: chosen("level"),
      seed: Number($("seed").value) || 0,
    };
    if (body.idea.length < 3) {
      msg("genmsg", "please write your idea first");
      return;
    }
    $("makebtn").disabled = true;
    try {
      const r = await json("/api/generate", { method: "POST", body: JSON.stringify(body) });
      keep("job", r.id);
      watch(r.id);
    } catch (err) {
      msg("genmsg", err.message);
      $("makebtn").disabled = !ready;
    }
  }

  function watch(id) {
    $("empty").hidden = true;
    $("board").hidden = true;
    $("progress").hidden = false;
    $("makebtn").disabled = true;
    $("stepnow").textContent = "waiting";
    $("ahead").textContent = "";
    clearTimeout(timer);
    let misses = 0;
    const tick = async () => {
      if (!me) return;
      try {
        const j = await json("/api/jobs/" + id);
        misses = 0;
        $("stepnow").textContent = j.step || "waiting";
        $("ahead").textContent = j.status === "queued" && j.ahead > 0 ? j.ahead + " storyboard(s) before yours" : "";
        if (j.status === "done") { await finish(j.boardid); return; }
        if (j.status === "failed") { fail(j.error); return; }
      } catch (err) {
        if (err.status === 404) { fail("the server was restarted, please try again"); return; }
        if (err.status === 401) return;
        misses += 1;
        if (misses > 15) { fail("lost the connection to the server"); return; }
      }
      timer = setTimeout(tick, 2000);
    };
    tick();
  }

  async function finish(boardid) {
    keep("job", "");
    try {
      const b = await json("/api/boards/" + boardid);
      $("progress").hidden = true;
      $("board").hidden = false;
      render($("board"), b, false);
    } catch (err) {
      fail(err.message);
    }
    $("makebtn").disabled = !ready;
  }

  function fail(text) {
    keep("job", "");
    $("progress").hidden = true;
    $("empty").hidden = false;
    msg("genmsg", text);
    $("makebtn").disabled = !ready;
  }

  // ---------- showing a storyboard ----------

  function render(box, b, saved) {
    box.replaceChildren();

    const top = el("div", "boardtop");
    const titles = el("div");
    titles.append(el("h2", "", b.idea));
    const tags = el("div", "tags");
    tags.append(el("span", "tag", b.style), el("span", "tag", b.level + " words"));
    titles.append(tags);

    const actions = el("div", "actions");
    const zip = el("button", "btn small", "download zip");
    zip.type = "button";
    zip.addEventListener("click", () => download(b.id).catch((err) => alert(err.message)));
    const print = el("button", "btn small", "print");
    print.type = "button";
    print.addEventListener("click", () => window.print());
    actions.append(zip, print);
    if (saved) {
      const del = el("button", "btn small danger", "delete");
      del.type = "button";
      del.addEventListener("click", () => remove(b.id));
      actions.append(del);
    }
    top.append(titles, actions);

    const story = el("div", "card storycard");
    story.append(el("h3", "", "the story"), el("p", "readable", b.story));
    story.append(el("p", "muted small", "main character: " + b.character));

    const scenes = el("div", "scenes");
    b.scenes.forEach((s, i) => {
      const fig = el("figure", "scene");
      const img = el("img", "shimmer");
      img.alt = "scene " + (i + 1) + ": " + s.text;
      loadimg(img, "/api/boards/" + b.id + "/image/" + (i + 1));
      const cap = el("figcaption");
      cap.append(el("b", "", "scene " + (i + 1)), el("p", "readable", s.text));
      fig.append(img, cap);
      scenes.append(fig);
    });

    box.append(top, story, scenes);
  }

  async function download(id) {
    const res = await call("/api/boards/" + id + "/zip");
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "storyboard" + id + ".zip";
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 3000);
  }

  // ---------- saved storyboards ----------

  async function loadlibrary() {
    const grid = $("grid");
    try {
      const list = await json("/api/boards");
      grid.replaceChildren();
      $("libempty").hidden = list.length > 0;
      list.forEach((b) => {
        const tile = el("button", "card tile");
        tile.type = "button";
        const img = el("img", "shimmer");
        img.alt = "";
        loadimg(img, "/api/boards/" + b.id + "/cover");
        const when = new Date(b.created * 1000).toLocaleDateString();
        tile.append(img, el("strong", "", b.idea), el("span", "muted small", when + " · " + b.count + " scenes · " + b.style));
        tile.addEventListener("click", () => opendetail(b.id));
        grid.append(tile);
      });
    } catch (err) {
      $("libempty").hidden = false;
      $("libempty").textContent = err.message;
    }
  }

  async function opendetail(id) {
    try {
      const b = await json("/api/boards/" + id);
      render($("detailboard"), b, true);
      go("detail");
    } catch (err) {
      alert(err.message);
    }
  }

  async function remove(id) {
    if (!confirm("delete this storyboard? this cannot be undone.")) return;
    try {
      await call("/api/boards/" + id, { method: "DELETE" });
      go("library");
    } catch (err) {
      alert(err.message);
    }
  }

  // ---------- start ----------

  function applyeasy() {
    const on = $("easy").checked;
    document.body.classList.toggle("easy", on);
    keep("easy", on ? "1" : "0");
  }

  function wire() {
    $("tablogin").addEventListener("click", () => showtab("login"));
    $("tabsignup").addEventListener("click", () => showtab("signup"));
    $("loginform").addEventListener("submit", onlogin);
    $("signupform").addEventListener("submit", onsignup);
    $("logout").addEventListener("click", onlogout);
    $("makeform").addEventListener("submit", generate);
    $("back").addEventListener("click", () => go("library"));
    document.querySelectorAll("nav button").forEach((b) => b.addEventListener("click", () => go(b.dataset.view)));
    $("idea").addEventListener("input", () => { $("ideacount").textContent = $("idea").value.length; });
    $("scenes").addEventListener("input", () => { $("scenesout").textContent = $("scenes").value; });
    $("easy").checked = stored("easy") !== "0";
    $("easy").addEventListener("change", applyeasy);
    applyeasy();
  }

  async function start() {
    try {
      buildoptions(await json("/api/options"));
    } catch (e) {
      banner("cannot reach the server. check that the kaggle session is still running and open the link from the server cell again.", true);
      go("auth");
      setTimeout(start, 8000);
      return;
    }

    if (token) {
      try {
        const r = await json("/api/me");
        enter(r.name);
      } catch (e) {
        leave();
      }
    } else {
      go("auth");
    }
    checkstatus();
  }

  pickserver();
  wire();
  start();
})();
