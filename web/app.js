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
    micBtn: $('#micBtn'), micMenuBtn: $('#micMenuBtn'), micMenu: $('#micMenu'), micDevice: $('#micDevice'),
    duckCheck: $('#duckCheck'), peerPop: $('#peerPop'), peerPopName: $('#peerPopName'), peerVol: $('#peerVol'),
    voices: $('#voices'), camBtn: $('#camBtn'), camMenuBtn: $('#camMenuBtn'), camMenu: $('#camMenu'),
    camDevice: $('#camDevice'), selfCheck: $('#selfCheck'), camsCheck: $('#camsCheck'), cams: $('#cams'),
    preview: $('#preview'), previewVideo: $('#previewVideo'), previewMeter: $('#previewMeter'),
    preMicBtn: $('#preMicBtn'), preCamBtn: $('#preCamBtn'),
    camsBox: $('#camsBox'), camsSizeBtn: $('#camsSizeBtn'), sideLeft: $('#sideLeft'), sideRight: $('#sideRight'),
    catalogSel: $('#catalogSel'), browseSearch: $('#browseSearch'), browseQuery: $('#browseQuery'),
    addonsBtn: $('#addonsBtn'), addonsPanel: $('#addonsPanel'), addonList: $('#addonList'), addonForm: $('#addonForm'),
    addonUrl: $('#addonUrl'), addonsNote: $('#addonsNote'), addonsHostOnly: $('#addonsHostOnly'),
    browseList: $('#browseList'), browseGrid: $('#browseGrid'), browseStatus: $('#browseStatus'), browseMore: $('#browseMore'),
    titleView: $('#titleView'), titleBack: $('#titleBack'), titlePoster: $('#titlePoster'), titleName: $('#titleName'),
    titleMeta: $('#titleMeta'), titleDesc: $('#titleDesc'), episodes: $('#episodes'), seasonSel: $('#seasonSel'),
    episodeList: $('#episodeList'), streamList: $('#streamList'),
    addonSubs: $('#addonSubs'), addonSubsBtn: $('#addonSubsBtn'), addonSubsList: $('#addonSubsList'),
  };
  const video = el.video;

  // ---------------------------------------------------------------- preferences
  const PREFS_KEY = 'cowatch.prefs.v1';
  const DEFAULT_PREFS = {
    name: '', uiLang: detectUiLang(), primaryLang: '', secondaryLang: '', offsetMs: 0,
    fontSize: 100, bottom: 8, searchLangs: '', volume: 1, muted: false, color: '', sfx: true,
    micDevice: '', duck: true, peerVolume: {}, micHintShown: false, camDevice: '', showSelf: true, showCams: true,
    camCorner: 'tr', camsSmall: false, browseCatalog: '',
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
    penMode: false, iceServers: [],
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
      if (S.joined) sendHello();
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
        clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(connect, 2000);
      }
    };
  }
  // Back on the network (Wi-Fi again, laptop woke up): reconnect now instead of at the next try.
  let reconnectTimer = null;
  window.addEventListener('online', () => {
    if (S.ws && S.ws.readyState === WebSocket.CLOSED) { clearTimeout(reconnectTimer); connect(); }
  });
  function setConn (stateName) {
    el.conn.className = `conn ${stateName}`;
    el.conn.title = t(`conn_${stateName}`);
  }

  function onMessage (msg) {
    switch (msg.type) {
      case 'welcome':
        // A new connection means a new id: connections to the others were made for the old one.
        closeAllPeers();
        S.clientId = msg.clientId;
        S.iceServers = Array.isArray(msg.iceServers) ? msg.iceServers : [];
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
      case 'rtc': onRtc(msg); break;
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
    if (changedFilm) { S.cues.clear(); el.addonSubsList.replaceChildren(); }
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

  // The slider sets prefs.volume; while someone talks the film plays at a fraction of it (duck,
  // see voice below), without moving the slider.
  let duck = 1;
  function applyFilmVolume () {
    video.volume = Math.min(1, Math.max(0, prefs.volume * duck));
  }
  applyFilmVolume();
  video.muted = prefs.muted;
  el.volume.value = prefs.volume;
  el.volume.addEventListener('input', () => {
    prefs.volume = Number(el.volume.value);
    video.muted = prefs.volume === 0;
    prefs.muted = video.muted; savePrefs(); applyFilmVolume(); renderControls();
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
    if (!S.joined) return;
    // Ctrl+D microphone, Ctrl+E camera (Cmd on a Mac), as in Meet, even while typing.
    if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && ['d', 'e'].includes(e.key.toLowerCase())) {
      e.preventDefault();
      if (e.key.toLowerCase() === 'd') toggleMic(); else toggleCam();
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return; // browser shortcuts, not ours
    const tag = (e.target && e.target.tagName) || '';
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(tag)) return;
    if (e.code === 'Space' || e.key === 'k') { e.preventDefault(); togglePlay(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); seekTo(expectedPosition() - 10); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); seekTo(expectedPosition() + 10); }
    else if (e.key === 'f') toggleFullscreen();
    else if (e.key === 'm') el.muteBtn.click();
    else if (e.key === 'd') setPen(!S.penMode);
    else if (e.key === 'Escape') {
      el.palette.hidden = true; el.micMenu.hidden = true; el.camMenu.hidden = true; el.peerPop.hidden = true;
      if (S.penMode) setPen(false);
    }
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

  const isUi = (node) => !!(node && node.closest && node.closest('.controls, .toolbar, .cams-box, .center-msg.clickable'));
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
    syncPeers();
    renderCams();
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
    for (const menu of [el.micMenu, el.camMenu]) {
      if (!menu.hidden && !menu.parentNode.contains(e.target)) menu.hidden = true;
    }
    if (!el.peerPop.hidden && !el.peerPop.contains(e.target) && !el.members.contains(e.target) && !el.camsBox.contains(e.target)) {
      el.peerPop.hidden = true;
    }
  });

  // ---------------------------------------------------------------- voice and camera
  // Sound and picture go straight between the viewers' browsers (WebRTC), one connection per
  // pair; the server only passes the setup messages ("rtc") along. The viewer with the smaller
  // id makes the offer and adds both transceivers (sound, camera); the other one takes them
  // over from the offer. Turning the microphone or camera on or off only swaps the track on
  // those transceivers (replaceTrack), so it never needs a new offer. Perfect negotiation:
  // https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API/Perfect_negotiation
  const SPEAK_LEVEL = 0.025; // audio level (0-1, linear) that counts as talking
  const SPEAK_AFTER_MS = 150; // loud this long before someone counts as talking
  const QUIET_AFTER_MS = 300; // the glow goes after this much quiet
  const UNDUCK_AFTER_MS = 800; // the film comes back up after this much quiet
  const DUCK_TO = 0.5;
  // Small tiles need little: this keeps a camera at about half a megabit per viewer, and
  // under congestion the picture gives way before the sound.
  const SENDER_LIMITS = {
    audio: { priority: 'high', networkPriority: 'high' },
    video: { maxBitrate: 500000, maxFramerate: 24, priority: 'low', networkPriority: 'low' },
  };
  const peers = new Map(); // member id -> peer
  const voice = {
    mic: null, cam: null, camStream: null, busy: { mic: false, cam: false }, analyser: null, source: null, buf: null,
  };
  const loud = new Map(); // member id -> { since, last }: when they started, and last were, loud
  const speaking = new Set();

  function sendHello () {
    send({ type: 'hello', name: prefs.name, color: prefs.color, mic: !!voice.mic, cam: !!voice.cam });
  }
  const sendAv = () => send({ type: 'av', mic: !!voice.mic, cam: !!voice.cam });
  const sendRtc = (to, data) => send({ type: 'rtc', to, data });

  function syncPeers () {
    if (!S.joined || !S.clientId || !window.RTCPeerConnection) return;
    const want = new Set(S.members.filter((m) => m.joined && m.id !== S.clientId).map((m) => m.id));
    for (const id of peers.keys()) if (!want.has(id)) closePeer(id);
    for (const id of want) if (!peers.has(id)) makePeer(id);
    for (const peer of peers.values()) applyPeerVolume(peer);
  }

  function makePeer (id) {
    const pc = new RTCPeerConnection({ iceServers: S.iceServers });
    const audioEl = document.createElement('audio');
    audioEl.autoplay = true;
    el.voices.appendChild(audioEl);
    const peer = {
      id, pc, audioEl, polite: S.clientId > id, makingOffer: false, ignoreOffer: false,
      audioTx: null, videoTx: null, videoStream: null, queue: Promise.resolve(),
      badSince: performance.now(), restarted: false, // see peerWatch
    };
    peers.set(id, peer);
    pc.onicecandidate = ({ candidate }) => sendRtc(id, { candidate: candidate ? candidate.toJSON() : null });
    pc.onnegotiationneeded = async () => {
      try {
        peer.makingOffer = true;
        await pc.setLocalDescription();
        sendRtc(id, { description: pc.localDescription.toJSON() });
      } catch (err) {
        console.warn('[cowatch] offer', err);
      } finally {
        peer.makingOffer = false;
      }
    };
    pc.ontrack = ({ track }) => {
      if (track.kind === 'video') {
        peer.videoStream = new MediaStream([track]); // shown in their tile while their camera is on
        renderCams();
        return;
      }
      audioEl.srcObject = new MediaStream([track]);
      audioEl.play().catch(() => {});
    };
    pc.onconnectionstatechange = () => {
      if (pc.connectionState === 'connected') limitSenders(peer);
      else if (pc.connectionState === 'failed' && !peer.restarted) { peer.restarted = true; pc.restartIce(); }
    };
    applyPeerVolume(peer);
    if (!peer.polite) {
      peer.audioTx = pc.addTransceiver('audio', { direction: 'sendrecv' });
      peer.videoTx = pc.addTransceiver('video', { direction: 'sendrecv' });
      applyLocalTracks(peer);
    }
    return peer;
  }

  function closePeer (id) {
    const peer = peers.get(id);
    if (!peer) return;
    peers.delete(id);
    peer.pc.close();
    peer.audioEl.srcObject = null;
    peer.audioEl.remove();
    loud.delete(id);
    speaking.delete(id);
  }
  function closeAllPeers () {
    for (const id of [...peers.keys()]) closePeer(id);
  }

  // A connection that drops (network change, sleep, Wi-Fi hop) mends itself: first a new ICE
  // round on the same connection; if it is still down after PEER_RESET_MS, the offering side
  // throws it away, builds a fresh one and tells the other side to do the same ("reset").
  const PEER_RESET_MS = 20000;
  function resetPeer (id) {
    const old = peers.get(id);
    if (!old) return;
    closePeer(id);
    makePeer(id);
    sendRtc(id, { reset: true }); // sent before the new offer, which waits for negotiationneeded
    renderCams();
  }
  function peerWatch () {
    const now = performance.now();
    for (const peer of [...peers.values()]) {
      const state = peer.pc.connectionState;
      if (state === 'connected') { peer.badSince = null; peer.restarted = false; continue; }
      if (peer.badSince === null) peer.badSince = now;
      const down = now - peer.badSince;
      if (!peer.restarted && (state === 'failed' || (state === 'disconnected' && down > 4000))) {
        peer.restarted = true;
        peer.pc.restartIce();
      } else if (down > PEER_RESET_MS && !peer.polite) {
        console.info('[cowatch] rebuilding the connection to', peer.id);
        resetPeer(peer.id);
      }
    }
  }

  // The polite side takes over the transceivers the offer created and sends on them too.
  function adoptTransceivers (peer) {
    for (const tx of peer.pc.getTransceivers()) {
      const kind = tx.receiver.track.kind;
      if (kind === 'audio' && !peer.audioTx) peer.audioTx = tx;
      else if (kind === 'video' && !peer.videoTx) peer.videoTx = tx;
      else continue;
      if (tx.direction !== 'sendrecv') tx.direction = 'sendrecv';
    }
    applyLocalTracks(peer);
  }
  function applyLocalTracks (peer) {
    for (const [tx, track] of [[peer.audioTx, voice.mic], [peer.videoTx, voice.cam]]) {
      if (tx && tx.sender.track !== track) {
        tx.sender.replaceTrack(track).catch((err) => console.warn('[cowatch] replaceTrack', err));
      }
    }
    limitSenders(peer);
  }
  // Encodings exist only once the connection is negotiated; until then this does nothing and
  // runs again when the connection comes up.
  async function limitSenders (peer) {
    for (const [tx, limits] of [[peer.audioTx, SENDER_LIMITS.audio], [peer.videoTx, SENDER_LIMITS.video]]) {
      if (!tx || peer.pc.signalingState === 'closed') continue;
      const params = tx.sender.getParameters();
      const enc = params.encodings && params.encodings[0];
      if (!enc || Object.entries(limits).every(([k, v]) => enc[k] === v)) continue;
      Object.assign(enc, limits);
      try { await tx.sender.setParameters(params); } catch (err) { console.warn('[cowatch] setParameters', err); }
    }
  }

  function onRtc (msg) {
    const m = memberById(msg.from);
    const allowed = S.joined && m && m.joined && window.RTCPeerConnection;
    if (msg.data && msg.data.reset) { // the other side rebuilt: start over here too (no reset back)
      closePeer(msg.from);
      if (allowed) makePeer(msg.from);
      renderCams();
      return;
    }
    let peer = peers.get(msg.from);
    if (!peer) {
      if (!allowed) return;
      peer = makePeer(msg.from);
    }
    // One at a time per peer: a candidate must not overtake the description it belongs to.
    peer.queue = peer.queue.then(() => handleRtc(peer, msg.data || {})).catch((err) => console.warn('[cowatch] rtc', err));
  }
  async function handleRtc (peer, data) {
    const { pc } = peer;
    if (pc.signalingState === 'closed') return;
    if (data.description) {
      const offer = data.description.type === 'offer';
      const collision = offer && (peer.makingOffer || pc.signalingState !== 'stable');
      peer.ignoreOffer = !peer.polite && collision;
      if (peer.ignoreOffer) return;
      await pc.setRemoteDescription(data.description);
      if (offer) {
        adoptTransceivers(peer);
        await pc.setLocalDescription();
        sendRtc(peer.id, { description: pc.localDescription.toJSON() });
      }
    } else if ('candidate' in data) {
      try {
        await pc.addIceCandidate(data.candidate || undefined);
      } catch (err) {
        if (!peer.ignoreOffer) throw err;
      }
    }
  }

  // ---- microphone and camera: the same steps for both
  const DEVICES = {
    mic: {
      media: 'audio', kind: 'audioinput', pref: 'micDevice',
      constraints: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    },
    cam: {
      media: 'video', kind: 'videoinput', pref: 'camDevice',
      constraints: { width: { ideal: 640 }, height: { ideal: 360 }, frameRate: { ideal: 24, max: 30 } },
    },
  };
  function deviceErrorText (what, err) {
    const name = err && err.name;
    if (name === 'NotAllowedError' || name === 'SecurityError') return t(`err_${what}_denied`);
    if (name === 'NotFoundError') return t(`err_${what}_missing`);
    if (name === 'NotReadableError' || name === 'AbortError') return t(`err_${what}_busy`);
    return t('err_generic', { detail: (err && err.message) || String(err) });
  }
  async function openDevice (what) {
    const { media, pref, constraints } = DEVICES[what];
    const ask = async (deviceId) => {
      const stream = await navigator.mediaDevices.getUserMedia({
        [media]: deviceId ? { ...constraints, deviceId: { exact: deviceId } } : constraints,
      });
      return stream.getTracks()[0];
    };
    try {
      return await ask(prefs[pref]);
    } catch (err) {
      if (!prefs[pref] || !['OverconstrainedError', 'NotFoundError'].includes(err.name)) throw err;
      prefs[pref] = ''; savePrefs(); // the saved one was unplugged: take the default
      return ask('');
    }
  }
  function useTrack (what, track) {
    const old = voice[what];
    voice[what] = track;
    if (old && old !== track) old.stop(); // releases the device: the tab's red dot or the camera light goes off
    if (track) {
      track.onended = () => { // unplugged
        if (voice[what] !== track) return;
        toast(t(`${what}_lost`), 'error');
        useTrack(what, null);
      };
    }
    if (what === 'mic') meterMic(track);
    else voice.camStream = track ? new MediaStream([track]) : null;
    for (const peer of peers.values()) applyLocalTracks(peer);
    sendAv();
    renderVoice();
    renderMembers();
    renderCams();
  }
  async function setDevice (what, on) {
    if (voice.busy[what] || on === !!voice[what]) return;
    if (!on) { useTrack(what, null); return; }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      toast(t(`err_${what}_insecure`), 'error'); return;
    }
    voice.busy[what] = true; renderVoice();
    try {
      useTrack(what, await openDevice(what));
      if (what === 'mic' && !prefs.micHintShown) { prefs.micHintShown = true; savePrefs(); toast(t('mic_headphones'), 'info', 8000); }
    } catch (err) {
      toast(deviceErrorText(what, err), 'error');
    } finally {
      voice.busy[what] = false; renderVoice();
    }
  }
  const toggleMic = () => setDevice('mic', !voice.mic);
  const toggleCam = () => setDevice('cam', !voice.cam);
  el.micBtn.addEventListener('click', toggleMic);
  el.camBtn.addEventListener('click', toggleCam);
  // The join screen has the same two buttons, with a preview, as in Meet: whatever is on
  // there is on when you join.
  el.preMicBtn.innerHTML = el.micBtn.innerHTML;
  el.preCamBtn.innerHTML = el.camBtn.innerHTML;
  el.preMicBtn.addEventListener('click', toggleMic);
  el.preCamBtn.addEventListener('click', toggleCam);

  async function switchDevice (what) {
    if (!voice[what] || voice.busy[what]) return;
    voice.busy[what] = true;
    try {
      useTrack(what, await openDevice(what));
    } catch (err) {
      toast(deviceErrorText(what, err), 'error');
    } finally {
      voice.busy[what] = false; renderVoice();
    }
  }
  async function renderDevices (what) {
    const select = what === 'mic' ? el.micDevice : el.camDevice;
    const { kind, pref } = DEVICES[what];
    let inputs = [];
    try { inputs = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === kind); } catch { /* no devices API */ }
    select.replaceChildren();
    const def = document.createElement('option');
    def.value = ''; def.textContent = t('mic_default');
    select.appendChild(def);
    inputs.filter((d) => d.deviceId && d.deviceId !== 'default').forEach((d, i) => {
      const option = document.createElement('option');
      option.value = d.deviceId; option.textContent = d.label || t(`${what}_n`, { n: i + 1 }); // names only after permission
      select.appendChild(option);
    });
    select.value = [...select.options].some((o) => o.value === prefs[pref]) ? prefs[pref] : '';
    el.duckCheck.checked = prefs.duck;
    el.selfCheck.checked = prefs.showSelf;
    el.camsCheck.checked = prefs.showCams;
  }
  for (const [what, btn, menu, select] of [['mic', el.micMenuBtn, el.micMenu, el.micDevice], ['cam', el.camMenuBtn, el.camMenu, el.camDevice]]) {
    btn.addEventListener('click', () => {
      menu.hidden = !menu.hidden;
      if (!menu.hidden) renderDevices(what);
    });
    select.addEventListener('change', () => { prefs[DEVICES[what].pref] = select.value; savePrefs(); switchDevice(what); });
  }
  el.duckCheck.addEventListener('change', () => { prefs.duck = el.duckCheck.checked; savePrefs(); });
  el.selfCheck.addEventListener('change', () => { prefs.showSelf = el.selfCheck.checked; savePrefs(); renderCams(); });
  el.camsCheck.addEventListener('change', () => { prefs.showCams = el.camsCheck.checked; savePrefs(); renderCams(); });
  if (navigator.mediaDevices && navigator.mediaDevices.addEventListener) {
    navigator.mediaDevices.addEventListener('devicechange', () => {
      if (!el.micMenu.hidden) renderDevices('mic');
      if (!el.camMenu.hidden) renderDevices('cam');
    });
  }

  function renderVoice () {
    for (const [what, btn] of [['mic', el.micBtn], ['cam', el.camBtn], ['mic', el.preMicBtn], ['cam', el.preCamBtn]]) {
      const on = !!voice[what];
      btn.classList.toggle('off', !on);
      btn.title = t(on ? `${what}_off` : `${what}_on`);
      btn.disabled = voice.busy[what];
    }
    el.preview.classList.toggle('live', !!voice.cam);
    if (el.previewVideo.srcObject !== voice.camStream) el.previewVideo.srcObject = voice.camStream;
    el.previewMeter.hidden = !voice.mic;
  }
  function renderPreviewMeter () {
    if (el.joinOverlay.hidden || !voice.mic) return;
    const bars = Math.min(5, Math.floor(Math.sqrt(myLevel()) * 12)); // about 1 bar at the talking level
    el.previewMeter.querySelectorAll('i').forEach((bar, i) => bar.classList.toggle('on', i < bars));
  }

  // ---- camera tiles over the picture, top right. They show while anyone's camera is on:
  // the picture for those whose camera is on, their coloured ball for the others, mine
  // mirrored at the bottom. Inside the stage, so they stay in fullscreen.
  const tiles = new Map(); // member id -> { node, video, name }
  function makeTile (id, me) {
    const node = document.createElement('div');
    node.className = me ? 'cam me' : 'cam others';
    node.dataset.id = id;
    node.innerHTML = '<video autoplay playsinline muted></video>'
      + '<div class="cam-face"><span class="eye"><i></i></span><span class="eye"><i></i></span></div><span class="cam-name"></span>';
    const tile = { node, video: node.querySelector('video'), name: node.querySelector('.cam-name') };
    tiles.set(id, tile);
    return tile;
  }
  function renderCams () {
    const others = S.joined ? S.members.filter((m) => m.joined && m.id !== S.clientId) : [];
    const me = memberById(S.clientId);
    const anyCam = !!voice.cam || others.some((m) => m.cam);
    const list = prefs.showCams && anyCam ? [...others, ...(prefs.showSelf && me ? [me] : [])] : [];
    const keep = new Set(list.map((m) => m.id));
    for (const [id, tile] of tiles) {
      if (!keep.has(id)) { tile.video.srcObject = null; tile.node.remove(); tiles.delete(id); }
    }
    for (const m of list) {
      const isMe = m.id === S.clientId;
      const tile = tiles.get(m.id) || makeTile(m.id, isMe);
      el.cams.appendChild(tile.node); // also keeps the order of the member list
      tile.node.style.setProperty('--c', m.color || '#ffffff');
      tile.node.classList.toggle('speaking', speaking.has(m.id));
      const camOn = isMe ? !!voice.cam : !!m.cam;
      const peer = peers.get(m.id);
      const stream = camOn ? (isMe ? voice.camStream : peer && peer.videoStream) : null;
      if (tile.video.srcObject !== stream) {
        tile.video.srcObject = stream || null;
        if (stream) tile.video.play().catch(() => {});
      }
      tile.node.classList.toggle('live', !!stream);
      tile.name.textContent = isMe ? t('you') : m.name;
      if (!(isMe ? voice.mic : m.mic)) tile.name.insertAdjacentHTML('beforeend', MIC_OFF_ICON);
    }
    el.camsBox.hidden = !list.length;
    placeCams();
  }

  // The tiles sit in a corner of the picture, top right at first: dragged anywhere, they
  // settle in the nearest corner. On the right they share the side with the drawing toolbar.
  const CORNERS = ['tl', 'tr', 'bl', 'br'];
  function placeCams () {
    const corner = CORNERS.includes(prefs.camCorner) ? prefs.camCorner : 'tr';
    const side = corner[1] === 'l' ? el.sideLeft : el.sideRight;
    if (el.camsBox.parentNode !== side) side.prepend(el.camsBox);
    for (const s of [el.sideLeft, el.sideRight]) {
      const here = !el.camsBox.hidden && s === side;
      s.classList.toggle('top', here && corner[0] === 't');
      s.classList.toggle('bottom', here && corner[0] === 'b');
    }
    el.camsBox.style.order = corner[0] === 't' ? '-1' : '1'; // above or below the toolbar
    el.camsBox.classList.toggle('small', !!prefs.camsSmall);
    el.camsBox.title = t('cams_move');
    el.camsSizeBtn.title = t(prefs.camsSmall ? 'cams_big' : 'cams_small');
  }
  el.camsSizeBtn.addEventListener('click', () => { prefs.camsSmall = !prefs.camsSmall; savePrefs(); placeCams(); });

  let camDrag = null; let dragEndedAt = 0;
  el.camsBox.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || e.target.closest('.cams-size')) return;
    camDrag = { id: e.pointerId, x: e.clientX, y: e.clientY, moved: false };
  });
  window.addEventListener('pointermove', (e) => {
    if (!camDrag || e.pointerId !== camDrag.id) return;
    const dx = e.clientX - camDrag.x; const dy = e.clientY - camDrag.y;
    if (!camDrag.moved) {
      if (Math.hypot(dx, dy) < 6) return; // still a click
      camDrag.moved = true;
      el.camsBox.classList.add('dragging');
    }
    el.camsBox.style.transform = `translate(${dx}px, ${dy}px)`;
  });
  function endCamDrag (e) {
    if (!camDrag || e.pointerId !== camDrag.id) return;
    const { moved } = camDrag;
    camDrag = null;
    if (!moved) return;
    el.camsBox.classList.remove('dragging');
    el.camsBox.style.transform = '';
    const r = el.stage.getBoundingClientRect();
    prefs.camCorner = (e.clientY < r.top + r.height / 2 ? 't' : 'b') + (e.clientX < r.left + r.width / 2 ? 'l' : 'r');
    savePrefs();
    placeCams();
    dragEndedAt = performance.now(); // the click that follows the drop is not a click on a tile
  }
  window.addEventListener('pointerup', endCamDrag);
  window.addEventListener('pointercancel', endCamDrag);

  el.cams.addEventListener('click', (e) => {
    if (performance.now() - dragEndedAt < 300) return;
    const node = e.target.closest('.cam.others');
    if (node) openPeerPop(node.dataset.id, node);
  });

  // ---- who is talking: my own level from the microphone, the others' from the incoming
  // packets (getSynchronizationSources). Remote sound is not fed into WebAudio: Chrome plays
  // a remote WebRTC stream into WebAudio as silence unless a media element plays it as well.
  function meterMic (track) {
    if (voice.source) { voice.source.disconnect(); voice.source = null; voice.analyser = null; }
    const ctx = track && audio();
    if (!ctx) return;
    voice.source = ctx.createMediaStreamSource(new MediaStream([track]));
    voice.analyser = ctx.createAnalyser();
    voice.analyser.fftSize = 1024;
    voice.buf = new Float32Array(voice.analyser.fftSize);
    voice.source.connect(voice.analyser);
  }
  function myLevel () {
    if (!voice.analyser) return 0;
    voice.analyser.getFloatTimeDomainData(voice.buf);
    let sum = 0;
    for (const v of voice.buf) sum += v * v;
    return Math.sqrt(sum / voice.buf.length);
  }
  function peerLevel (peer) {
    const m = memberById(peer.id);
    if (!m || !m.mic || !peer.audioTx) return 0;
    const sources = peer.audioTx.receiver.getSynchronizationSources();
    return sources.length ? (sources[0].audioLevel || 0) : 0;
  }

  function voiceTick () {
    renderPreviewMeter();
    const now = performance.now();
    const levels = new Map();
    if (S.clientId && voice.mic) levels.set(S.clientId, myLevel());
    for (const peer of peers.values()) levels.set(peer.id, peerLevel(peer));
    let othersLoudAt = -Infinity;
    for (const id of new Set([...loud.keys(), ...levels.keys()])) {
      const level = levels.get(id) || 0;
      const st = loud.get(id) || { since: null, last: -Infinity };
      if (level >= SPEAK_LEVEL) {
        st.last = now;
        if (st.since === null) st.since = now;
      } else if (now - st.last > QUIET_AFTER_MS) {
        st.since = null;
      }
      loud.set(id, st);
      const talking = st.since !== null && now - st.since >= SPEAK_AFTER_MS;
      if (talking !== speaking.has(id)) {
        if (talking) speaking.add(id); else speaking.delete(id);
        showSpeaking(id, talking);
      }
      if (id !== S.clientId && st.since !== null && now - st.since >= SPEAK_AFTER_MS) othersLoudAt = Math.max(othersLoudAt, st.last);
    }
    // Lower the film while someone else talks: down in about 0.3 s, back up over about 1 s.
    const target = prefs.duck && now - othersLoudAt < UNDUCK_AFTER_MS ? DUCK_TO : 1;
    const step = target < duck ? (1 - DUCK_TO) / 3 : (1 - DUCK_TO) / 10;
    const next = target < duck ? Math.max(target, duck - step) : Math.min(target, duck + step);
    if (next !== duck) { duck = next; applyFilmVolume(); }
  }
  function showSpeaking (id, on) {
    const ball = id === S.clientId ? mine : balls.get(id);
    if (ball) ball.node.classList.toggle('speaking', on);
    const chip = el.members.querySelector(`[data-id="${id}"]`);
    if (chip) chip.classList.toggle('speaking', on);
    const tile = tiles.get(id);
    if (tile) tile.node.classList.toggle('speaking', on);
  }

  // ---- per-person volume: click someone's name at the top, or their camera tile
  function applyPeerVolume (peer) {
    const m = memberById(peer.id);
    const vol = m && prefs.peerVolume[m.name];
    peer.audioEl.volume = typeof vol === 'number' ? Math.min(1, Math.max(0, vol)) : 1;
  }
  let popFor = null;
  function openPeerPop (id, anchor) {
    const m = memberById(id);
    if (!m || (popFor === m.id && !el.peerPop.hidden)) { el.peerPop.hidden = true; return; }
    popFor = m.id;
    // In fullscreen only the stage is drawn, so the box has to live inside it then.
    const parent = document.fullscreenElement === el.stage ? el.stage : document.body;
    if (el.peerPop.parentNode !== parent) parent.appendChild(el.peerPop);
    el.peerPopName.textContent = t('peer_volume', { name: m.name });
    const vol = prefs.peerVolume[m.name];
    el.peerVol.value = typeof vol === 'number' ? vol : 1;
    const r = anchor.getBoundingClientRect();
    const beside = anchor.classList.contains('cam'); // a tile: to its left; a name: below it
    el.peerPop.style.top = `${beside ? r.top : r.bottom + 6}px`;
    el.peerPop.style.left = `${Math.max(8, Math.min(window.innerWidth - 216, beside ? r.left - 210 : r.right - 200))}px`;
    el.peerPop.hidden = false;
  }
  el.members.addEventListener('click', (e) => {
    const chip = e.target.closest('.member.others');
    if (chip) openPeerPop(chip.dataset.id, chip);
  });
  el.peerVol.addEventListener('input', () => {
    const m = memberById(popFor);
    if (!m) return;
    prefs.peerVolume[m.name] = Number(el.peerVol.value); savePrefs();
    const peer = peers.get(m.id);
    if (peer) applyPeerVolume(peer);
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
      const left = result.added.map((tr) => tr.remaining).filter(Number.isFinite);
      if (left.length) toast(t('search_remaining', { n: Math.min(...left) }));
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

  async function openPath (path) {
    try {
      await api('/api/media/open', { json: { path } });
    } catch (err) {
      toast(errorText(err), 'error');
    }
  }
  el.pathForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const path = el.pathInput.value.trim().replace(/^"(.*)"$/, '$1');
    if (!path) { toast(t('path_needed')); el.pathInput.focus(); return; }
    openPath(path);
  });
  // The system's file dialog opens on the host's screen (the server runs there); the browser's
  // own picker would not tell us the file's full path.
  const pickFileBtn = $('#pickFileBtn');
  pickFileBtn.addEventListener('click', async () => {
    pickFileBtn.disabled = true;
    try {
      const { path } = await api('/api/media/pick', { json: { title: t('pick_file_title') } });
      if (path) { el.pathInput.value = path; openPath(path); }
    } catch (err) {
      toast(errorText(err), 'error');
    } finally {
      pickFileBtn.disabled = false;
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

  // ---------------------------------------------------------------- browse: add-on catalogs
  // Catalogs, details and sources come from Stremio add-ons, through the server. A source is
  // opened by the `ref` the server gave it, for everyone in the room, like a torrent.
  const B = {
    addons: [], canEdit: false, catalogs: [], key: '', query: '', skip: 0, items: [], seq: 0, streamSeq: 0,
    started: false, title: null, videos: [], season: null, episode: null,
  };
  const typeName = (type) => t(type === 'series' ? 'type_series' : 'type_movie');
  const catKey = (c) => `${c.addon}|${c.type}|${c.id}`;
  const query = (params) => new URLSearchParams(params).toString();
  const metaLine = (m) => [m.year, typeName(m.type), m.rating ? `★ ${m.rating}` : '', m.runtime]
    .filter(Boolean).join(' · ');

  async function loadAddons () {
    try {
      const data = await api('/api/addons');
      B.addons = data.addons || [];
      B.canEdit = !!data.canEdit;
      B.catalogs = B.addons.flatMap((a) => (a.catalogs || []).map((c) => ({ ...c, addonName: a.name })));
    } catch (err) {
      toast(errorText(err), 'error');
      return;
    }
    renderCatalogs();
    renderAddons();
    if (!B.started) { B.started = true; loadCatalog(true); }
  }

  function renderCatalogs () {
    const wanted = B.key || prefs.browseCatalog;
    el.catalogSel.replaceChildren();
    for (const c of B.catalogs.filter((x) => !x.searchOnly)) {
      const option = document.createElement('option');
      option.value = catKey(c);
      option.textContent = `${c.addonName} · ${c.name} (${typeName(c.type)})`;
      el.catalogSel.appendChild(option);
    }
    if ([...el.catalogSel.options].some((o) => o.value === wanted)) el.catalogSel.value = wanted;
    B.key = el.catalogSel.value;
  }

  function showList () { el.titleView.hidden = true; el.browseList.hidden = false; B.title = null; }

  async function loadCatalog (reset) {
    if (reset) { B.skip = 0; B.items = []; el.browseGrid.replaceChildren(); }
    showList();
    const seq = ++B.seq;
    el.browseStatus.textContent = t('browse_loading');
    el.browseMore.hidden = true;
    const metas = [];
    try {
      if (B.query) { // every catalog that can search, films and series together
        const results = await Promise.allSettled(B.catalogs.filter((c) => c.search).map((c) =>
          api(`/api/addons/catalog?${query({ addon: c.addon, type: c.type, id: c.id, search: B.query })}`)));
        for (const r of results) if (r.status === 'fulfilled') metas.push(...r.value.metas);
      } else {
        const c = B.catalogs.find((x) => catKey(x) === B.key);
        if (c) metas.push(...(await api(`/api/addons/catalog?${query({ addon: c.addon, type: c.type, id: c.id, skip: B.skip })}`)).metas);
      }
    } catch (err) {
      if (seq === B.seq) { el.browseStatus.textContent = ''; toast(errorText(err), 'error'); }
      return;
    }
    if (seq !== B.seq) return; // a newer search or catalog took over
    const seen = new Set(B.items.map((m) => m.id));
    const fresh = metas.filter((m) => !seen.has(m.id) && seen.add(m.id));
    if (B.query) { // films and series come from separate catalogs: the closest names first
      const q = B.query.toLowerCase();
      const rank = (m) => { const n = (m.name || '').toLowerCase(); return n === q ? 0 : n.startsWith(q) ? 1 : 2; };
      fresh.sort((a, b) => rank(a) - rank(b));
    }
    B.items.push(...fresh);
    B.skip += metas.length;
    for (const m of fresh) el.browseGrid.appendChild(posterCard(m));
    el.browseStatus.textContent = !B.items.length ? t('browse_empty') : (B.query ? t('browse_results', { q: B.query }) : '');
    el.browseMore.hidden = !!B.query || !metas.length;
  }

  function posterCard (m) {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'poster';
    const box = document.createElement('span');
    box.className = 'img';
    if (m.poster) {
      const img = document.createElement('img');
      img.loading = 'lazy'; img.alt = ''; img.referrerPolicy = 'no-referrer'; img.src = m.poster;
      box.appendChild(img);
    } else {
      box.textContent = m.name;
    }
    const name = document.createElement('span'); name.className = 'name'; name.textContent = m.name;
    const sub = document.createElement('span'); sub.className = 'sub'; sub.textContent = metaLine(m);
    card.append(box, name, sub);
    card.addEventListener('click', () => openTitle(m));
    return card;
  }

  async function openTitle (m) {
    B.title = { ...m }; B.videos = []; B.season = null; B.episode = null;
    el.browseList.hidden = true;
    el.titleView.hidden = false;
    el.titlePoster.src = m.poster || '';
    el.titleName.textContent = m.name;
    el.titleMeta.textContent = metaLine(m);
    el.titleDesc.textContent = '';
    el.episodes.hidden = true;
    streamMessage(t('browse_loading'));
    el.browseList.parentNode.scrollIntoView({ block: 'nearest' });
    let meta = null;
    try {
      meta = (await api(`/api/addons/meta?${query({ type: m.type, id: m.id })}`)).meta;
    } catch { /* details are a nicety: sources still work */ }
    if (!B.title || B.title.id !== m.id) return;
    if (meta) {
      Object.assign(B.title, meta, { name: meta.name || m.name, poster: meta.poster || m.poster });
      el.titlePoster.src = B.title.poster || '';
      el.titleMeta.textContent = [metaLine(B.title), (meta.genres || []).join(', ')].filter(Boolean).join(' · ');
      el.titleDesc.textContent = meta.description || '';
    }
    if (m.type === 'series' && meta && meta.videos && meta.videos.length) {
      B.videos = meta.videos;
      renderSeasons();
      streamMessage(t('streams_pick_episode'));
    } else {
      loadStreams(m.type, m.id, B.title.name);
    }
  }

  function renderSeasons () {
    const seasons = [...new Set(B.videos.map((v) => v.season ?? 0))].sort((a, b) => (a || 9999) - (b || 9999));
    el.seasonSel.replaceChildren();
    for (const s of seasons) {
      const option = document.createElement('option');
      option.value = String(s);
      option.textContent = s ? t('season_n', { n: s }) : t('season_specials');
      el.seasonSel.appendChild(option);
    }
    if (B.season === null) B.season = seasons[0];
    el.seasonSel.value = String(B.season);
    el.episodes.hidden = false;
    renderEpisodes();
  }
  el.seasonSel.addEventListener('change', () => { B.season = Number(el.seasonSel.value); renderEpisodes(); });

  function renderEpisodes () {
    el.episodeList.replaceChildren();
    const list = B.videos.filter((v) => (v.season ?? 0) === B.season).sort((a, b) => (a.episode ?? 0) - (b.episode ?? 0));
    for (const v of list) {
      const li = document.createElement('li');
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.classList.toggle('sel', v.id === B.episode);
      const num = document.createElement('span'); num.className = 'num'; num.textContent = v.episode ?? '';
      const name = document.createElement('span'); name.textContent = v.name || '';
      btn.append(num, name);
      btn.addEventListener('click', () => {
        B.episode = v.id;
        renderEpisodes();
        loadStreams('series', v.id, B.title.name);
      });
      li.appendChild(btn);
      el.episodeList.appendChild(li);
    }
  }

  function streamMessage (text) {
    const li = document.createElement('li');
    li.className = 'msg';
    li.textContent = text;
    el.streamList.replaceChildren(li);
  }

  async function loadStreams (type, id, name) {
    const seq = ++B.streamSeq;
    streamMessage(t('browse_loading'));
    let streams;
    try {
      streams = (await api(`/api/addons/streams?${query({ type, id, name })}`)).streams;
    } catch (err) {
      if (seq === B.streamSeq) streamMessage(errorText(err));
      return;
    }
    if (seq !== B.streamSeq) return;
    if (!streams.length) { streamMessage(t('streams_none')); return; }
    el.streamList.replaceChildren();
    for (const s of streams) {
      const li = document.createElement('li');
      const what = document.createElement('span'); what.className = 'what';
      const head = document.createElement('b'); head.textContent = [s.addon, s.name].filter(Boolean).join(' · ');
      const detail = document.createElement('span'); detail.textContent = s.detail;
      what.append(head, detail);
      const kind = document.createElement('span'); kind.className = 'kind';
      kind.textContent = t(s.kind === 'torrent' ? 'stream_torrent' : 'stream_url');
      const open = document.createElement('button'); open.type = 'button'; open.className = 'primary';
      open.textContent = t('stream_open');
      open.addEventListener('click', async () => {
        open.disabled = true;
        try {
          await api('/api/media/open', { json: { stream: s.ref } });
          toast(t('stream_opening', { name }));
          el.stage.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } catch (err) {
          toast(errorText(err), 'error');
        } finally {
          open.disabled = false;
        }
      });
      li.append(what, kind, open);
      el.streamList.appendChild(li);
    }
  }

  el.titleBack.addEventListener('click', () => { showList(); B.streamSeq++; });
  el.catalogSel.addEventListener('change', () => {
    B.key = el.catalogSel.value;
    prefs.browseCatalog = B.key; savePrefs();
    B.query = ''; el.browseQuery.value = '';
    loadCatalog(true);
  });
  el.browseSearch.addEventListener('submit', (e) => {
    e.preventDefault();
    B.query = el.browseQuery.value.trim().slice(0, 100);
    loadCatalog(true);
  });
  el.browseMore.addEventListener('click', () => loadCatalog(false));

  // ---- the add-on list: everyone sees it, only the host changes it
  function renderAddons () {
    el.addonList.replaceChildren();
    for (const a of B.addons) {
      const li = document.createElement('li');
      const name = document.createElement('span'); name.className = 'name'; name.textContent = a.name;
      const what = document.createElement('span'); what.className = 'what';
      what.textContent = a.description || (a.resources || []).join(', ');
      what.title = a.url;
      li.append(name, what);
      if (a.builtin) {
        const badge = document.createElement('span'); badge.className = 'badge'; badge.textContent = t('addons_builtin');
        li.appendChild(badge);
      }
      if (a.error) {
        const bad = document.createElement('span'); bad.className = 'bad'; bad.textContent = t('addons_unreachable');
        bad.title = a.error;
        li.appendChild(bad);
      }
      if (B.canEdit && !a.builtin) {
        const del = document.createElement('button'); del.type = 'button'; del.className = 'ghost';
        del.textContent = t('addons_remove');
        del.addEventListener('click', async () => {
          if (!confirm(t('addons_confirm_remove', { name: a.name }))) return;
          try { await api(`/api/addons?${query({ url: a.url })}`, { method: 'DELETE' }); } catch (err) { toast(errorText(err), 'error'); }
          await loadAddons();
          loadCatalog(true);
        });
        li.appendChild(del);
      }
      el.addonList.appendChild(li);
    }
    el.addonForm.hidden = !B.canEdit;
    el.addonsNote.hidden = !B.canEdit;
    el.addonsHostOnly.hidden = B.canEdit;
  }
  el.addonsBtn.addEventListener('click', () => {
    el.addonsPanel.hidden = !el.addonsPanel.hidden;
    if (!el.addonsPanel.hidden) loadAddons();
  });
  el.addonForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const url = el.addonUrl.value.trim();
    if (!url) return;
    const btn = el.addonForm.querySelector('button');
    btn.disabled = true;
    try {
      const added = await api('/api/addons', { json: { url } });
      toast(t('addons_added', { name: added.name }));
      el.addonUrl.value = '';
      await loadAddons();
    } catch (err) {
      toast(errorText(err), 'error');
    } finally {
      btn.disabled = false;
    }
  });

  // ---- subtitles the add-ons offer for the open film (found by its id and file hash)
  el.addonSubsBtn.addEventListener('click', async () => {
    el.addonSubsBtn.disabled = true;
    el.addonSubsList.replaceChildren();
    try {
      const { subtitles } = await api('/api/addons/subtitles');
      if (!subtitles.length) {
        const li = document.createElement('li'); li.textContent = t('subs_addons_none');
        el.addonSubsList.appendChild(li);
      }
      for (const sub of subtitles) el.addonSubsList.appendChild(addonSubItem(sub));
    } catch (err) {
      toast(errorText(err), 'error');
    } finally {
      el.addonSubsBtn.disabled = false;
    }
  });
  function addonSubItem (sub) {
    const li = document.createElement('li');
    const lang = document.createElement('span'); lang.className = 'lang'; lang.textContent = sub.lang.toUpperCase();
    const label = document.createElement('span'); label.className = 'label';
    label.textContent = `${langName(sub.lang)} · ${sub.addon}`;
    li.append(lang, label);
    const add = document.createElement('button'); add.type = 'button'; add.className = 'ghost';
    add.textContent = sub.added ? t('subs_addons_added') : t('addons_add');
    add.disabled = !!sub.added;
    add.addEventListener('click', async () => {
      add.disabled = true;
      try {
        const track = await api('/api/addons/subtitles', { json: { ref: sub.ref } });
        toast(t('uploaded', { label: track.label }));
        add.textContent = t('subs_addons_added');
        if (!S.primary) selectTrack('primary', track.id);
      } catch (err) {
        add.disabled = false;
        toast(errorText(err), 'error');
      }
    });
    li.appendChild(add);
    return li;
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
    sendHello();
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
    renderToolbar(); renderVoice(); renderCams(); renderCatalogs(); renderAddons();
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

  const MIC_OFF_ICON = '<svg class="mic-off" viewBox="0 0 24 24"><path d="M19 11h-1.7c0 .7-.2 1.4-.4 2l1.2 1.3c.6-1 .9-2.1.9-3.3zm-4 .2V5a3 3 0 0 0-6 0v.2zM4.3 3 3 4.3l6 6v.7a3 3 0 0 0 3.7 2.9l1.6 1.7c-.7.3-1.5.5-2.3.5-2.8 0-5.3-2.1-5.3-5.1H5c0 3.4 2.7 6.2 6 6.7V21h2v-3.3c.9-.1 1.8-.4 2.5-.9l4.2 4.2 1.3-1.3z"/></svg>';
  function renderMembers () {
    el.members.replaceChildren();
    for (const m of S.members) {
      const chip = document.createElement('span');
      const me = m.id === S.clientId;
      chip.className = 'member';
      chip.dataset.id = m.id;
      if (m.color) chip.style.setProperty('--c', m.color);
      chip.classList.toggle('me', me);
      chip.classList.toggle('others', !me && !!m.joined);
      chip.classList.toggle('speaking', speaking.has(m.id));
      const titles = [];
      if (m.buffering) { chip.classList.add('buffering'); titles.push(t('buffering')); }
      chip.textContent = me ? `${m.name} (${t('you')})` : m.name;
      // My own state is known here at once; the server's copy comes back a moment later.
      const micOn = me ? !!voice.mic : !!m.mic;
      if (m.joined && !micOn) {
        chip.insertAdjacentHTML('beforeend', MIC_OFF_ICON);
        titles.push(t('mic_muted'));
      }
      chip.title = titles.join(' · ');
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
    el.addonSubs.hidden = !(S.media && S.media.content);
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
    voice: {
      mic: !!voice.mic, cam: !!voice.cam, camLive: !!(voice.cam && voice.cam.readyState === 'live'),
      duck, filmVolume: video.volume, speaking: [...speaking],
      peers: [...peers.values()].map((p) => {
        const enc = p.videoTx && (p.videoTx.sender.getParameters().encodings || [])[0];
        return {
          id: p.id, polite: p.polite, state: p.pc.connectionState, level: peerLevel(p),
          sending: !!(p.audioTx && p.audioTx.sender.track), sendingVideo: !!(p.videoTx && p.videoTx.sender.track),
          videoMaxBitrate: enc ? enc.maxBitrate : null, transceivers: p.pc.getTransceivers().length,
        };
      }),
    },
  });

  // Drops the room connection, as a network hiccup would; the page reconnects by itself.
  window.cowatchDebug.reconnect = () => { if (S.ws) S.ws.close(); };
  // Rebuilds every voice and camera connection, as peerWatch does for one that stays down.
  window.cowatchDebug.resetPeers = () => { for (const id of [...peers.keys()]) resetPeer(id); };

  // ---------------------------------------------------------------- start
  applyI18n();
  connect();
  pollStatus();
  loadAddons();
  setInterval(pollStatus, 3000);
  setInterval(syncTick, 250);
  setInterval(voiceTick, 100);
  setInterval(peerWatch, 1000);
  requestAnimationFrame(frame);
})();
