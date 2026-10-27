'use strict';
/* global Hls, I18N, UI_LANGS, detectUiLang */
// Co-Watch client. The server owns playback state; this page only sends requests
// (play/pause/seek/buffering) and keeps its own <video> aligned with the broadcast state.
// Film time = video.currentTime + media.streamStart. Subtitles are drawn locally.
(() => {
  const $ = (sel) => document.querySelector(sel);
  const el = {
    video: $('#video'), stage: $('#stage'), subPrimary: $('#subPrimary'), subSecondary: $('#subSecondary'),
    empty: $('#empty'), centerMsg: $('#centerMsg'), controls: $('#controls'), seekBar: $('#seekBar'),
    produced: $('#produced'), playBtn: $('#playBtn'), backBtn: $('#backBtn'), fwdBtn: $('#fwdBtn'),
    timeLabel: $('#timeLabel'), muteBtn: $('#muteBtn'), volume: $('#volume'), fsBtn: $('#fsBtn'),
    filmTitle: $('#filmTitle'), members: $('#members'), conn: $('#conn'), uiLang: $('#uiLang'),
    magnetForm: $('#magnetForm'), magnetInput: $('#magnetInput'), fileList: $('#fileList'),
    pathForm: $('#pathForm'), pathInput: $('#pathInput'), hostHint: $('#hostHint'),
    mediaInfo: $('#mediaInfo'), torrentInfo: $('#torrentInfo'), closeMedia: $('#closeMedia'),
    primarySel: $('#primarySel'), secondarySel: $('#secondarySel'), offsetOut: $('#offsetOut'),
    sizeRange: $('#sizeRange'), bottomRange: $('#bottomRange'), searchForm: $('#searchForm'),
    searchLangs: $('#searchLangs'), osOff: $('#osOff'), uploadForm: $('#uploadForm'), subFile: $('#subFile'),
    subLang: $('#subLang'), trackList: $('#trackList'), joinOverlay: $('#joinOverlay'), joinForm: $('#joinForm'),
    nameInput: $('#nameInput'), joinLang: $('#joinLang'), toasts: $('#toasts'),
    drawCanvas: $('#drawCanvas'), cursors: $('#cursors'), toolbar: $('#toolbar'), penBtn: $('#penBtn'),
    colorBtn: $('#colorBtn'), palette: $('#palette'), clearBtn: $('#clearBtn'), sfxBtn: $('#sfxBtn'),
  };
  const video = el.video;

  // ---------------------------------------------------------------- preferences
  const PREFS_KEY = 'cowatch.prefs.v1';
  const DEFAULT_PREFS = {
    name: '', uiLang: detectUiLang(), primaryLang: '', secondaryLang: '', offsetMs: 0,
    fontSize: 100, bottom: 8, searchLangs: '', volume: 1, muted: false, color: '', sfx: true,
  };
  const prefs = (() => {
    try { return { ...DEFAULT_PREFS, ...JSON.parse(localStorage.getItem(PREFS_KEY) || '{}') }; } catch { return { ...DEFAULT_PREFS }; }
  })();
  const savePrefs = () => { try { localStorage.setItem(PREFS_KEY, JSON.stringify(prefs)); } catch { /* private mode */ } };

  // ---------------------------------------------------------------- i18n
  function t (key, params = {}) {
    const dict = I18N[prefs.uiLang] || I18N.en;
    const text = dict[key] ?? I18N.en[key] ?? key;
    return text.replace(/\{(\w+)\}/g, (_, k) => (params[k] ?? ''));
  }
  function applyI18n () {
    document.documentElement.lang = prefs.uiLang;
    document.querySelectorAll('[data-i18n]').forEach((n) => { n.textContent = t(n.dataset.i18n); });
    document.querySelectorAll('[data-i18n-placeholder]').forEach((n) => { n.placeholder = t(n.dataset.i18nPlaceholder); });
    document.querySelectorAll('[data-i18n-title]').forEach((n) => { n.title = t(n.dataset.i18nTitle); });
    renderAll();
  }
  function langName (code) {
    try {
      return new Intl.DisplayNames([prefs.uiLang], { type: 'language' }).of(code) || code;
    } catch { return code; }
  }

  // ---------------------------------------------------------------- state
  const S = {
    ws: null, connected: false, clientId: null,
    clock: { offset: 0, samples: [] },
    room: { playing: false, position: 0, updatedAt: 0, rate: 1, loading: false, waiting: [], seq: 0 },
    media: null, progress: null, members: [], tracks: [], cues: new Map(), osEnabled: false, opening: false,
    joined: false, hls: null, streamId: null, primary: '', secondary: '',
    bufferingSent: false, waitTimer: null, dragging: false, isHost: false, autoplayBlocked: false,
    torrent: null, downloadThrottled: false,
    palette: ['#ff6b6b', '#4dabf7', '#51cf66', '#fcc419', '#cc5de8', '#ff922b', '#22b8cf', '#f06595'],
    penMode: false,
  };

  // ---------------------------------------------------------------- helpers
  const fmtTime = (sec) => {
    if (!Number.isFinite(sec) || sec < 0) sec = 0;
    const s = Math.floor(sec % 60); const m = Math.floor(sec / 60) % 60; const h = Math.floor(sec / 3600);
    return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
  };
  const fmtBytes = (n) => {
    if (!n) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
  };
  function toast (text, level = 'info', ms = 4500) {
    const node = document.createElement('div');
    node.className = `toast ${level}`;
    node.textContent = text;
    el.toasts.appendChild(node);
    setTimeout(() => node.remove(), level === 'error' ? ms * 2 : ms);
  }
  function errorText (err) {
    const raw = String(err && err.message ? err.message : err);
    const code = raw.split(':')[0].trim();
    const key = `err_${code}`;
    if ((I18N[prefs.uiLang] || {})[key] || I18N.en[key]) return t(key);
    return t('err_generic', { detail: raw });
  }
  async function api (path, opts = {}) {
    const init = { credentials: 'same-origin', ...opts };
    if (opts.json !== undefined) {
      init.method = init.method || 'POST';
      init.headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
      init.body = JSON.stringify(opts.json);
      delete init.json;
    }
    const res = await fetch(path, init);
    let data = null;
    try { data = await res.json(); } catch { /* empty body */ }
    if (!res.ok) {
      const detail = data && data.detail !== undefined ? data.detail : res.statusText;
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }
    return data;
  }

  // ---------------------------------------------------------------- clock & room time
  const serverNow = () => performance.now() + S.clock.offset;
  function onPong (msg) {
    const now = performance.now();
    const rtt = now - msg.t0;
    if (!(rtt >= 0 && rtt < 10000)) return;
    S.clock.samples.push({ rtt, offset: msg.ts - (msg.t0 + rtt / 2) });
    if (S.clock.samples.length > 12) S.clock.samples.shift();
    const best = S.clock.samples.reduce((a, b) => (b.rtt < a.rtt ? b : a));
    S.clock.offset = best.offset;
  }
  const roomRunning = () => S.room.playing && !S.room.loading && !(S.room.waiting && S.room.waiting.length);
  function expectedPosition () {
    const r = S.room;
    if (!roomRunning()) return r.position;
    const pos = r.position + ((serverNow() - r.updatedAt) / 1000) * (r.rate || 1);
    return S.media && S.media.duration ? Math.min(pos, S.media.duration) : pos;
  }
  const filmTime = () => (S.media ? video.currentTime + S.media.streamStart : 0);

  // ---------------------------------------------------------------- websocket
  let pingTimer = null;
  function startPings () {
    clearInterval(pingTimer);
    let count = 0;
    const ping = () => {
      send({ type: 'ping', t0: performance.now() });
      count += 1;
      if (count === 6) { clearInterval(pingTimer); pingTimer = setInterval(ping, 10000); }
    };
    ping();
    pingTimer = setInterval(ping, 500);
  }
  function send (msg) {
    if (S.ws && S.ws.readyState === WebSocket.OPEN) S.ws.send(JSON.stringify(msg));
  }
  function connect () {
    setConn('connecting');
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${location.host}/ws`);
    S.ws = ws;
    ws.onopen = () => {
      S.connected = true;
      setConn('connected');
      if (S.joined) send({ type: 'hello', name: prefs.name, color: prefs.color });
      startPings();
    };
    ws.onmessage = (event) => {
      let msg;
      try { msg = JSON.parse(event.data); } catch { return; }
      onMessage(msg);
    };
    ws.onclose = () => {
      S.connected = false;
      clearInterval(pingTimer);
      if (S.ws === ws) {
        setConn('disconnected');
        setTimeout(connect, 2000);
      }
    };
  }
  function setConn (stateName) {
    el.conn.className = `conn ${stateName}`;
    el.conn.title = t(`conn_${stateName}`);
  }

  function onMessage (msg) {
    switch (msg.type) {
      case 'welcome':
        S.clientId = msg.clientId;
        S.clock.samples = [];
        S.clock.offset = msg.serverTime - performance.now();
        S.osEnabled = !!msg.osEnabled;
        S.opening = !!msg.opening;
        S.room = msg.state;
        S.members = msg.members || [];
        if (Array.isArray(msg.palette) && msg.palette.length) S.palette = msg.palette;
        S.progress = msg.progress;
        onMembers();
        applyMedia(msg.media);
        applyTracks(msg.tracks || []);
        renderAll();
        break;
      case 'pong': onPong(msg); break;
      case 'state': {
        const wasRunning = roomRunning();
        S.room = msg;
        if (wasRunning !== roomRunning()) retimeStrokes();
        renderControls(); renderCenter();
        break;
      }
      case 'members': S.members = msg.members || []; onMembers(); renderMembers(); renderCenter(); break;
      case 'media': applyMedia(msg.media); break;
      case 'progress': S.progress = msg; renderMediaInfo(); break;
      case 'subtitles': applyTracks(msg.tracks || []); break;
      case 'status': onStatus(msg); break;
      case 'cursor': onCursor(msg); break;
      case 'poke': if (msg.from !== S.clientId) pokeEffect(msg.from, [msg.x, msg.y]); break;
      case 'draw': onDraw(msg); break;
      case 'draw_clear': clearStrokes(msg.from); break;
      default: break;
    }
  }

  function onStatus (msg) {
    const params = { ...(msg.params || {}) };
    if (params.at !== undefined) params.at = fmtTime(params.at);
    if (msg.key === 'opening') S.opening = true;
    if (msg.key === 'stream_ready' || msg.key === 'open_failed') S.opening = false;
    if (msg.key === 'restarting') return; // the player shows its own loading message
    toast(t(`status_${msg.key}`, params), msg.level === 'error' ? 'error' : 'info');
  }

  // ---------------------------------------------------------------- player
  function applyMedia (media) {
    const changedFilm = (S.media && S.media.mediaKey) !== (media && media.mediaKey);
    S.media = media;
    if (changedFilm) { S.cues.clear(); }
    if (!media) {
      destroyPlayer();
    } else if (media.streamId !== S.streamId) {
      loadStream(media);
    }
    renderAll();
  }

  function destroyPlayer () {
    if (S.hls) { S.hls.destroy(); S.hls = null; }
    video.removeAttribute('src');
    video.load();
    S.streamId = null;
  }

  function loadStream (media) {
    destroyPlayer();
    S.streamId = media.streamId;
    const startLocal = Math.max(0, expectedPosition() - media.streamStart);
    if (window.Hls && Hls.isSupported()) {
      const hls = new Hls({
        startPosition: startLocal,
        maxBufferLength: 60,
        maxMaxBufferLength: 120,
        backBufferLength: 60,
      });
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (!data.fatal) return;
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
          setTimeout(() => { if (S.hls === hls) hls.startLoad(); }, 1500);
        } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
          hls.recoverMediaError();
        } else {
          console.error('hls fatal error', data);
          setTimeout(() => { if (S.hls === hls && S.media) loadStream(S.media); }, 2000);
        }
      });
      hls.on(Hls.Events.INIT_PTS_FOUND, (_event, data) => {
        console.debug('[cowatch] initPTS', data.initPTS / data.timescale, 'streamStart', media.streamStart);
      });
      hls.loadSource(media.url);
      hls.attachMedia(video);
      S.hls = hls;
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = media.url; // Safari plays HLS natively
      video.addEventListener('loadedmetadata', () => seekFilm(expectedPosition()), { once: true });
    } else {
      toast(t('err_no_hls'), 'error');
    }
  }

  function seekFilm (target) {
    if (!S.media) return;
    video.currentTime = Math.max(0, target - S.media.streamStart);
  }
  function setRate (rate) {
    if (video.playbackRate !== rate) video.playbackRate = rate;
  }

  function syncTick () {
    if (!S.joined || !S.media || !S.streamId || video.readyState < 1) return;
    const running = roomRunning();
    const expected = expectedPosition();
    const drift = filmTime() - expected;
    const starving = running && video.readyState < 3; // buffering: let the buffering report handle it
    if (!video.seeking && !starving) {
      if (Math.abs(drift) > (running ? 1.0 : 0.15)) seekFilm(expected);
      else if (running && Math.abs(drift) > 0.1) setRate(drift > 0 ? 0.95 : 1.05);
      else setRate(1);
    }
    if (running && video.paused) {
      video.play().then(() => {
        if (S.autoplayBlocked) { S.autoplayBlocked = false; renderCenter(); }
      }).catch((err) => {
        if (err && err.name === 'NotAllowedError' && !S.autoplayBlocked) { S.autoplayBlocked = true; renderCenter(); }
      });
    } else if (!running && !video.paused) {
      video.pause();
    }
    // Resume only with a few seconds in hand, so a slow viewer does not stop the room every second.
    if (S.bufferingSent && !video.seeking) {
      const ahead = bufferedAhead();
      const nearEnd = filmTime() + ahead >= S.media.duration - 0.5;
      if (ahead >= 4 || nearEnd) reportBuffering(false);
    }
  }

  function bufferedAhead () {
    const ranges = video.buffered;
    const now = video.currentTime;
    for (let i = 0; i < ranges.length; i++) {
      if (ranges.start(i) <= now + 0.1 && ranges.end(i) > now) return ranges.end(i) - now;
    }
    return 0;
  }

  function reportBuffering (value) {
    S.bufferingSent = value;
    send(value ? { type: 'buffering', value, position: filmTime() } : { type: 'buffering', value });
  }
  video.addEventListener('waiting', () => {
    clearTimeout(S.waitTimer);
    S.waitTimer = setTimeout(() => {
      if (S.joined && video.readyState < 3 && roomRunning() && !S.bufferingSent) reportBuffering(true);
    }, 1200);
  });
  video.addEventListener('playing', () => {
    clearTimeout(S.waitTimer);
    if (S.bufferingSent) reportBuffering(false);
  });

  // ---------------------------------------------------------------- commands
  function togglePlay () {
    if (!S.media) return;
    send({ type: S.room.playing ? 'pause' : 'play' });
  }
  function seekTo (target) {
    if (!S.media) return;
    send({ type: 'seek', position: Math.max(0, Math.min(target, S.media.duration)) });
  }
  el.playBtn.addEventListener('click', togglePlay);
  el.backBtn.addEventListener('click', () => seekTo(expectedPosition() - 10));
  el.fwdBtn.addEventListener('click', () => seekTo(expectedPosition() + 10));
  el.seekBar.addEventListener('input', () => {
    S.dragging = true;
    el.timeLabel.textContent = `${fmtTime(Number(el.seekBar.value))} / ${fmtTime(S.media ? S.media.duration : 0)}`;
  });
  el.seekBar.addEventListener('change', () => {
    S.dragging = false;
    seekTo(Number(el.seekBar.value));
  });

  video.volume = prefs.volume;
  video.muted = prefs.muted;
  el.volume.value = prefs.volume;
  el.volume.addEventListener('input', () => {
    video.volume = Number(el.volume.value);
    video.muted = video.volume === 0;
    prefs.volume = video.volume; prefs.muted = video.muted; savePrefs(); renderControls();
  });
  el.muteBtn.addEventListener('click', () => {
    video.muted = !video.muted;
    prefs.muted = video.muted; savePrefs(); renderControls();
  });

  function toggleFullscreen () {
    const fsEl = document.fullscreenElement || document.webkitFullscreenElement;
    if (fsEl) {
      (document.exitFullscreen || document.webkitExitFullscreen).call(document);
    } else {
      const request = el.stage.requestFullscreen || el.stage.webkitRequestFullscreen;
      if (request) request.call(el.stage);
    }
  }
  el.fsBtn.addEventListener('click', toggleFullscreen);
  el.stage.addEventListener('dblclick', (e) => { if (!isUi(e.target) && !S.penMode) toggleFullscreen(); });
  // A click on the picture pokes the others (see presence below); pausing for everyone
  // takes the button or the space key, so nobody stops the film by accident.
  el.stage.addEventListener('click', (e) => {
    if (!isUi(e.target) && S.autoplayBlocked) video.play().catch(() => {});
  });

  document.addEventListener('keydown', (e) => {
    const tag = (e.target && e.target.tagName) || '';
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(tag) || !S.joined) return;
    if (e.code === 'Space' || e.key === 'k') { e.preventDefault(); togglePlay(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); seekTo(expectedPosition() - 10); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); seekTo(expectedPosition() + 10); }
    else if (e.key === 'f') toggleFullscreen();
    else if (e.key === 'm') el.muteBtn.click();
    else if (e.key === 'd') setPen(!S.penMode);
    else if (e.key === 'Escape') { el.palette.hidden = true; if (S.penMode) setPen(false); }
  });

  // Hide the controls while playing and the mouse is still.
  let idleTimer = null;
  function wake () {
    el.stage.classList.remove('idle');
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => { if (roomRunning() && !S.dragging) el.stage.classList.add('idle'); }, 3000);
  }
  el.stage.addEventListener('mousemove', wake);
  el.stage.addEventListener('touchstart', wake, { passive: true });

  // ---------------------------------------------------------------- presence: pointers, pokes, pen
  // Everyone's pointer shows as a ball with their name and colour; a click pokes (the ball
  // blinks and chirps for everyone); the pen draws for everyone. Positions are fractions of
  // the video picture, not of the window, so they land on the same spot of the film on
  // every screen, whatever its size or letterboxing.
  const CURSOR_SEND_MS = 40;
  const CURSOR_IDLE_MS = 4000;
  const STROKE_HOLD_MS = 4000; // a finished stroke stays this long while the film plays
  const STROKE_FADE_MS = 900;
  const MAX_STROKES = 300;
  const MAX_STROKE_POINTS = 4000;

  const isUi = (node) => !!(node && node.closest && node.closest('.controls, .toolbar, .center-msg.clickable'));
  const hovers = (e) => e.pointerType === 'mouse' || e.pointerType === 'pen';
  const memberById = (id) => S.members.find((m) => m.id === id);
  const colorOf = (id) => { const m = memberById(id); return (m && m.color) || '#ffffff'; };
  const myColor = () => { const m = memberById(S.clientId); return (m && m.color) || prefs.color || S.palette[0]; };
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const round4 = (v) => Math.round(v * 10000) / 10000;

  // Where the picture sits inside the stage: object-fit: contain leaves bars around it.
  function geom () {
    const r = el.stage.getBoundingClientRect();
    let w = r.width; let h = r.height;
    const vw = video.videoWidth; const vh = video.videoHeight;
    if (S.media && vw && vh && w && h) {
      const scale = Math.min(w / vw, h / vh);
      w = vw * scale; h = vh * scale;
    }
    return {
      left: r.left, top: r.top, width: r.width, height: r.height,
      ox: (r.width - w) / 2, oy: (r.height - h) / 2, w: w || 1, h: h || 1,
    };
  }
  const toPicture = (e, g) => [round4((e.clientX - g.left - g.ox) / g.w), round4((e.clientY - g.top - g.oy) / g.h)];
  const toStage = (p, g) => [g.ox + p[0] * g.w, g.oy + p[1] * g.h];

  // ---- balls
  function makeBall (me) {
    const node = document.createElement('div');
    node.className = me ? 'ball me gone' : 'ball gone';
    node.innerHTML = '<div class="body"><span class="eye"><i></i></span><span class="eye"><i></i></span></div><span class="tag"></span>';
    el.cursors.appendChild(node);
    return { node, tag: node.querySelector('.tag'), x: 0, y: 0, tx: 0, ty: 0, lx: 0, ly: 0, seen: 0, visible: false };
  }
  const balls = new Map(); // clientId -> the ball of another viewer
  const mine = Object.assign(makeBall(true), { inside: false, overUi: false, sent: false, sx: null, sy: null });

  function paintBall (ball, color, name) {
    ball.node.style.setProperty('--c', color);
    if (ball.tag.textContent !== name) ball.tag.textContent = name;
  }
  function ballFor (id) {
    let ball = balls.get(id);
    if (!ball) {
      ball = makeBall(false);
      balls.set(id, ball);
      const m = memberById(id);
      paintBall(ball, colorOf(id), m ? m.name : '?');
    }
    return ball;
  }
  function showBall (ball, p) {
    ball.tx = p[0]; ball.ty = p[1]; ball.seen = performance.now();
    if (!ball.visible) {
      ball.x = p[0]; ball.y = p[1]; ball.visible = true;
      ball.node.classList.remove('gone');
    }
  }
  function hideBall (ball) {
    ball.visible = false;
    ball.node.classList.add('gone');
  }
  function onCursor (msg) {
    if (!msg.from || msg.from === S.clientId) return;
    const ball = ballFor(msg.from);
    if (msg.hidden) hideBall(ball);
    else showBall(ball, [msg.x, msg.y]);
  }
  function onMembers () {
    const ids = new Set(S.members.map((m) => m.id));
    for (const [id, ball] of balls) {
      if (!ids.has(id)) { ball.node.remove(); balls.delete(id); continue; }
      const m = memberById(id);
      paintBall(ball, m.color || '#ffffff', m.name);
    }
    for (const stroke of strokes.values()) if (!stroke.done && !ids.has(stroke.owner)) finishStroke(stroke);
    const me = memberById(S.clientId);
    if (me && me.color && me.color !== prefs.color) { prefs.color = me.color; savePrefs(); }
    renderToolbar();
  }

  // My own ball replaces the mouse pointer over the picture, so I see what the others see.
  function placeMine (e, g) {
    const sx = e.clientX - g.left; const sy = e.clientY - g.top;
    if (mine.sx !== null) {
      mine.lx = clamp((sx - mine.sx) * 0.6, -2.2, 2.2);
      mine.ly = clamp((sy - mine.sy) * 0.6, -2.2, 2.2);
    }
    mine.sx = sx; mine.sy = sy;
    mine.node.style.transform = `translate3d(${sx}px, ${sy}px, 0)`;
    renderMine();
  }
  function renderMine () {
    const show = !!(S.joined && mine.inside && !mine.overUi && !S.penMode && mine.sx !== null);
    mine.node.classList.toggle('gone', !show);
    el.stage.classList.toggle('ball-cursor', show);
  }

  let cursorTimer = null; let lastCursorAt = 0; let pendingCursor = null;
  function sendCursor (p) {
    pendingCursor = p;
    const wait = CURSOR_SEND_MS - (performance.now() - lastCursorAt);
    if (wait <= 0) flushCursor();
    else if (!cursorTimer) cursorTimer = setTimeout(flushCursor, wait);
  }
  function flushCursor () {
    clearTimeout(cursorTimer); cursorTimer = null;
    if (!pendingCursor) return;
    lastCursorAt = performance.now();
    send({ type: 'cursor', x: pendingCursor[0], y: pendingCursor[1] });
    pendingCursor = null;
    mine.sent = true;
  }
  function withdrawCursor () {
    clearTimeout(cursorTimer); cursorTimer = null; pendingCursor = null;
    if (mine.sent) { send({ type: 'cursor', hidden: true }); mine.sent = false; }
  }

  el.stage.addEventListener('pointermove', (e) => {
    if (!hovers(e) || !S.joined) return;
    const g = geom();
    mine.inside = true;
    mine.overUi = isUi(e.target);
    placeMine(e, g);
    if (!S.penMode) sendCursor(toPicture(e, g));
  });
  el.stage.addEventListener('pointerleave', (e) => {
    if (!hovers(e)) return;
    mine.inside = false;
    renderMine();
    withdrawCursor();
  });

  // ---- pokes
  let lastPokeAt = 0;
  el.stage.addEventListener('pointerdown', (e) => {
    if (!hovers(e) || e.button !== 0 || !S.joined) return;
    if (S.penMode || S.autoplayBlocked || isUi(e.target)) return;
    const now = performance.now();
    if (now - lastPokeAt < 150) return; // the server drops pokes this close together
    lastPokeAt = now;
    const g = geom();
    const p = toPicture(e, g);
    send({ type: 'poke', x: p[0], y: p[1] });
    pokeEffect(S.clientId, p, g);
  });

  function pokeEffect (id, p, g = geom()) {
    const me = id === S.clientId;
    const ball = me ? mine : ballFor(id);
    if (!me) showBall(ball, p);
    const node = ball.node;
    node.classList.remove('blink');
    void node.offsetWidth; // restart the blink animation
    node.classList.add('blink');
    clearTimeout(ball.blinkTimer);
    ball.blinkTimer = setTimeout(() => node.classList.remove('blink'), 420);
    const color = me ? myColor() : colorOf(id);
    const [x, y] = toStage(p, g);
    const ring = document.createElement('span');
    ring.className = 'ripple';
    ring.style.setProperty('--c', color);
    ring.style.left = `${x}px`;
    ring.style.top = `${y}px`;
    el.cursors.appendChild(ring);
    setTimeout(() => ring.remove(), 700);
    if (prefs.sfx) chirp(color);
  }

  // ---- sound: a short synthesised "boop", a whole tone apart per colour, so you hear who poked
  let audioCtx = null;
  function audio () {
    try {
      if (!audioCtx) {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return null;
        audioCtx = new Ctx();
      }
      if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
    } catch { return null; }
    return audioCtx;
  }
  function chirp (color) {
    const ctx = audio();
    if (!ctx || ctx.state !== 'running') return;
    const step = Math.max(0, S.palette.indexOf(color));
    const base = 392 * 2 ** ((step * 2) / 12);
    const t = ctx.currentTime;
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.2, t + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.24);
    gain.connect(ctx.destination);
    const osc = ctx.createOscillator();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(base * 1.9, t);
    osc.frequency.exponentialRampToValueAtTime(base, t + 0.09);
    osc.connect(gain);
    osc.start(t);
    osc.stop(t + 0.26);
  }

  // ---- pen
  const strokes = new Map(); // `${owner}:${id}` -> { id, owner, color, pts, done, fadeAt }
  const drawCtx = el.drawCanvas.getContext('2d');
  let drawDirty = true; let geomKey = '';
  let myStroke = null; let strokeQueue = []; let strokeTimer = null;

  function addStroke (key, id, owner, color) {
    if (strokes.size >= MAX_STROKES) strokes.delete(strokes.keys().next().value);
    const stroke = { id, owner, color, pts: [], done: false, fadeAt: null };
    strokes.set(key, stroke);
    return stroke;
  }
  // While the film plays, a finished stroke fades after a few seconds. While it is paused,
  // strokes stay until playback resumes or someone clears them.
  function finishStroke (stroke) {
    stroke.done = true;
    stroke.fadeAt = roomRunning() ? performance.now() + STROKE_HOLD_MS : null;
    drawDirty = true;
  }
  function retimeStrokes () {
    const running = roomRunning(); const now = performance.now();
    for (const stroke of strokes.values()) {
      if (!stroke.done) continue;
      if (running && stroke.fadeAt === null) stroke.fadeAt = now + 1500;
      else if (!running && stroke.fadeAt !== null && stroke.fadeAt > now) stroke.fadeAt = null;
    }
    drawDirty = true;
  }
  function onDraw (msg) {
    if (!msg.from || msg.from === S.clientId) return;
    const key = `${msg.from}:${msg.stroke}`;
    const stroke = strokes.get(key) || addStroke(key, msg.stroke, msg.from, msg.color || colorOf(msg.from));
    for (const p of msg.points || []) if (stroke.pts.length < MAX_STROKE_POINTS) stroke.pts.push(p);
    if (msg.end) finishStroke(stroke);
    drawDirty = true;
  }
  function clearStrokes (fromId) {
    strokes.clear();
    myStroke = null; strokeQueue = [];
    drawDirty = true;
    if (fromId && fromId !== S.clientId) {
      const m = memberById(fromId);
      toast(t('drawings_cleared', { name: m ? m.name : '?' }), 'info', 2500);
    }
  }

  function setPen (on) {
    S.penMode = on;
    el.stage.classList.toggle('drawing', on);
    el.penBtn.classList.toggle('active', on);
    el.palette.hidden = true;
    if (on) withdrawCursor(); // while drawing, the stroke itself shows where you are
    renderMine();
  }
  el.penBtn.addEventListener('click', () => setPen(!S.penMode));

  el.drawCanvas.addEventListener('pointerdown', (e) => {
    if (!S.penMode || !S.joined || (e.pointerType === 'mouse' && e.button !== 0)) return;
    e.preventDefault();
    el.drawCanvas.setPointerCapture(e.pointerId);
    const id = Math.random().toString(36).slice(2, 10);
    const p = toPicture(e, geom());
    const color = myColor();
    myStroke = addStroke(`${S.clientId}:${id}`, id, S.clientId, color);
    myStroke.pts.push(p);
    strokeQueue = [];
    send({ type: 'draw', id, start: true, color, points: [p] });
    drawDirty = true;
  });
  el.drawCanvas.addEventListener('pointermove', (e) => {
    if (!myStroke) return;
    const g = geom();
    const coalesced = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
    for (const ev of (coalesced.length ? coalesced : [e])) {
      const p = toPicture(ev, g);
      const last = myStroke.pts[myStroke.pts.length - 1];
      if (Math.hypot((p[0] - last[0]) * g.w, (p[1] - last[1]) * g.h) < 2) continue; // under 2 px
      if (myStroke.pts.length >= MAX_STROKE_POINTS) break;
      myStroke.pts.push(p);
      strokeQueue.push(p);
    }
    drawDirty = true;
    if (strokeQueue.length && !strokeTimer) strokeTimer = setTimeout(() => flushStroke(false), 40);
  });
  function flushStroke (end) {
    clearTimeout(strokeTimer); strokeTimer = null;
    if (!myStroke) return;
    do {
      const points = strokeQueue.splice(0, 200);
      const last = end && !strokeQueue.length;
      if (points.length || last) {
        send(last ? { type: 'draw', id: myStroke.id, points, end: true } : { type: 'draw', id: myStroke.id, points });
      }
    } while (strokeQueue.length);
  }
  function endStroke () {
    if (!myStroke) return;
    flushStroke(true);
    finishStroke(myStroke);
    myStroke = null;
  }
  el.drawCanvas.addEventListener('pointerup', endStroke);
  el.drawCanvas.addEventListener('pointercancel', endStroke);

  function renderStrokes (now, g) {
    const canvas = el.drawCanvas;
    const dpr = window.devicePixelRatio || 1;
    const cw = Math.max(1, Math.round(g.width * dpr)); const ch = Math.max(1, Math.round(g.height * dpr));
    if (canvas.width !== cw || canvas.height !== ch) { canvas.width = cw; canvas.height = ch; drawDirty = true; }
    const key = `${g.ox.toFixed(1)},${g.oy.toFixed(1)},${g.w.toFixed(1)},${g.h.toFixed(1)}`;
    if (key !== geomKey) { geomKey = key; drawDirty = true; }
    let fading = false;
    for (const stroke of strokes.values()) {
      if (stroke.fadeAt !== null && now >= stroke.fadeAt) { fading = true; break; }
    }
    if (!drawDirty && !fading) return;
    drawDirty = false;
    const ctx = drawCtx;
    ctx.clearRect(0, 0, cw, ch);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.lineWidth = Math.max(4, g.h * 0.009) * dpr; // a marker: about 10 px on a 1080p picture
    ctx.shadowColor = 'rgba(0, 0, 0, .55)';
    ctx.shadowBlur = 3 * dpr;
    const at = (p) => [(g.ox + p[0] * g.w) * dpr, (g.oy + p[1] * g.h) * dpr];
    for (const [strokeKey, stroke] of strokes) {
      let alpha = 1;
      if (stroke.fadeAt !== null && now >= stroke.fadeAt) {
        alpha = 1 - (now - stroke.fadeAt) / STROKE_FADE_MS;
        if (alpha <= 0) { strokes.delete(strokeKey); continue; }
      }
      const pts = stroke.pts;
      if (!pts.length) continue;
      ctx.globalAlpha = alpha;
      ctx.strokeStyle = stroke.color;
      ctx.fillStyle = stroke.color;
      const first = at(pts[0]);
      ctx.beginPath();
      if (pts.length === 1) {
        ctx.arc(first[0], first[1], ctx.lineWidth / 2, 0, Math.PI * 2);
        ctx.fill();
        continue;
      }
      ctx.moveTo(first[0], first[1]);
      for (let i = 1; i < pts.length - 1; i++) {
        const a = at(pts[i]); const b = at(pts[i + 1]);
        ctx.quadraticCurveTo(a[0], a[1], (a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
      }
      const last = at(pts[pts.length - 1]);
      ctx.lineTo(last[0], last[1]);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  let lastFrameAt = 0;
  function animateBalls (now, g) {
    const dt = Math.min(100, now - (lastFrameAt || now));
    lastFrameAt = now;
    const k = 1 - Math.exp(-dt / 50);
    for (const ball of balls.values()) {
      if (!ball.visible) continue;
      if (now - ball.seen > CURSOR_IDLE_MS) { hideBall(ball); continue; }
      const nx = ball.x + (ball.tx - ball.x) * k; const ny = ball.y + (ball.ty - ball.y) * k;
      // The eyes look where the ball is heading.
      ball.lx += (clamp((nx - ball.x) * g.w * 0.8, -2.2, 2.2) - ball.lx) * 0.3;
      ball.ly += (clamp((ny - ball.y) * g.h * 0.8, -2.2, 2.2) - ball.ly) * 0.3;
      ball.x = nx; ball.y = ny;
      const [x, y] = toStage([nx, ny], g);
      ball.node.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0)`;
      ball.node.style.setProperty('--lx', `${ball.lx.toFixed(2)}px`);
      ball.node.style.setProperty('--ly', `${ball.ly.toFixed(2)}px`);
    }
    if (Math.abs(mine.lx) > 0.02 || Math.abs(mine.ly) > 0.02) {
      mine.lx *= 0.88; mine.ly *= 0.88;
      mine.node.style.setProperty('--lx', `${mine.lx.toFixed(2)}px`);
      mine.node.style.setProperty('--ly', `${mine.ly.toFixed(2)}px`);
    }
  }

  // ---- toolbar
  function renderToolbar () {
    const color = myColor();
    el.stage.style.setProperty('--me', color);
    el.sfxBtn.classList.toggle('off', !prefs.sfx);
    paintBall(mine, color, prefs.name || '?');
    if (!el.palette.hidden) renderPalette();
  }
  function renderPalette () {
    el.palette.replaceChildren();
    const current = myColor();
    for (const color of S.palette) {
      const swatch = document.createElement('button');
      swatch.type = 'button';
      swatch.style.setProperty('--c', color);
      swatch.classList.toggle('sel', color === current);
      swatch.addEventListener('click', () => pickColor(color));
      el.palette.appendChild(swatch);
    }
  }
  function pickColor (color) {
    prefs.color = color; savePrefs();
    const me = memberById(S.clientId);
    if (me) me.color = color; // shown right away; the server confirms with a members message
    send({ type: 'color', color });
    el.palette.hidden = true;
    onMembers();
    renderMembers();
  }
  el.colorBtn.addEventListener('click', () => {
    el.palette.hidden = !el.palette.hidden;
    if (!el.palette.hidden) renderPalette();
  });
  el.clearBtn.addEventListener('click', () => { clearStrokes(); send({ type: 'draw_clear' }); });
  el.sfxBtn.addEventListener('click', () => {
    prefs.sfx = !prefs.sfx; savePrefs(); renderToolbar();
    if (prefs.sfx) chirp(myColor());
  });
  document.addEventListener('pointerdown', (e) => {
    if (!el.palette.hidden && !el.toolbar.contains(e.target)) el.palette.hidden = true;
  });

  // ---------------------------------------------------------------- subtitles
  function activeText (trackId, time) {
    const cues = S.cues.get(trackId);
    if (!cues || !cues.length) return '';
    let lo = 0; let hi = cues.length - 1; let idx = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (cues[mid][0] <= time) { idx = mid; lo = mid + 1; } else { hi = mid - 1; }
    }
    const lines = [];
    for (let i = idx; i >= 0 && i > idx - 8; i--) {
      if (cues[i][1] > time) lines.unshift(cues[i][2]);
    }
    return lines.join('\n');
  }
  function setSubText (node, text) {
    if (node.textContent !== text) node.textContent = text;
    node.hidden = !text;
  }

  async function ensureCues (trackId) {
    if (!trackId || S.cues.has(trackId)) return;
    S.cues.set(trackId, []);
    try {
      const data = await api(`/api/subtitles/${trackId}.json`);
      S.cues.set(trackId, data.cues || []);
    } catch (err) {
      S.cues.delete(trackId);
      toast(errorText(err), 'error');
    }
  }

  function applyTracks (tracks) {
    S.tracks = tracks;
    const ids = new Set(tracks.map((tr) => tr.id));
    if (S.primary && !ids.has(S.primary)) S.primary = '';
    if (S.secondary && !ids.has(S.secondary)) S.secondary = '';
    if (!S.primary && prefs.primaryLang) {
      const match = tracks.find((tr) => tr.lang === prefs.primaryLang);
      if (match) S.primary = match.id;
    }
    if (!S.secondary && prefs.secondaryLang) {
      const match = tracks.find((tr) => tr.lang === prefs.secondaryLang && tr.id !== S.primary);
      if (match) S.secondary = match.id;
    }
    ensureCues(S.primary);
    ensureCues(S.secondary);
    renderTracks();
  }

  function selectTrack (slot, trackId) {
    const track = S.tracks.find((tr) => tr.id === trackId);
    if (slot === 'primary') {
      S.primary = trackId;
      prefs.primaryLang = track ? track.lang : '';
    } else {
      S.secondary = trackId;
      prefs.secondaryLang = track ? track.lang : '';
    }
    savePrefs();
    ensureCues(trackId);
    renderTracks();
    renderAll();
  }
  el.primarySel.addEventListener('change', () => selectTrack('primary', el.primarySel.value));
  el.secondarySel.addEventListener('change', () => selectTrack('secondary', el.secondarySel.value));

  document.querySelectorAll('[data-off]').forEach((btn) => {
    btn.addEventListener('click', () => {
      prefs.offsetMs = btn.dataset.off === 'reset' ? 0 : prefs.offsetMs + Number(btn.dataset.off);
      savePrefs(); renderSubStyle();
    });
  });
  el.sizeRange.addEventListener('input', () => { prefs.fontSize = Number(el.sizeRange.value); savePrefs(); renderSubStyle(); });
  el.bottomRange.addEventListener('input', () => { prefs.bottom = Number(el.bottomRange.value); savePrefs(); renderSubStyle(); });

  el.searchForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const languages = el.searchLangs.value.split(/[\s,;]+/).map((s) => s.trim().toLowerCase()).filter(Boolean);
    if (!languages.length) return;
    prefs.searchLangs = el.searchLangs.value; savePrefs();
    const btn = el.searchForm.querySelector('button');
    btn.disabled = true;
    toast(t('search_running'));
    try {
      const result = await api('/api/subtitles/search', { json: { languages } });
      toast(t('search_result', { added: result.added.length }));
      if (result.notFound && result.notFound.length) toast(t('search_missing', { langs: result.notFound.join(', ') }), 'error');
      if (!S.primary && result.added.length) selectTrack('primary', result.added[0].id);
    } catch (err) {
      toast(errorText(err), 'error');
    } finally {
      btn.disabled = false;
    }
  });

  el.uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const file = el.subFile.files[0];
    const lang = el.subLang.value.trim().toLowerCase();
    if (!file || !lang) { (file ? el.subLang : el.subFile).focus(); return; }
    const form = new FormData();
    form.append('file', file);
    form.append('lang', lang);
    form.append('label', file.name);
    const btn = el.uploadForm.querySelector('button');
    btn.disabled = true;
    try {
      const track = await api('/api/subtitles/upload', { method: 'POST', body: form });
      toast(t('uploaded', { label: track.label }));
      el.subFile.value = '';
      if (!S.primary) selectTrack('primary', track.id);
    } catch (err) {
      toast(errorText(err), 'error');
    } finally {
      btn.disabled = false;
    }
  });

  // ---------------------------------------------------------------- media panel
  el.magnetForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const magnet = el.magnetInput.value.trim();
    if (!magnet) return;
    const btn = el.magnetForm.querySelector('button');
    btn.disabled = true;
    el.fileList.hidden = true;
    toast(t('torrent_adding'));
    try {
      const info = await api('/api/torrent/add', { json: { magnet } });
      const videos = info.files.filter((f) => f.isVideo).sort((a, b) => b.length - a.length);
      const choices = videos.length ? videos : info.files;
      if (choices.length === 1) {
        await openTorrent(info.infoHash, choices[0].index);
      } else {
        renderFileChoices(info.infoHash, choices);
      }
      el.magnetInput.value = '';
    } catch (err) {
      toast(errorText(err), 'error');
    } finally {
      btn.disabled = false;
    }
  });

  function renderFileChoices (infoHash, files) {
    el.fileList.replaceChildren();
    const title = document.createElement('p');
    title.textContent = t('choose_file');
    el.fileList.appendChild(title);
    for (const f of files) {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = `${f.name} · ${fmtBytes(f.length)}`;
      b.addEventListener('click', () => { el.fileList.hidden = true; openTorrent(infoHash, f.index); });
      el.fileList.appendChild(b);
    }
    el.fileList.hidden = false;
  }

  async function openTorrent (infoHash, fileIndex) {
    try {
      await api('/api/media/open', { json: { torrent: { infoHash, fileIndex } } });
    } catch (err) {
      toast(errorText(err), 'error');
    }
  }

  el.pathForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const path = el.pathInput.value.trim().replace(/^"(.*)"$/, '$1');
    if (!path) return;
    try {
      await api('/api/media/open', { json: { path } });
    } catch (err) {
      toast(errorText(err), 'error');
    }
  });

  el.closeMedia.addEventListener('click', async () => {
    try { await api('/api/media/close', { method: 'POST' }); } catch (err) { toast(errorText(err), 'error'); }
  });

  async function pollStatus () {
    try {
      const status = await api('/api/status');
      S.isHost = !!status.isHost;
      S.osEnabled = !!status.osEnabled;
      S.torrent = status.torrent;
      S.downloadThrottled = !!status.downloadThrottled;
      if (status.progress) S.progress = status.progress;
      renderMediaPanel();
    } catch { /* offline: the websocket indicator already shows it */ }
  }

  // ---------------------------------------------------------------- join
  el.nameInput.value = prefs.name;
  el.joinForm.addEventListener('submit', (e) => {
    e.preventDefault();
    prefs.name = el.nameInput.value.trim().slice(0, 24) || '?';
    prefs.uiLang = el.joinLang.value;
    savePrefs();
    S.joined = true;
    el.joinOverlay.hidden = true;
    // Called inside the click, so the browser allows sound for later play() calls
    // and for the poke sounds.
    video.play().then(() => { if (!roomRunning()) video.pause(); }).catch(() => {});
    audio();
    send({ type: 'hello', name: prefs.name, color: prefs.color });
    applyI18n();
  });

  function fillLangSelect (select) {
    select.replaceChildren();
    for (const [code, name] of Object.entries(UI_LANGS)) {
      const option = document.createElement('option');
      option.value = code; option.textContent = name;
      select.appendChild(option);
    }
    select.value = prefs.uiLang;
  }
  fillLangSelect(el.uiLang);
  fillLangSelect(el.joinLang);
  el.joinLang.addEventListener('change', () => { prefs.uiLang = el.joinLang.value; savePrefs(); applyI18n(); });
  el.uiLang.addEventListener('change', () => { prefs.uiLang = el.uiLang.value; savePrefs(); applyI18n(); });

  // ---------------------------------------------------------------- rendering
  function renderAll () {
    renderControls(); renderMembers(); renderMediaPanel(); renderTracks(); renderSubStyle(); renderCenter();
    renderToolbar();
    el.uiLang.value = prefs.uiLang;
    el.joinLang.value = prefs.uiLang;
    if (document.activeElement !== el.searchLangs) {
      el.searchLangs.value = prefs.searchLangs || [prefs.primaryLang, prefs.secondaryLang, 'en']
        .filter((v, i, a) => v && a.indexOf(v) === i).join(',');
    }
  }

  function renderControls () {
    el.playBtn.classList.toggle('playing', !!S.room.playing);
    el.muteBtn.classList.toggle('muted', video.muted);
    const disabled = !S.media;
    for (const node of [el.playBtn, el.backBtn, el.fwdBtn, el.seekBar]) node.disabled = disabled;
    if (!roomRunning()) el.stage.classList.remove('idle');
  }

  function renderMembers () {
    el.members.replaceChildren();
    for (const m of S.members) {
      const chip = document.createElement('span');
      chip.className = 'member';
      if (m.color) chip.style.setProperty('--c', m.color);
      if (m.id === S.clientId) chip.classList.add('me');
      if (m.buffering) { chip.classList.add('buffering'); chip.title = t('buffering'); }
      chip.textContent = m.id === S.clientId ? `${m.name} (${t('you')})` : m.name;
      el.members.appendChild(chip);
    }
  }

  function renderCenter () {
    let text = '';
    let clickable = false;
    if (S.media) {
      if (S.room.loading) {
        text = t('loading_stream');
      } else if (S.room.waiting && S.room.waiting.length) {
        const names = S.members.filter((m) => S.room.waiting.includes(m.id)).map((m) => m.name);
        text = t('waiting_for', { names: names.join(', ') || '…' });
      } else if (S.autoplayBlocked && S.joined) {
        text = t('autoplay_blocked'); clickable = true;
      }
    }
    el.centerMsg.textContent = text;
    el.centerMsg.hidden = !text;
    el.centerMsg.classList.toggle('clickable', clickable);
    el.empty.hidden = !!S.media;
  }

  function renderMediaPanel () {
    el.pathForm.hidden = !S.isHost;
    el.hostHint.hidden = S.isHost;
    el.closeMedia.hidden = !S.media;
    el.osOff.hidden = S.osEnabled;
    el.filmTitle.textContent = S.media ? S.media.title : '';
    renderMediaInfo();
    renderTorrentInfo();
  }

  function renderMediaInfo () {
    const m = S.media;
    el.mediaInfo.replaceChildren();
    if (!m) return;
    const parts = [
      m.mode === 'copy' ? t('mode_copy') : t('mode_transcode'),
      `${(m.videoCodec || '').toUpperCase()} ${m.width || '?'}×${m.height || '?'}`,
      m.bitrateKbps ? `${(m.bitrateKbps / 1000).toFixed(1)} Mbps` : '',
      m.audio ? `${(m.audio.codec || '').toUpperCase()} ${m.audio.channels || ''}ch → AAC 2.0` : '',
    ].filter(Boolean);
    const line = document.createElement('div');
    const strong = document.createElement('b');
    strong.textContent = m.title;
    line.append(strong, document.createElement('br'), parts.join(' · '));
    el.mediaInfo.appendChild(line);
    const p = S.progress;
    if (p && p.streamId === m.streamId) {
      const prog = document.createElement('div');
      prog.textContent = p.ended && m.streamStart < 1
        ? t('produced_done')
        : t('produced', { from: fmtTime(m.streamStart), to: fmtTime(p.producedEnd) });
      el.mediaInfo.appendChild(prog);
    }
  }

  function renderTorrentInfo () {
    const tor = S.torrent;
    if (!tor || !S.media || S.media.source !== 'torrent') { el.torrentInfo.textContent = ''; return; }
    el.torrentInfo.textContent = t('torrent_stats', {
      pct: (tor.progress * 100).toFixed(1),
      down: fmtBytes(tor.downloadSpeed),
      up: fmtBytes(tor.uploadSpeed),
      peers: tor.numPeers,
    }) + (S.downloadThrottled ? ` ${t('torrent_throttled')}` : '');
  }

  function trackLabel (track) {
    const name = langName(track.lang);
    return `${name} · ${track.label}${track.hashMatch ? ' ✓' : ''}`;
  }

  function renderTracks () {
    for (const [select, current] of [[el.primarySel, S.primary], [el.secondarySel, S.secondary]]) {
      select.replaceChildren();
      const none = document.createElement('option');
      none.value = ''; none.textContent = t('subs_none');
      select.appendChild(none);
      for (const track of S.tracks) {
        const option = document.createElement('option');
        option.value = track.id;
        option.textContent = trackLabel(track);
        select.appendChild(option);
      }
      select.value = current || '';
    }
    el.trackList.replaceChildren();
    if (!S.tracks.length) {
      const li = document.createElement('li');
      li.textContent = t('subs_empty');
      el.trackList.appendChild(li);
      return;
    }
    for (const track of S.tracks) {
      const li = document.createElement('li');
      const lang = document.createElement('span'); lang.className = 'lang'; lang.textContent = track.lang.toUpperCase();
      const label = document.createElement('span'); label.className = 'label'; label.textContent = track.label; label.title = track.label;
      li.append(lang, label);
      if (track.hashMatch) {
        const badge = document.createElement('span'); badge.className = 'badge'; badge.textContent = t('hash_match');
        li.appendChild(badge);
      }
      const del = document.createElement('button');
      del.type = 'button'; del.className = 'ghost'; del.textContent = t('delete');
      del.addEventListener('click', async () => {
        if (!confirm(t('confirm_delete'))) return;
        try { await api(`/api/subtitles/${track.id}`, { method: 'DELETE' }); } catch (err) { toast(errorText(err), 'error'); }
      });
      li.appendChild(del);
      el.trackList.appendChild(li);
    }
  }

  function renderSubStyle () {
    document.documentElement.style.setProperty('--sub-scale', String(prefs.fontSize / 100));
    document.documentElement.style.setProperty('--sub-bottom', `${prefs.bottom}%`);
    el.sizeRange.value = prefs.fontSize;
    el.bottomRange.value = prefs.bottom;
    const sec = prefs.offsetMs / 1000;
    el.offsetOut.textContent = `${sec > 0 ? '+' : ''}${sec.toFixed(1)} s`;
  }

  let lastUi = 0;
  function frame (now) {
    const g = geom();
    animateBalls(now, g);
    renderStrokes(now, g);
    if (S.media) {
      const time = filmTime() - prefs.offsetMs / 1000;
      setSubText(el.subPrimary, S.primary ? activeText(S.primary, time) : '');
      setSubText(el.subSecondary, S.secondary && S.secondary !== S.primary ? activeText(S.secondary, time) : '');
    } else {
      setSubText(el.subPrimary, '');
      setSubText(el.subSecondary, '');
    }
    if (now - lastUi > 250) {
      lastUi = now;
      el.clearBtn.disabled = !strokes.size;
      const duration = S.media ? S.media.duration : 0;
      el.seekBar.max = String(Math.max(duration, 1));
      if (!S.dragging) {
        const shown = S.media ? (video.readyState ? filmTime() : expectedPosition()) : 0;
        el.seekBar.value = String(shown);
        el.timeLabel.textContent = `${fmtTime(shown)} / ${fmtTime(duration)}`;
      }
      const p = S.progress;
      if (S.media && duration > 0 && p && p.streamId === S.media.streamId) {
        const start = S.media.streamStart / duration;
        const end = Math.min(1, p.producedEnd / duration);
        el.produced.style.left = `${start * 100}%`;
        el.produced.style.width = `${Math.max(0, end - start) * 100}%`;
      } else {
        el.produced.style.width = '0';
      }
    }
    requestAnimationFrame(frame);
  }

  // For the browser console: cowatchDebug() shows the sync numbers.
  window.cowatchDebug = () => ({
    filmTime: filmTime(), expected: expectedPosition(), drift: filmTime() - expectedPosition(),
    room: S.room, media: S.media, clockOffset: S.clock.offset, rate: video.playbackRate,
    readyState: video.readyState, primary: S.primary, secondary: S.secondary,
    clientId: S.clientId, members: S.members, penMode: S.penMode, strokes: strokes.size, balls: [...balls.keys()],
  });

  // ---------------------------------------------------------------- start
  applyI18n();
  connect();
  pollStatus();
  setInterval(pollStatus, 3000);
  setInterval(syncTick, 250);
  requestAnimationFrame(frame);
})();
