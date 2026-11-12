'use strict';
/* global Hls, I18N, UI_LANGS, detectUiLang, qrcode */
// Co-Watch client. The server owns playback state; this page only sends requests
// (play/pause/seek/buffering) and keeps its own <video> aligned with the broadcast state.
// Film time = video.currentTime + media.streamStart. Subtitles are drawn locally.
(() => {
  const $ = (sel) => document.querySelector(sel);
  const el = {
    video: $('#video'), stage: $('#stage'), subPrimary: $('#subPrimary'), subSecondary: $('#subSecondary'),
    empty: $('#empty'), centerMsg: $('#centerMsg'), controls: $('#controls'), seekBar: $('#seekBar'),
    produced: $('#produced'), playBtn: $('#playBtn'), backBtn: $('#backBtn'), fwdBtn: $('#fwdBtn'), tapSeek: $('#tapSeek'),
    timeLabel: $('#timeLabel'), muteBtn: $('#muteBtn'), volume: $('#volume'), fsBtn: $('#fsBtn'),
    filmTitle: $('#filmTitle'), members: $('#members'), conn: $('#conn'), uiLang: $('#uiLang'),
    magnetForm: $('#magnetForm'), magnetInput: $('#magnetInput'), fileList: $('#fileList'),
    pathForm: $('#pathForm'), pathInput: $('#pathInput'), hostHint: $('#hostHint'),
    libraryBox: $('#libraryBox'), libraryHint: $('#libraryHint'), libraryFilter: $('#libraryFilter'),
    libraryList: $('#libraryList'), peerGrant: $('#peerGrant'), peerGrantHint: $('#peerGrantHint'), peerKick: $('#peerKick'), joinNotice: $('#joinNotice'),
    screenVideo: $('#screenVideo'), screenTag: $('#screenTag'), shareAsks: $('#shareAsks'), screenBtn: $('#screenBtn'),
    screenGroup: $('#screenGroup'), screenMenuBtn: $('#screenMenuBtn'), screenMenu: $('#screenMenu'), screenQuality: $('#screenQuality'),
    screenQualityHint: $('#screenQualityHint'), screenStats: $('#screenStats'),
    peerStopShare: $('#peerStopShare'), mediaLockHint: $('#mediaLockHint'),
    mediaInfo: $('#mediaInfo'), torrentInfo: $('#torrentInfo'), closeMedia: $('#closeMedia'),
    primarySel: $('#primarySel'), secondarySel: $('#secondarySel'), offsetField: $('#offsetField'), offsetRows: $('#offsetRows'),
    sizeRange: $('#sizeRange'), bottomRange: $('#bottomRange'), searchForm: $('#searchForm'),
    searchLangs: $('#searchLangs'), osOff: $('#osOff'), uploadForm: $('#uploadForm'), subFile: $('#subFile'),
    subLang: $('#subLang'), trackList: $('#trackList'), joinOverlay: $('#joinOverlay'), joinForm: $('#joinForm'),
    nameInput: $('#nameInput'), joinLang: $('#joinLang'), toasts: $('#toasts'),
    drawCanvas: $('#drawCanvas'), cursors: $('#cursors'), toolbar: $('#toolbar'), penBtn: $('#penBtn'),
    colorBtn: $('#colorBtn'), palette: $('#palette'), clearBtn: $('#clearBtn'), sfxBtn: $('#sfxBtn'),
    eraserBtn: $('#eraserBtn'), eraserModes: $('#eraserModes'), camBig: $('#camBig'), camBigVideo: $('#camBig video'), camBigName: $('#camBigName'),
    micBtn: $('#micBtn'), micMenuBtn: $('#micMenuBtn'), micMenu: $('#micMenu'), micDevice: $('#micDevice'),
    duckCheck: $('#duckCheck'), peerPop: $('#peerPop'), peerNet: $('#peerNet'),
    speedTestBtn: $('#speedTestBtn'), speedTestOut: $('#speedTestOut'), speedTestBox: $('#speedTestBox'), peerPopName: $('#peerPopName'), peerVol: $('#peerVol'),
    voices: $('#voices'), camBtn: $('#camBtn'), camMenuBtn: $('#camMenuBtn'), camMenu: $('#camMenu'),
    camDevice: $('#camDevice'), selfCheck: $('#selfCheck'), camsCheck: $('#camsCheck'), cams: $('#cams'),
    preview: $('#preview'), previewVideo: $('#previewVideo'), previewMeter: $('#previewMeter'),
    previewFace: $('#previewFace'), joinColors: $('#joinColors'), joinAnimals: $('#joinAnimals'),
    preMicBtn: $('#preMicBtn'), preCamBtn: $('#preCamBtn'),
    camsBox: $('#camsBox'), camsSizeBtn: $('#camsSizeBtn'), sideLeft: $('#sideLeft'), sideRight: $('#sideRight'),
    catalogSel: $('#catalogSel'), browseSearch: $('#browseSearch'), browseQuery: $('#browseQuery'),
    addonsBtn: $('#addonsBtn'), addonsPanel: $('#addonsPanel'), addonList: $('#addonList'), addonForm: $('#addonForm'),
    addonUrl: $('#addonUrl'), addonsStremio: $('#addonsStremio'), addonsNote: $('#addonsNote'),
    addonsHostOnly: $('#addonsHostOnly'),
    browseList: $('#browseList'), browseGrid: $('#browseGrid'), browseStatus: $('#browseStatus'), browseMore: $('#browseMore'),
    titleView: $('#titleView'), titleBack: $('#titleBack'), titlePoster: $('#titlePoster'), titleName: $('#titleName'),
    titleMeta: $('#titleMeta'), titleDesc: $('#titleDesc'), episodes: $('#episodes'), seasonSel: $('#seasonSel'),
    episodeList: $('#episodeList'), streamList: $('#streamList'),
    streamTools: $('#streamTools'), streamFilter: $('#streamFilter'), streamAddon: $('#streamAddon'),
    streamQuality: $('#streamQuality'), streamCount: $('#streamCount'), streamMore: $('#streamMore'),
    addonSubs: $('#addonSubs'), addonSubsBtn: $('#addonSubsBtn'), addonSubsList: $('#addonSubsList'),
    addonSubsLang: $('#addonSubsLang'), addonSubsMore: $('#addonSubsMore'),
    shareCard: $('#shareCard'), settingsBtn: $('#settingsBtn'), tsLight: $('#tsLight'), tsText: $('#tsText'),
    tsLink: $('#tsLink'), tsOpen: $('#tsOpen'), shareRetry: $('#shareRetry'), tsHint: $('#tsHint'),
    friendRow: $('#friendRow'), friendLink: $('#friendLink'), copyLink: $('#copyLink'), shareHint: $('#shareHint'),
    qrCanvas: $('#qrCanvas'), settingsOverlay: $('#settingsOverlay'), settingsForm: $('#settingsForm'),
    settingsClose: $('#settingsClose'), settingsCancel: $('#settingsCancel'), settingsSave: $('#settingsSave'),
    settingsWarn: $('#settingsWarn'), qualityMbps: $('#qualityMbps'), dirList: $('#dirList'), dirInput: $('#dirInput'),
    dirPick: $('#dirPick'), dirAdd: $('#dirAdd'), osApiKey: $('#osApiKey'), osUsername: $('#osUsername'),
    osPassword: $('#osPassword'), port: $('#port'), torrentUploadLimit: $('#torrentUploadLimit'),
    iceServers: $('#iceServers'), newKeyBtn: $('#newKeyBtn'),
    storageInfo: $('#storageInfo'), storageClean: $('#storageClean'), audioField: $('#audioField'), audioSel: $('#audioSel'),
    stageWrap: $('#stageWrap'), miniBack: $('#miniBack'), miniClose: $('#miniClose'), pipBtn: $('#pipBtn'),
    awayMsg: $('#awayMsg'), pipReturn: $('#pipReturn'),
    chatBtn: $('#chatBtn'), chatBadge: $('#chatBadge'), chatBox: $('#chatBox'), chatClose: $('#chatClose'),
    chatLog: $('#chatLog'), chatForm: $('#chatForm'), chatInput: $('#chatInput'), chatPeek: $('#chatPeek'),
    watch: $('#watch'), chatDock: $('#chatDock'),
    aiBox: $('#aiBox'), aiForm: $('#aiForm'), aiLang: $('#aiLang'), aiSource: $('#aiSource'), aiGo: $('#aiGo'),
    aiHint: $('#aiHint'), aiSettings: $('#aiSettings'), aiProvider: $('#aiProvider'), aiProtocol: $('#aiProtocol'),
    aiBaseUrl: $('#aiBaseUrl'), aiApiKey: $('#aiApiKey'), aiModel: $('#aiModel'), aiModels: $('#aiModels'),
    aiModelsBtn: $('#aiModelsBtn'), aiTestBtn: $('#aiTestBtn'), aiTestOut: $('#aiTestOut'),
    aiNote: $('#aiNote'), aiKeyLabel: $('#aiKeyLabel'), aiModelLabel: $('#aiModelLabel'),
    loader: $('#loader'), loaderText: $('#loaderText'), loaderBar: $('#loaderBar'), loaderStats: $('#loaderStats'),
    loaderCancel: $('#loaderCancel'), torrentWait: $('#torrentWait'),
  };
  const video = el.video;
  // Screen sharing (see "screen sharing" below): who shares, who waits for an answer, and my
  // own capture, opened on the click and sent only once the screen is mine.
  const screen = { owner: null, pending: [], stream: null, asking: false };

  // ---------------------------------------------------------------- preferences
  const PREFS_KEY = 'cowatch.prefs.v1';
  const DEFAULT_PREFS = {
    name: '', uiLang: detectUiLang(), primaryLang: '', secondaryLang: '',
    fontSize: 100, bottom: 8, searchLangs: '', volume: 1, muted: false, color: '', sfx: true,
    micDevice: '', duck: true, peerVolume: {}, micHintShown: false, camDevice: '', showSelf: true, showCams: true,
    camCorner: 'tr', camsSmall: false, browseCatalog: '', chatDock: true, eraseWhole: false, screenQuality: 'auto',
    align: {}, // each subtitle's own timing, by its id: {offset (ms), scale, used}
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
    bufferingSent: false, waitTimer: null, dragging: false, isHost: false, canLibrary: false, libraryConfigured: false, canChangeMedia: true, cohost: null, autoplayBlocked: false,
    torrent: null, downloadThrottled: false,
    palette: ['#ff6b6b', '#4dabf7', '#51cf66', '#fcc419', '#cc5de8', '#ff922b', '#22b8cf', '#f06595'],
    penMode: false, eraser: false, iceServers: [],
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
    while (el.toasts.children.length > 3) el.toasts.firstChild.remove(); // a phone has no room for more
    setTimeout(() => node.remove(), level === 'error' ? ms * 2 : ms);
    return node;
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
  // A server that has gone quiet: the oldest ping with nothing at all heard since. Every ping
  // gets a pong, so after `SILENT_MS` of silence the connection is dropped and made again (the
  // link hiccuped, or the server gave up on this page). Measured from the ping, not from the
  // last message, so that a background tab whose timers run once a minute is not dropped.
  const SILENT_MS = 25000;
  let pingTimer = null;
  let unanswered = null; // performance.now() of the first ping since the last message
  function startPings () {
    clearInterval(pingTimer);
    unanswered = null;
    let count = 0;
    const ping = () => {
      const now = performance.now();
      if (unanswered !== null && now - unanswered > SILENT_MS) { dropSocket(S.ws); return; }
      send({ type: 'ping', t0: now });
      if (unanswered === null) unanswered = now;
      count += 1;
      if (count === 6) { clearInterval(pingTimer); pingTimer = setInterval(ping, 10000); }
    };
    ping();
    pingTimer = setInterval(ping, 500);
  }
  // No waiting for the closing handshake: on a dead link it may never come.
  function dropSocket (ws) {
    if (!ws || S.ws !== ws) return;
    ws.onmessage = null;
    ws.onclose = null;
    try { ws.close(4000); } catch { /* closing already */ }
    lostSocket(ws);
  }
  function lostSocket (ws) {
    S.connected = false;
    clearInterval(pingTimer);
    if (S.ws === ws && !S.kicked) {
      setConn('disconnected');
      clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(connect, 2000);
    }
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
      unanswered = null; // the server is there
      let msg;
      try { msg = JSON.parse(event.data); } catch { return; }
      onMessage(msg);
    };
    // 4003: the host removed me (main.KICKED_CLOSE). Any other code, 4000 too (main.DEAD_CLOSE:
    // the server could not reach me and let me go), means trying again.
    ws.onclose = (event) => {
      if (event.code === 4003) onKicked();
      lostSocket(ws);
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
        lumaWatch.welcomes += 1; lumaWatch.stateAt = performance.now();
        S.clientId = msg.clientId;
        S.iceServers = Array.isArray(msg.iceServers) ? msg.iceServers : [];
        S.clock.samples = [];
        S.clock.offset = msg.serverTime - performance.now();
        S.osEnabled = !!msg.osEnabled;
        S.opening = !!msg.opening;
        followOpening();
        S.room = msg.state;
        S.bufferingSent = false; // the new id waits for nothing yet
        S.members = msg.members || [];
        if (Array.isArray(msg.palette) && msg.palette.length) S.palette = msg.palette;
        S.progress = msg.progress;
        onMembers();
        if (screen.stream) stopMyScreen(false); // a new connection is a new id: the screen was let go
        onScreen(msg.screen || {});
        applyMedia(msg.media);
        applyTracks(msg.tracks || []);
        setChatHistory(msg.chat);
        renderAll();
        if (!el.joinOverlay.hidden) renderLook();
        break;
      case 'pong': onPong(msg); break;
      case 'kicked': onKicked(); break;
      case 'repair': onRepair(); break;
      case 'state': {
        lumaWatch.stateAt = performance.now();
        const wasRunning = roomRunning();
        S.room = msg;
        // What the server holds is the truth: after 20 s it lets the room go on without me (and
        // takes no stall from me for a while), and my old "waiting" must not decide the next report.
        const waitingForMe = (msg.waiting || []).includes(S.clientId);
        if (waitingForMe) clearTimeout(S.waitTimer);
        S.bufferingSent = waitingForMe;
        if (wasRunning !== roomRunning()) retimeStrokes();
        renderControls(); renderCenter(); phoneSync();
        break;
      }
      case 'members':
        S.members = msg.members || []; for (const m of S.members) if (m.net) netSpeed.set(m.id, m.net);
        onMembers(); renderMembers(); renderCenter(); renderScreen();
        if (!el.joinOverlay.hidden) renderLook();
        break;
      case 'screen': onScreen(msg); break;
      case 'media': applyMedia(msg.media); keepRetune(); break;
      case 'retune': onRetune(msg); break;
      case 'resumed': onResumed(msg); break;
      case 'progress': S.progress = msg; renderMediaInfo(); break;
      case 'subtitles': applyTracks(msg.tracks || []); break;
      case 'status': onStatus(msg); break;
      case 'cursor': onCursor(msg); break;
      case 'poke': if (msg.from !== S.clientId) pokeEffect(msg.from, [msg.x, msg.y]); break;
      case 'draw': onDraw(msg); break;
      case 'draw_clear': clearStrokes(msg.from); break;
      case 'draw_erase':
        if (Array.isArray(msg.strokes)) eraseStrokes(msg.strokes.map((s) => `${s[0]}:${s[1]}`));
        break;
      case 'rtc': onRtc(msg); break;
      case 'chat': onChat(msg); break;
      case 'netstat': onNetstat(msg); break;
      case 'net_hint': onNetHint(msg); break;
      default: break;
    }
  }

  function onStatus (msg) {
    const params = { ...(msg.params || {}) };
    if (params.at !== undefined) params.at = fmtTime(params.at);
    if (msg.key === 'restarting') return; // the stage shows its own loader
    if (['translating', 'translated', 'translate_failed'].includes(msg.key)) { onAiStatus(msg, params); return; }
    // Opening a film takes a few steps: the loader on the stage follows them, for everyone.
    if (OPEN_ORDER.includes(msg.key)) {
      S.opening = true;
      Object.assign(OPEN, { step: msg.key, params });
      followOpening();
      renderCenter();
      return;
    }
    if (['stream_ready', 'open_failed', 'open_cancelled'].includes(msg.key)) {
      S.opening = false;
      Object.assign(OPEN, { step: null, params: {}, torrent: null });
      followOpening();
      renderCenter();
    }
    toast(t(`status_${msg.key}`, params), msg.level === 'error' ? 'error' : 'info', msg.key === 'stream_ready' ? 3000 : 4500);
  }
  // ---- the loader on the stage, while a film opens or the stream restarts after a seek
  const OPEN_ORDER = ['opening', 'torrent_adding', 'reading_hash', 'probing', 'stream_starting'];
  const OPEN = { step: null, params: {}, torrent: null, poll: null };
  // Torrent peers and speed come with the status; while a film opens, every second.
  function followOpening () {
    if (S.opening && !OPEN.poll) OPEN.poll = setInterval(pollStatus, 1000);
    if (!S.opening && OPEN.poll) { clearInterval(OPEN.poll); OPEN.poll = null; }
  }
  function renderLoader () {
    const opening = S.opening && !screen.owner;
    const restarting = !!S.media && S.room.loading && !screen.owner;
    el.loader.hidden = !(opening || restarting);
    if (el.loader.hidden) return;
    const step = OPEN_ORDER.indexOf(OPEN.step);
    el.loaderText.textContent = opening ? t(`status_${OPEN.step || 'opening'}`, OPEN.params) : t('loading_stream');
    // The bar moves step by step; between steps (and while the stream restarts) it shimmers.
    el.loaderBar.style.width = opening ? `${Math.round(((Math.max(0, step) + 1) / (OPEN_ORDER.length + 1)) * 100)}%` : '';
    el.loader.classList.toggle('indeterminate', !opening);
    const tor = opening ? OPEN.torrent : null;
    el.loaderStats.textContent = !tor ? '' : tor.numPeers
      ? t('loader_torrent', { peers: tor.numPeers, speed: fmtBytes(tor.downloadSpeed), got: fmtBytes(tor.downloaded) })
      : t('loader_no_peers');
    el.loaderCancel.hidden = !opening || !S.canChangeMedia;
  }
  el.loaderCancel.addEventListener('click', async () => {
    el.loaderCancel.disabled = true; el.loaderCancel.classList.add('busy');
    try { await api('/api/media/cancel', { method: 'POST' }); } catch (err) { toast(errorText(err), 'error'); }
    el.loaderCancel.disabled = false;
  });

  // ---------------------------------------------------------------- player
  function applyMedia (media) {
    const changedFilm = (S.media && S.media.mediaKey) !== (media && media.mediaKey);
    S.media = media;
    if (changedFilm) { S.cues.clear(); resetAddonSubs(); }
    if (!media) {
      destroyPlayer();
    } else if (media.streamId !== S.streamId) {
      loadStream(media);
    }
    renderAll();
    phoneSync();
  }

  function destroyPlayer () {
    if (S.hls) { S.hls.destroy(); S.hls = null; }
    video.removeAttribute('src');
    video.load();
    S.streamId = null;
  }

  // Patient loading: hls.js gives up on a request with no first byte in 10 s and asks for it
  // again from zero, throwing away what a busy link (Funnel) had half sent; every error in
  // playback.log was one of these. 30 s for the first byte, and more tries before a fatal error.
  const hlsPolicy = (maxLoadTimeMs, timeouts, errors) => ({
    default: {
      maxTimeToFirstByteMs: 30000, maxLoadTimeMs,
      timeoutRetry: { maxNumRetry: timeouts, retryDelayMs: 0, maxRetryDelayMs: 0 },
      errorRetry: { maxNumRetry: errors, retryDelayMs: 1000, maxRetryDelayMs: 8000 },
    },
  });
  const HLS_LOAD_POLICIES = {
    manifestLoadPolicy: hlsPolicy(60000, 4, 4),
    playlistLoadPolicy: hlsPolicy(60000, 4, 6),
    fragLoadPolicy: hlsPolicy(120000, 6, 8),
  };

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
        ...HLS_LOAD_POLICIES,
      });
      const mediaErrors = [];
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (!data.fatal) return;
        report('hls_error', `${data.type} ${data.details}${data.error ? `: ${data.error.message || data.error}` : ''}`);
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
          setTimeout(() => { if (S.hls === hls) hls.startLoad(); }, 1500);
        } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
          // The first time a plain recovery; again within 20 s with the audio codec swapped; a
          // third time the stream is loaded afresh. Each one goes back to where the room is.
          const now = performance.now();
          while (mediaErrors.length && now - mediaErrors[0] > 20000) mediaErrors.shift();
          mediaErrors.push(now);
          if (mediaErrors.length >= 3) { loadStream(S.media); return; }
          if (mediaErrors.length === 2) hls.swapAudioCodec();
          hls.recoverMediaError();
          setTimeout(() => { if (S.hls === hls && S.media) seekFilm(expectedPosition()); }, 300);
        } else {
          console.error('hls fatal error', data);
          setTimeout(() => { if (S.hls === hls && S.media) loadStream(S.media); }, 2000);
        }
      });
      hls.on(Hls.Events.FRAG_LOADED, (_event, data) => noteFragment(data));
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
    if (S.bufferingSent) maybeResume();
  }

  // ---- how much film a waiting viewer gathers before the room goes on
  // A few seconds in hand, so a slow viewer does not stop the room every second. 3.5 s, not the
  // 4 s of a segment: after a stall at a segment's start one segment gives 3.99… s, and the room
  // waited for a second one. A viewer who stalls again within two minutes gathers more this time
  // (10 s, then 20 s: fewer, longer stops instead of many short ones); each two calm minutes
  // step it back down. The server lets the room go on after 20 s of waiting anyway (room.py),
  // so on a link slower than half the film the 20 s step ends with the room going on.
  const RESUME = { levels: [3.5, 10, 20], level: 0, lastStall: -Infinity, repeatMs: 120000 };
  function noteStall () {
    const now = performance.now();
    const calm = now - RESUME.lastStall;
    if (calm < RESUME.repeatMs) RESUME.level = Math.min(RESUME.level + 1, RESUME.levels.length - 1);
    else RESUME.level = Math.max(0, RESUME.level - Math.floor(calm / RESUME.repeatMs)); // a step down per calm stretch
    RESUME.lastStall = now;
  }
  const resumeAhead = () => RESUME.levels[RESUME.level];
  function maybeResume () {
    if (!S.bufferingSent || video.seeking || !S.media) return;
    const ahead = bufferedAhead();
    const nearEnd = filmTime() + ahead >= S.media.duration - 0.5;
    if (ahead >= resumeAhead() || nearEnd) reportBuffering(false);
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
    if (value) noteStall();
    S.bufferingSent = value;
    // The film time and what is in hand go to the playback log; the server pauses the room at the position.
    send({ type: 'buffering', value, position: filmTime(), ahead: bufferedAhead() });
  }
  // ---- a picture that stops while the film goes on
  // A friend's screen went black with the time running and came back after a seek: the browser's
  // video decoder had stopped giving frames. The watch counts the frames the decoder gives
  // (getVideoPlaybackQuality), not the colour of the picture: a black scene is still 24 frames a
  // second. When the film time moves on for FRAME_STALL_S with no new frame, this viewer alone
  // seeks to where the room is (what a manual seek did); if that does not hold for a minute, the
  // stream is loaded afresh; after that it only reports, for two minutes. A hidden tab is left
  // alone (the browser may stop its picture on purpose), and so is the first while after it shows again.
  const FRAME_STALL_S = 4;
  const frameWatch = { frames: -1, time: 0, stalled: 0, lastFix: 0, step: 0, calmUntil: 0, fixes: 0, reloads: 0 };
  function watchFrames () {
    const now = performance.now();
    const quality = video.getVideoPlaybackQuality ? video.getVideoPlaybackQuality() : null;
    const watching = S.joined && S.media && S.media.width && S.streamId && !video.paused && !video.seeking &&
      video.readyState >= 3 && (!!PIP.win || !document.hidden) && !el.stage.classList.contains('sharing');
    if (!quality || !watching || now < frameWatch.calmUntil) { frameWatch.frames = -1; frameWatch.stalled = 0; return; }
    const frames = quality.totalVideoFrames;
    const time = video.currentTime;
    if (frameWatch.frames < 0 || frames !== frameWatch.frames) frameWatch.stalled = 0;
    else if (time > frameWatch.time) frameWatch.stalled += time - frameWatch.time;
    frameWatch.frames = frames;
    frameWatch.time = time;
    if (frameWatch.stalled < FRAME_STALL_S) return;
    frameWatch.frames = -1;
    frameWatch.stalled = 0;
    if (now - frameWatch.lastFix > 60000) frameWatch.step = 0; // the last fix held: start again gently
    frameWatch.lastFix = now;
    frameWatch.step += 1;
    const detail = `no new frame for ${FRAME_STALL_S} s at ${frames} frames`;
    if (frameWatch.step === 1) {
      frameWatch.fixes += 1;
      report('frames_stalled', `${detail}; seeking`);
      seekFilm(expectedPosition());
    } else if (frameWatch.step === 2) {
      frameWatch.reloads += 1;
      report('reloaded', `${detail} again; loading the stream afresh`);
      loadStream(S.media);
    } else {
      report('frames_stalled', `${detail}; nothing helped, waiting 2 minutes`);
      frameWatch.calmUntil = now + 120000;
    }
  }
  setInterval(watchFrames, 1000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) frameWatch.calmUntil = Math.max(frameWatch.calmUntil, performance.now() + 5000);
  });
  video.addEventListener('error', () => {
    const err = video.error;
    if (!err || !S.media || /empty src/i.test(err.message || '')) return; // destroyPlayer empties it on purpose
    report('video_error', `code ${err.code}${err.message ? `: ${err.message}` : ''}`);
  });
  // What went wrong in this browser goes to the host's data/playback.log, with the film time.
  function report (kind, detail) {
    console.warn('[cowatch]', kind, detail);
    send({ type: 'report', kind, detail, ua: navigator.userAgent, position: S.media ? filmTime() : undefined });
  }

  // ---- a black picture on this page only
  // Every LUMA_EVERY_MS while the room runs and the film is shown, the picture is copied into a
  // 32×18 canvas and its mean brightness goes to the server with the film time and the player's
  // numbers (`luma`). The server compares the pages: black here while another page is bright at
  // the same film moment means trouble on this page (a dark scene is dark for everyone), and it
  // sends `repair`: first a seek to where the room is, again within a minute a fresh stream,
  // after that only a report. A video with no picture at all draws nothing and counts as black.
  // A canvas the browser will not read (tainted) sends nothing.
  const LUMA_EVERY_MS = 3000;
  const lumaWatch = { canvas: null, ctx: null, stateAt: 0, welcomes: 0, calmUntil: 0, lastRepair: 0, step: 0 };
  function pictureLuma () {
    if (!lumaWatch.ctx) {
      lumaWatch.canvas = document.createElement('canvas');
      lumaWatch.canvas.width = 32; lumaWatch.canvas.height = 18;
      lumaWatch.ctx = lumaWatch.canvas.getContext('2d', { willReadFrequently: true });
    }
    const ctx = lumaWatch.ctx;
    try {
      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, 32, 18);
      ctx.drawImage(video, 0, 0, 32, 18);
      const data = ctx.getImageData(0, 0, 32, 18).data;
      let sum = 0;
      for (let i = 0; i < data.length; i += 4) sum += 0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2];
      return sum / (data.length / 4);
    } catch { return null; }
  }
  function sampleLuma () {
    const now = performance.now();
    const showing = S.joined && S.media && S.media.width && roomRunning() && !video.seeking &&
      (!!PIP.win || !document.hidden) && !el.stage.classList.contains('sharing');
    if (!showing || now < lumaWatch.calmUntil) return;
    const luma = pictureLuma();
    if (luma === null) return;
    const quality = video.getVideoPlaybackQuality ? video.getVideoPlaybackQuality() : null;
    send({
      type: 'luma',
      t: video.readyState >= 1 ? filmTime() : expectedPosition(),
      luma: Math.round(luma * 10) / 10,
      ready: video.readyState,
      ahead: Math.round(bufferedAhead() * 10) / 10,
      paused: video.paused,
      frames: quality ? quality.totalVideoFrames : undefined,
      dropped: quality ? quality.droppedVideoFrames : undefined,
      stream: S.streamId || undefined,
      streamOk: S.streamId === S.media.streamId,
      stateMs: lumaWatch.stateAt ? Math.round(now - lumaWatch.stateAt) : undefined,
      reconnects: Math.max(0, lumaWatch.welcomes - 1),
    });
  }
  setInterval(sampleLuma, LUMA_EVERY_MS);
  // A new stream (destroyPlayer empties the video) has no picture until its first part arrives.
  video.addEventListener('emptied', () => { lumaWatch.calmUntil = Math.max(lumaWatch.calmUntil, performance.now() + 10000); });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) lumaWatch.calmUntil = Math.max(lumaWatch.calmUntil, performance.now() + 5000);
  });
  function onRepair () {
    if (!S.media) return;
    const now = performance.now();
    if (now - lumaWatch.lastRepair > 60000) lumaWatch.step = 0; // the last repair held: start again gently
    lumaWatch.lastRepair = now;
    lumaWatch.step += 1;
    lumaWatch.calmUntil = now + 4000; // give the fix a moment before the next sample
    if (lumaWatch.step === 1) {
      report('repaired', 'black picture while others see the film; seeking');
      seekFilm(expectedPosition());
    } else if (lumaWatch.step === 2) {
      report('repaired', 'black picture again; loading the stream afresh');
      loadStream(S.media);
    } else {
      report('repaired', 'black picture again; nothing more to try');
    }
  }

  // ---- connection panel: how fast this viewer's film segments arrive
  // From hls.js's statistics for each segment: bytes over the time from the first byte to the
  // last (the wait before the first byte is mostly the server making a converted segment). Over
  // the last NET.window segments, sent every 10 s; the people chips show it next to the film's
  // bitrate, and the host hears about a viewer who keeps stalling (server/netpanel.py).
  const NET = { window: 8, samples: [], mbps: null, every: 10000, slowBelow: 1.2 };
  const netSpeed = new Map(); // client id -> {mbps, ahead}, from the server
  function noteFragment (data) {
    const st = (data.frag && data.frag.stats) || data.stats;
    if (!st || !st.loaded || !st.loading) return;
    const ms = st.loading.end - (st.loading.first || st.loading.start);
    if (!(ms >= 0)) return;
    NET.samples.push({ bytes: st.loaded, ms: Math.max(ms, 1) });
    while (NET.samples.length > NET.window) NET.samples.shift();
    const bytes = NET.samples.reduce((a, x) => a + x.bytes, 0);
    const time = NET.samples.reduce((a, x) => a + x.ms, 0);
    NET.mbps = Math.min(1000, (bytes * 8) / time / 1000);
  }
  setInterval(() => {
    if (S.joined && S.media && NET.mbps != null) {
      send({ type: 'netstat', mbps: Math.round(NET.mbps * 100) / 100, bufferedAhead: Math.round(bufferedAhead() * 10) / 10 });
    }
  }, NET.every);
  function onNetstat (msg) {
    netSpeed.set(msg.id, { mbps: msg.mbps, ahead: msg.ahead });
    renderNet(msg.id);
  }
  const fmtMbps = (mbps) => (mbps >= 100 ? String(Math.round(mbps)) : mbps.toFixed(1).replace('.', t('decimal_sep')));
  const filmMbps = () => (S.media && S.media.streamKbps ? S.media.streamKbps / 1000 : null);
  // "3,1 Mbps · film 4,7 Mbps", and whether that link is too slow for this film.
  function netInfo (id) {
    const net = netSpeed.get(id) || (memberById(id) || {}).net;
    if (!net || typeof net.mbps !== 'number') return null;
    const film = filmMbps();
    const text = film ? t('net_speed_film', { mbps: fmtMbps(net.mbps), film: fmtMbps(film) }) : t('net_speed', { mbps: fmtMbps(net.mbps) });
    return { text, slow: !!film && net.mbps < film * NET.slowBelow };
  }
  function renderNet (id) {
    const chip = el.members.querySelector(`[data-id="${id}"]`);
    if (chip) {
      const info = netInfo(id);
      chip.classList.toggle('net-slow', !!(info && info.slow));
      chip.title = [...(chip.dataset.titles ? chip.dataset.titles.split('\n') : []), info ? info.text : ''].filter(Boolean).join(' · ');
    }
    if (popFor === id && !el.peerPop.hidden) renderPeerNet(id);
  }
  function renderPeerNet (id) {
    const info = netInfo(id);
    el.peerNet.hidden = !info;
    el.peerNet.textContent = info ? info.text : '';
    el.peerNet.classList.toggle('slow', !!(info && info.slow));
  }
  // The host's notice: someone keeps waiting, how fast their link is, and what can be done.
  function onNetHint (msg) {
    const film = msg.filmKbps ? fmtMbps(msg.filmKbps / 1000) : null;
    const params = { name: msg.name, n: msg.stalls, minutes: msg.minutes, mbps: msg.mbps != null ? fmtMbps(msg.mbps) : '', film: film || '' };
    const key = msg.mbps != null && film ? 'net_hint' : film ? 'net_hint_film' : 'net_hint_plain';
    const actions = [];
    if (S.isHost) {
      actions.push({ label: t('net_hint_quality'), run: () => openSettingsAt('quality') });
      if (msg.funnel) actions.push({ label: t('net_hint_serve'), run: () => openSettingsAt('connection', t('net_hint_serve_note')) });
    }
    actionToast(t(key, params), actions);
  }
  function actionToast (text, actions, ms = 30000) {
    const node = toast(text, 'info', ms);
    node.classList.add('with-actions');
    if (!actions.length) return node;
    const row = document.createElement('div');
    row.className = 'toast-actions';
    for (const a of actions) {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'ghost'; b.textContent = a.label;
      b.addEventListener('click', () => { node.remove(); a.run(); });
      row.appendChild(b);
    }
    node.appendChild(row);
    return node;
  }
  async function openSettingsAt (key, note) {
    await openSettings();
    if (el.settingsOverlay.hidden) return;
    const field = el.settingsForm.querySelector(`[data-key="${key}"]`);
    if (!field) return;
    field.scrollIntoView({ block: 'center' });
    field.classList.add('pointed');
    setTimeout(() => field.classList.remove('pointed'), 4000);
    if (key === 'quality' && radio('quality') !== 'manual') { setRadio('quality', 'manual'); renderQuality(); }
    if (key === 'quality') el.qualityMbps.focus();
    if (note) toast(note, 'info', 9000);
  }

  video.addEventListener('waiting', () => {
    clearTimeout(S.waitTimer);
    S.waitTimer = setTimeout(() => {
      if (S.joined && video.readyState < 3 && roomRunning() && !S.bufferingSent) reportBuffering(true);
    }, 1200);
  });
  video.addEventListener('playing', () => {
    clearTimeout(S.waitTimer);
    maybeResume(); // with the same seconds in hand as syncTick
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
    el.screenVideo.volume = video.volume;
    el.screenVideo.muted = video.muted || screen.owner === S.clientId; // my own screen: no echo of my sound
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
    prefs.muted = video.muted; savePrefs(); applyFilmVolume(); renderControls();
  });

  // The iPhone's Safari lets only a <video> go fullscreen, not the stage with its subtitles,
  // pointers and chat: there the stage fills the window instead (.fill).
  const stageFull = () => (document.fullscreenElement || document.webkitFullscreenElement) === el.stage
    || el.stage.classList.contains('fill');
  function setFill (on) {
    el.stage.classList.toggle('fill', on);
    document.documentElement.classList.toggle('stage-fill', on);
    renderMini();
    placeChat();
  }
  function toggleFullscreen () {
    if (PIP.win) return; // a picture-in-picture window cannot go fullscreen
    if (el.stage.classList.contains('fill')) { setFill(false); return; }
    const fsEl = document.fullscreenElement || document.webkitFullscreenElement;
    if (fsEl) {
      (document.exitFullscreen || document.webkitExitFullscreen).call(document);
      return;
    }
    const request = el.stage.requestFullscreen || el.stage.webkitRequestFullscreen;
    const asked = request ? request.call(el.stage) : null;
    if (!request) setFill(true);
    else if (asked && asked.catch) asked.catch(() => setFill(true));
  }
  el.fsBtn.addEventListener('click', toggleFullscreen);
  document.addEventListener('fullscreenchange', () => renderMini());

  // ---- the player follows the viewer
  // Scrolled down to the source lists, the stage moves to a corner box (its place on the page
  // is held, so nothing jumps); a click on it scrolls back. The window button puts it in its
  // own always-on-top window (Chrome's Document Picture-in-Picture), which stays in front of
  // every app and monitor. Unlike the video-only picture-in-picture it takes the subtitles,
  // pointers and drawings along, since they are part of the stage.
  const MINI = { visible: true, off: false };
  const PIP = { win: null };
  new IntersectionObserver((entries) => {
    MINI.visible = entries[0].isIntersecting;
    if (MINI.visible) MINI.off = false; // closed for this trip down the page only
    renderMini();
    if (CHAT.unread) renderChat(); // scrolled back to the chat column
  }, { threshold: 0.2 }).observe(el.stageWrap);

  function renderMini () {
    const want = !MINI.visible && !MINI.off && !PIP.win && !stageFull() && !!(S.media || screen.owner);
    if (want === el.stage.classList.contains('mini')) return;
    el.stageWrap.style.height = want ? `${el.stageWrap.offsetHeight}px` : '';
    el.stage.classList.toggle('mini', want);
    document.body.classList.toggle('has-mini', want); // notices move up, off the box
  }
  el.miniBack.addEventListener('click', () => el.stageWrap.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  el.miniClose.addEventListener('click', () => { MINI.off = true; renderMini(); });

  el.pipBtn.hidden = !('documentPictureInPicture' in window);
  async function togglePip () {
    if (PIP.win) { PIP.win.close(); return; }
    const height = Math.round(Math.min(360, el.stage.clientHeight || 360));
    let win;
    try {
      win = await window.documentPictureInPicture.requestWindow({ width: Math.round(height * 16 / 9), height });
    } catch (err) {
      toast(errorText(err), 'error');
      return;
    }
    PIP.win = win;
    for (const node of document.querySelectorAll('link[rel="stylesheet"], style')) win.document.head.appendChild(node.cloneNode(true));
    win.document.documentElement.style.cssText = document.documentElement.style.cssText; // subtitle size and height
    win.document.title = document.title;
    win.document.body.className = 'pip-body';
    el.stageWrap.style.height = `${el.stageWrap.offsetHeight}px`;
    el.stage.classList.remove('mini');
    el.stage.classList.add('pip');
    win.document.body.appendChild(el.stage);
    placeChat(); // the column stays behind: the panel goes along, over the picture
    resumeAfterMove();
    el.stageWrap.classList.add('away');
    el.awayMsg.hidden = false;
    // Keys pressed in the small window work as on the page (space, arrows, m...).
    win.document.addEventListener('keydown', (e) => {
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return; // typing in the chat
      const copy = new KeyboardEvent('keydown', { key: e.key, code: e.code, ctrlKey: e.ctrlKey, metaKey: e.metaKey, altKey: e.altKey, shiftKey: e.shiftKey });
      if (!document.dispatchEvent(copy) || copy.defaultPrevented) e.preventDefault();
    });
    win.addEventListener('pagehide', () => {
      el.stage.classList.remove('pip');
      el.stageWrap.appendChild(el.stage);
      resumeAfterMove();
      el.stageWrap.classList.remove('away');
      el.awayMsg.hidden = true;
      el.stageWrap.style.height = '';
      PIP.win = null;
      renderMini();
      placeChat();
    });
    win.requestAnimationFrame(pipFrame);
  }
  // The browser pauses a video moved to another document; a running room carries on at once.
  function resumeAfterMove () {
    if (roomRunning() && S.media && !screen.owner) video.play().catch(() => {});
    if (screen.owner && el.screenVideo.srcObject) el.screenVideo.play().catch(() => {});
  }
  el.pipBtn.addEventListener('click', togglePip);
  el.pipReturn.addEventListener('click', () => { if (PIP.win) PIP.win.close(); });
  el.stage.addEventListener('dblclick', (e) => {
    clearTimeout(clickTimer);
    if (lastPointer === 'touch') return; // a double tap is handled below
    if (!isUi(e.target) && !S.penMode) toggleFullscreen();
  });
  // A click on the picture plays or pauses for everyone, and pokes the others too (see
  // presence below). It waits a moment, so a double click goes fullscreen without also
  // pausing and playing. On a touch screen a tap only shows the controls.
  // Only a press that began on the picture and stayed put counts: letting go of a dragged
  // camera tile or a pen stroke over the picture is not a click.
  let clickTimer = null;
  let pressAt = null;
  let lastPointer = 'mouse';
  el.stage.addEventListener('pointerdown', (e) => {
    lastPointer = e.pointerType;
    pressAt = { x: e.clientX, y: e.clientY, ui: isUi(e.target) };
  });

  // On a touch screen one tap only shows the controls. A quick double tap in the small picture
  // goes fullscreen, wherever it is (its sides are too narrow to aim at); in fullscreen it seeks
  // 10 s on the sides (a quarter each) and goes back in the large middle. More taps on the
  // same side right after add up (+10, +20…), and the room gets one seek once they stop, so the
  // stream does not start again for everyone on every tap.
  const TAP = { gapMs: 300, slop: 40, side: 0.25, step: 10, moreMs: 800, sendMs: 600 };
  const tap = { at: 0, x: 0, y: 0, run: null, timer: null, hide: null };
  function tapSide (x) {
    const r = el.stage.getBoundingClientRect();
    const f = (x - r.left) / r.width;
    return f < TAP.side ? 'back' : f > 1 - TAP.side ? 'fwd' : 'mid';
  }
  function showTapSeek (side, total) {
    el.tapSeek.className = `tap-seek ${side}`;
    el.tapSeek.textContent = side === 'back' ? `⏪ ${t('tap_seconds', { n: total })}` : `${t('tap_seconds', { n: total })} ⏩`;
    el.tapSeek.hidden = false;
    clearTimeout(tap.hide);
    tap.hide = setTimeout(() => { el.tapSeek.hidden = true; }, TAP.sendMs + 500);
  }
  function tapSeek (side) {
    const now = performance.now();
    if (!tap.run || tap.run.side !== side) tap.run = { side, base: expectedPosition(), total: 0 };
    tap.run.total += TAP.step;
    tap.run.last = now;
    showTapSeek(side, tap.run.total);
    clearTimeout(tap.timer);
    tap.timer = setTimeout(() => {
      const run = tap.run;
      tap.run = null;
      if (run) seekTo(run.base + (run.side === 'back' ? -run.total : run.total));
    }, TAP.sendMs);
  }
  el.stage.addEventListener('pointerup', (e) => {
    const press = pressAt;
    if (e.pointerType !== 'touch' || !press || press.ui || isUi(e.target) || S.penMode) return;
    if (Math.hypot(e.clientX - press.x, e.clientY - press.y) > TAP.slop) return; // a swipe
    const now = performance.now();
    const side = stageFull() ? tapSide(e.clientX) : 'mid';
    const seeks = side !== 'mid' && S.media && !screen.owner;
    if (seeks && tap.run && tap.run.side === side && now - tap.run.last < TAP.moreMs) { tapSeek(side); return; }
    const quick = now - tap.at < TAP.gapMs && Math.hypot(e.clientX - tap.x, e.clientY - tap.y) < TAP.slop;
    if (!quick) { Object.assign(tap, { at: now, x: e.clientX, y: e.clientY }); return; }
    tap.at = 0;
    if (side === 'mid') toggleFullscreen();
    else if (seeks) tapSeek(side);
  });
  el.stage.addEventListener('click', (e) => {
    if (isUi(e.target)) return;
    if (S.autoplayBlocked) { video.play().catch(() => {}); return; }
    clearTimeout(clickTimer);
    const press = pressAt;
    pressAt = null;
    if (!press || press.ui || Math.hypot(e.clientX - press.x, e.clientY - press.y) > 6) return;
    if (e.detail > 1 || S.penMode || e.pointerType === 'touch' || screen.owner) return;
    clickTimer = setTimeout(togglePlay, 250);
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
    if (!el.settingsOverlay.hidden) return; // its own keys: Escape closes it
    const tag = (e.target && e.target.tagName) || '';
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(tag)) return;
    if (e.code === 'Space' || e.key === 'k') { e.preventDefault(); togglePlay(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); seekTo(expectedPosition() - 10); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); seekTo(expectedPosition() + 10); }
    else if (e.key === 'f') toggleFullscreen();
    else if (e.key === 'm') el.muteBtn.click();
    else if (e.key === 'd') setTool(S.penMode && !S.eraser ? null : 'pen');
    else if (e.key === 'e') setTool(S.eraser ? null : 'eraser');
    else if (e.key === 'c') { e.preventDefault(); setChat(true); } // preventDefault: no "c" in the box
    else if (e.key === 'Escape') {
      el.palette.hidden = true; el.micMenu.hidden = true; el.camMenu.hidden = true; el.screenMenu.hidden = true; el.peerPop.hidden = true;
      if (camBig.id) showBig(null);
      else if (S.penMode) setPen(false);
      else if (el.stage.classList.contains('fill')) setFill(false);
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

  const isUi = (node) => !!(node && node.closest && node.closest('.controls, .toolbar, .cams-box, .cam-big, .center-msg.clickable, .share-asks, .mini-back, .mini-close, .chat, .loader'));
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
    const pic = screen.owner ? el.screenVideo : video; // a shared screen covers the film
    const vw = pic.videoWidth; const vh = pic.videoHeight;
    if ((S.media || screen.owner) && vw && vh && w && h) {
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
  // A face (web/style.css): the colour, the eyes, and the ears and snout of the chosen animal.
  const ANIMALS = ['ball', 'cat', 'bear', 'bunny', 'fox', 'panda', 'mouse', 'dog'];
  const FACE = '<span class="ear l"></span><span class="ear r"></span>'
    + '<span class="head"><span class="eye"><i></i></span><span class="eye"><i></i></span><span class="snout"></span></span>';
  const myAnimal = () => (ANIMALS.includes(prefs.animal) ? prefs.animal : 'ball');
  const animalOf = (m) => (m && ANIMALS.includes(m.animal) ? m.animal : 'ball');
  function makeFace (animal, color) {
    const face = document.createElement('div');
    face.className = 'face';
    face.innerHTML = FACE;
    face.dataset.animal = animal;
    if (color) face.style.setProperty('--c', color);
    return face;
  }
  function makeBall (me) {
    const node = document.createElement('div');
    node.className = me ? 'ball me gone' : 'ball gone';
    node.innerHTML = `<div class="body face" data-animal="ball">${FACE}</div><span class="tag"></span>`;
    el.cursors.appendChild(node);
    return { node, face: node.querySelector('.face'), tag: node.querySelector('.tag'), x: 0, y: 0, tx: 0, ty: 0, lx: 0, ly: 0, seen: 0, visible: false };
  }
  const balls = new Map(); // clientId -> the ball of another viewer
  const mine = Object.assign(makeBall(true), { inside: false, overUi: false, sent: false, sx: null, sy: null });

  function paintBall (ball, color, name, animal) {
    ball.node.style.setProperty('--c', color);
    if (ball.tag.textContent !== name) ball.tag.textContent = name;
    ball.face.dataset.animal = animal || 'ball';
  }
  function ballFor (id) {
    let ball = balls.get(id);
    if (!ball) {
      ball = makeBall(false);
      balls.set(id, ball);
      const m = memberById(id);
      paintBall(ball, colorOf(id), m ? m.name : '?', animalOf(m));
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
      paintBall(ball, m.color || '#ffffff', m.name, animalOf(m));
    }
    for (const stroke of strokes.values()) if (!stroke.done && !ids.has(stroke.owner)) finishStroke(stroke);
    const me = memberById(S.clientId);
    if (me && me.color && me.color !== prefs.color) { prefs.color = me.color; savePrefs(); }
    // The host trusted me with the film folders, or took it back: kept across reconnects, so
    // only a real change is news.
    const cohost = !!(me && me.cohost);
    if (me && cohost !== S.cohost) {
      if (S.cohost !== null) { toast(t(cohost ? 'cohost_granted' : 'cohost_revoked')); pollStatus(); }
      S.cohost = cohost;
    }
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
  // An eraser is a stroke too (`erase`): drawn in order with the others, it rubs out what was
  // drawn before it where it passes, as wide as a share of the picture so it covers the same
  // spot on every screen. It never fades by itself; it goes once nothing is left under it.
  const strokes = new Map(); // `${owner}:${id}` -> { id, owner, color, pts, done, fadeAt, erase }
  const ERASER_SIZE = 0.045; // of the picture's height: about 50 px on a 1080p picture
  const drawCtx = el.drawCanvas.getContext('2d');
  let drawDirty = true; let geomKey = '';
  let myStroke = null; let strokeQueue = []; let strokeTimer = null;

  function addStroke (key, id, owner, color, erase = false) {
    if (strokes.size >= MAX_STROKES) strokes.delete(strokes.keys().next().value);
    const stroke = { id, owner, color, pts: [], done: false, fadeAt: null, erase };
    strokes.set(key, stroke);
    return stroke;
  }
  // While the film plays, a finished stroke fades after a few seconds. While it is paused,
  // strokes stay until playback resumes or someone clears them.
  function finishStroke (stroke) {
    stroke.done = true;
    stroke.fadeAt = roomRunning() && !stroke.erase ? performance.now() + STROKE_HOLD_MS : null;
    drawDirty = true;
  }
  function retimeStrokes () {
    const running = roomRunning(); const now = performance.now();
    for (const stroke of strokes.values()) {
      if (!stroke.done || stroke.erase) continue;
      if (running && stroke.fadeAt === null) stroke.fadeAt = now + 1500;
      else if (!running && stroke.fadeAt !== null && stroke.fadeAt > now) stroke.fadeAt = null;
    }
    drawDirty = true;
  }
  function onDraw (msg) {
    if (!msg.from || msg.from === S.clientId) return;
    const key = `${msg.from}:${msg.stroke}`;
    const stroke = strokes.get(key) || addStroke(key, msg.stroke, msg.from, msg.color || colorOf(msg.from), !!msg.erase);
    for (const p of msg.points || []) if (stroke.pts.length < MAX_STROKE_POINTS) stroke.pts.push(p);
    if (msg.end) finishStroke(stroke);
    drawDirty = true;
  }
  function eraseStrokes (keys) {
    for (const key of keys) strokes.delete(key);
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

  // The pen or the eraser (null: neither). Both take the picture's clicks away from playing.
  function setTool (tool) {
    S.penMode = !!tool;
    S.eraser = tool === 'eraser';
    el.stage.classList.toggle('drawing', S.penMode);
    el.stage.classList.toggle('erasing', S.eraser);
    el.penBtn.classList.toggle('active', S.penMode && !S.eraser);
    el.eraserBtn.classList.toggle('active', S.eraser);
    el.palette.hidden = true;
    if (S.penMode) withdrawCursor(); // while drawing, the stroke itself shows where you are
    renderEraserModes();
    renderMine();
  }
  // Two erasers: the area under it (a stroke that rubs out), or whole lines it touches.
  function renderEraserModes () {
    el.eraserModes.hidden = !S.eraser;
    el.stage.classList.toggle('erase-whole', S.eraser && !!prefs.eraseWhole);
    if (!S.eraser) return;
    const row = el.stage.classList.contains('tools-row'); // under the button, or beside it
    el.eraserModes.style.top = row ? '' : `${el.eraserBtn.offsetTop + el.eraserBtn.offsetHeight / 2}px`;
    el.eraserModes.style.left = row ? `${el.eraserBtn.offsetLeft + el.eraserBtn.offsetWidth / 2}px` : '';
    for (const btn of el.eraserModes.querySelectorAll('button')) {
      btn.classList.toggle('sel', (btn.dataset.mode === 'whole') === !!prefs.eraseWhole);
    }
    sizeEraserCursor(geom());
  }
  el.eraserModes.addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    prefs.eraseWhole = btn.dataset.mode === 'whole'; savePrefs();
    renderEraserModes();
  });
  // The pointer is a ring as wide as what the eraser takes away.
  let eraserCursorPx = 0;
  function sizeEraserCursor (g) {
    const d = prefs.eraseWhole ? 2 * ERASER_PX : Math.round(clamp(g.h * ERASER_SIZE, 8, 120));
    if (d === eraserCursorPx) return;
    eraserCursorPx = d;
    const r = d / 2 - 1.5; const c = d / 2;
    const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='${d}' height='${d}'>`
      + `<circle cx='${c}' cy='${c}' r='${r}' fill='rgba(255,255,255,.18)' stroke='white' stroke-width='2'/>`
      + `<circle cx='${c}' cy='${c}' r='${r}' fill='none' stroke='black' stroke-opacity='.5' stroke-dasharray='3 3'/></svg>`;
    el.stage.style.setProperty('--eraser-cursor', `url("data:image/svg+xml,${encodeURIComponent(svg)}") ${Math.round(c)} ${Math.round(c)}, cell`);
  }
  const setPen = (on) => setTool(on ? 'pen' : null);

  // The whole-line eraser takes the pen lines it touches, anyone's (finished ones only).
  const ERASER_PX = 12;
  let wiping = null;
  function segmentDistance (px, py, ax, ay, bx, by) {
    const dx = bx - ax; const dy = by - ay;
    const len = dx * dx + dy * dy;
    const k = len ? clamp(((px - ax) * dx + (py - ay) * dy) / len, 0, 1) : 0;
    return Math.hypot(px - (ax + k * dx), py - (ay + k * dy));
  }
  function wipeAt (events) {
    const g = geom();
    const reach = ERASER_PX + Math.max(4, g.h * 0.009) / 2; // the ring's radius and half a line
    const hit = [];
    for (const ev of events) {
      const [x, y] = toPicture(ev, g);
      const px = x * g.w; const py = y * g.h;
      for (const [key, stroke] of strokes) {
        if (!stroke.done || stroke.erase || hit.includes(key)) continue;
        const pts = stroke.pts;
        for (let i = 0; i < pts.length; i++) {
          const a = pts[i]; const b = pts[Math.min(i + 1, pts.length - 1)];
          if (segmentDistance(px, py, a[0] * g.w, a[1] * g.h, b[0] * g.w, b[1] * g.h) <= reach) { hit.push(key); break; }
        }
      }
    }
    if (!hit.length) return;
    send({ type: 'draw_erase', strokes: hit.map((key) => { const s = strokes.get(key); return [s.owner, s.id]; }) });
    eraseStrokes(hit);
  }
  el.penBtn.addEventListener('click', () => setTool(S.penMode && !S.eraser ? null : 'pen'));
  el.eraserBtn.addEventListener('click', () => setTool(S.eraser ? null : 'eraser'));

  el.drawCanvas.addEventListener('pointerdown', (e) => {
    if (!S.penMode || !S.joined || (e.pointerType === 'mouse' && e.button !== 0)) return;
    e.preventDefault();
    el.drawCanvas.setPointerCapture(e.pointerId);
    if (S.eraser && prefs.eraseWhole) { wiping = e.pointerId; wipeAt([e]); return; }
    const id = Math.random().toString(36).slice(2, 10);
    const p = toPicture(e, geom());
    const color = myColor();
    myStroke = addStroke(`${S.clientId}:${id}`, id, S.clientId, color, S.eraser);
    myStroke.pts.push(p);
    strokeQueue = [];
    send(S.eraser ? { type: 'draw', id, start: true, erase: true, points: [p] } : { type: 'draw', id, start: true, color, points: [p] });
    drawDirty = true;
  });
  el.drawCanvas.addEventListener('pointermove', (e) => {
    if (wiping === e.pointerId) {
      const coalesced = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
      wipeAt(coalesced.length ? coalesced : [e]);
      return;
    }
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
  function endStroke (e) {
    if (e && wiping === e.pointerId) wiping = null;
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
    if (key !== geomKey) { geomKey = key; drawDirty = true; if (S.eraser) sizeEraserCursor(g); }
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
    const penWidth = Math.max(4, g.h * 0.009) * dpr; // a marker: about 10 px on a 1080p picture
    const eraserWidth = g.h * ERASER_SIZE * dpr;
    ctx.shadowColor = 'rgba(0, 0, 0, .55)';
    const at = (p) => [(g.ox + p[0] * g.w) * dpr, (g.oy + p[1] * g.h) * dpr];
    let inked = false; // a pen stroke so far, for an eraser to rub out
    for (const [strokeKey, stroke] of strokes) {
      let alpha = 1;
      if (stroke.erase) {
        if (stroke.done && !inked) { strokes.delete(strokeKey); continue; } // nothing left under it
      } else if (stroke.fadeAt !== null && now >= stroke.fadeAt) {
        alpha = 1 - (now - stroke.fadeAt) / STROKE_FADE_MS;
        if (alpha <= 0) { strokes.delete(strokeKey); continue; }
      }
      const pts = stroke.pts;
      if (!pts.length) continue;
      if (!stroke.erase) inked = true;
      ctx.globalCompositeOperation = stroke.erase ? 'destination-out' : 'source-over';
      ctx.lineWidth = stroke.erase ? eraserWidth : penWidth;
      ctx.shadowBlur = stroke.erase ? 0 : 3 * dpr;
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
    ctx.globalCompositeOperation = 'source-over';
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
    paintBall(mine, color, prefs.name || '?', myAnimal());
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
    const animals = document.createElement('div');
    animals.className = 'palette-animals';
    animals.style.setProperty('--c', current);
    for (const animal of ANIMALS) animals.appendChild(animalButton(animal, current, () => pickAnimal(animal)));
    el.palette.appendChild(animals);
  }
  function animalButton (animal, color, onPick) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.title = t(`animal_${animal}`);
    btn.classList.toggle('sel', animal === myAnimal());
    btn.appendChild(makeFace(animal, color));
    btn.addEventListener('click', onPick);
    return btn;
  }
  function pickAnimal (animal) {
    prefs.animal = animal; savePrefs();
    const me = memberById(S.clientId);
    if (me) me.animal = animal;
    send({ type: 'color', animal });
    el.palette.hidden = true;
    onMembers();
    renderToolbar();
    renderCams();
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
    for (const menu of [el.micMenu, el.camMenu, el.screenMenu]) {
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
    screenAudio: { maxBitrate: 128000 },
  };
  // The sharer picks how a shared screen goes out (prefs.screenQuality). A shared screen is often
  // a video. Auto keeps the frame rate and lets the browser lower the resolution when the link
  // or the processor cannot keep up; high keeps the resolution and drops frames instead; low
  // sends at most 720p for a slow link.
  const SCREEN_QUALITY = {
    auto: { maxBitrate: 4000000, maxFramerate: 30, degradation: 'maintain-framerate' },
    high: { maxBitrate: 10000000, maxFramerate: 30, degradation: 'maintain-resolution' },
    low: { maxBitrate: 1500000, maxFramerate: 24, degradation: 'maintain-framerate', maxHeight: 720 },
  };
  function screenLimits () {
    const q = SCREEN_QUALITY[prefs.screenQuality] || SCREEN_QUALITY.auto;
    const track = screen.stream && screen.stream.getVideoTracks()[0];
    const height = (track && track.getSettings().height) || 0;
    const down = q.maxHeight && height > q.maxHeight ? Math.round(height / q.maxHeight * 100) / 100 : 1;
    return [{ maxBitrate: q.maxBitrate, maxFramerate: q.maxFramerate, scaleResolutionDownBy: down }, q.degradation];
  }
  // The transceivers of a connection, in the order the offer adds them: my sound and camera,
  // then a shared screen's picture and sound. Both sides find them by this order.
  const SLOTS = ['audioTx', 'videoTx', 'screenTx', 'screenAudioTx'];
  const peers = new Map(); // member id -> peer
  const voice = {
    mic: null, cam: null, camStream: null, busy: { mic: false, cam: false }, analyser: null, source: null, buf: null,
  };
  const loud = new Map(); // member id -> { since, last }: when they started, and last were, loud
  const speaking = new Set();

  function sendHello () {
    send({ type: 'hello', name: prefs.name, color: prefs.color, animal: myAnimal(), mic: !!voice.mic, cam: !!voice.cam });
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
      audioTx: null, videoTx: null, videoStream: null, screenTx: null, screenAudioTx: null, screenStream: null,
      queue: Promise.resolve(), limiting: Promise.resolve(), // see limitSenders
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
    pc.ontrack = ({ track, transceiver }) => {
      if (pc.getTransceivers().indexOf(transceiver) >= 2) { // a shared screen's picture or sound
        if (!peer.screenStream) peer.screenStream = new MediaStream();
        peer.screenStream.addTrack(track);
        renderScreen();
        return;
      }
      if (track.kind === 'video') {
        peer.videoStream = new MediaStream([track]); // shown in their tile while their camera is on
        renderCams();
        return;
      }
      audioEl.srcObject = new MediaStream([track]);
      audioEl.play().catch(() => {});
    };
    pc.onsignalingstatechange = () => { if (pc.signalingState === 'stable') limitSenders(peer); };
    pc.onconnectionstatechange = () => {
      if (pc.connectionState === 'connected') limitSenders(peer);
      else if (pc.connectionState === 'failed' && !peer.restarted) { peer.restarted = true; pc.restartIce(); }
    };
    applyPeerVolume(peer);
    if (!peer.polite) {
      SLOTS.forEach((slot, i) => { peer[slot] = pc.addTransceiver(i % 3 ? 'video' : 'audio', { direction: 'sendrecv' }); });
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
    peer.pc.getTransceivers().forEach((tx, i) => {
      const slot = SLOTS[i];
      if (!slot || peer[slot]) return;
      peer[slot] = tx;
      if (tx.direction !== 'sendrecv') tx.direction = 'sendrecv';
    });
    applyLocalTracks(peer);
  }
  function applyLocalTracks (peer) {
    const share = screen.owner === S.clientId ? screen.stream : null; // nothing goes out before it is mine
    const shareVideo = share ? share.getVideoTracks()[0] || null : null;
    const shareAudio = share ? share.getAudioTracks()[0] || null : null;
    for (const [tx, track] of [[peer.audioTx, voice.mic], [peer.videoTx, voice.cam],
      [peer.screenTx, shareVideo], [peer.screenAudioTx, shareAudio]]) {
      if (tx && tx.sender.track !== track) {
        tx.sender.replaceTrack(track).catch((err) => console.warn('[cowatch] replaceTrack', err));
      }
    }
    limitSenders(peer);
  }
  // Chrome hands out encodings before the first negotiation, but with RTCP parameters (cname,
  // reducedSize) that the negotiation then fills in; a setParameters made meanwhile is refused
  // ("modified RTCP parameters"). So a sender is limited only once its transceiver has been
  // negotiated and no offer is in flight; onsignalingstatechange runs this again at 'stable'.
  // Runs for one peer go one after another, and each sender's parameters are read right before
  // they are set.
  function limitSenders (peer) {
    peer.limiting = peer.limiting.then(() => applyLimits(peer));
    return peer.limiting;
  }
  async function applyLimits (peer) {
    for (const [tx, limits, degradation] of [[peer.audioTx, SENDER_LIMITS.audio], [peer.videoTx, SENDER_LIMITS.video],
      [peer.screenTx, ...screenLimits()], [peer.screenAudioTx, SENDER_LIMITS.screenAudio]]) {
      const pc = peer.pc;
      if (pc.signalingState !== 'stable' || peer.makingOffer || !pc.currentLocalDescription) return; // runs again at stable
      if (!tx || !tx.currentDirection || tx.currentDirection === 'stopped') continue;
      const params = tx.sender.getParameters();
      const enc = params.encodings && params.encodings[0];
      const sameDegradation = !degradation || !('degradationPreference' in params) || params.degradationPreference === degradation;
      if (!enc || (sameDegradation && Object.entries(limits).every(([k, v]) => enc[k] === v))) continue;
      Object.assign(enc, limits);
      if (degradation) params.degradationPreference = degradation; // a browser without it ignores it
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
    const level = myLevel();
    const bars = Math.min(5, Math.floor(Math.sqrt(level) * 12)); // about 1 bar at the talking level
    el.previewMeter.querySelectorAll('i').forEach((bar, i) => bar.classList.toggle('on', i < bars));
    el.previewFace.classList.toggle('speaking', level >= SPEAK_LEVEL);
  }

  // ---- the join screen's look: a colour (others' are dimmed: the server would give you
  // another) and an animal, with your face in the preview while the camera is off.
  function renderLook () {
    const taken = new Set(S.members.filter((m) => m.id !== S.clientId && m.color).map((m) => m.color));
    const color = S.palette.includes(prefs.color) ? prefs.color : (S.palette.find((c) => !taken.has(c)) || S.palette[0]);
    el.joinColors.replaceChildren(...S.palette.map((c) => {
      const swatch = document.createElement('button');
      swatch.type = 'button';
      swatch.style.setProperty('--c', c);
      swatch.classList.toggle('sel', c === color);
      swatch.classList.toggle('taken', taken.has(c));
      swatch.addEventListener('click', () => { prefs.color = c; savePrefs(); renderLook(); });
      return swatch;
    }));
    el.joinAnimals.style.setProperty('--c', color);
    el.joinAnimals.replaceChildren(...ANIMALS.map((animal) => animalButton(animal, color, () => {
      prefs.animal = animal; savePrefs(); renderLook();
    })));
    el.previewFace.innerHTML = FACE;
    el.previewFace.dataset.animal = myAnimal();
    el.previewFace.style.setProperty('--c', color);
  }

  // ---- camera tiles over the picture, top right. They show while anyone's camera is on:
  // the picture for those whose camera is on, their coloured ball for the others, mine
  // mirrored at the bottom. Inside the stage, so they stay in fullscreen.
  const tiles = new Map(); // member id -> { node, video, name }
  const camBig = { id: null }; // whose camera is shown large over the picture
  function makeTile (id, me) {
    const node = document.createElement('div');
    node.className = me ? 'cam me' : 'cam others';
    node.dataset.id = id;
    node.innerHTML = '<video autoplay playsinline muted></video>'
      + `<div class="cam-face face" data-animal="ball">${FACE}</div><span class="cam-name"></span>`;
    const tile = { node, video: node.querySelector('video'), name: node.querySelector('.cam-name'), face: node.querySelector('.face') };
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
      tile.face.dataset.animal = isMe ? myAnimal() : animalOf(m);
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
    renderBig();
  }

  // A click on a camera that is on shows it large over the picture; a click on it, or Esc,
  // makes it small again. It goes when that camera does.
  function showBig (id) { camBig.id = id; renderBig(); }
  function renderBig () {
    const tile = camBig.id ? tiles.get(camBig.id) : null;
    const stream = tile && tile.node.classList.contains('live') ? tile.video.srcObject : null;
    if (!stream) camBig.id = null;
    el.camBig.hidden = !stream;
    if (el.camBigVideo.srcObject !== stream) {
      el.camBigVideo.srcObject = stream;
      if (stream) el.camBigVideo.play().catch(() => {});
    }
    for (const [id, t] of tiles) t.node.classList.toggle('big', id === camBig.id);
    if (!stream) return;
    el.camBig.classList.toggle('me', camBig.id === S.clientId);
    el.camBig.classList.toggle('speaking', tile.node.classList.contains('speaking'));
    el.camBig.style.setProperty('--c', tile.node.style.getPropertyValue('--c'));
    el.camBigName.textContent = tile.name.textContent;
  }
  el.camBig.addEventListener('click', () => showBig(null));

  // The tiles sit in a corner of the picture, top right at first: dragged anywhere, they
  // settle in the nearest corner. On the right they share the side with the drawing toolbar.
  const CORNERS = ['tl', 'tr', 'bl', 'br'];
  function placeCams () {
    const corner = CORNERS.includes(prefs.camCorner) ? prefs.camCorner : 'tr';
    const side = corner[1] === 'l' ? el.sideLeft : el.sideRight;
    if (el.camsBox.parentNode !== side) side.prepend(el.camsBox);
    for (const s of [el.sideLeft, el.sideRight]) {
      const here = !el.camsBox.hidden && s === side;
      s.classList.toggle('at-top', here && corner[0] === 't');
      s.classList.toggle('at-bottom', here && corner[0] === 'b');
    }
    el.camsBox.style.order = corner[0] === 't' ? '-1' : '1'; // above or below the toolbar
    el.camsBox.classList.toggle('small', !!prefs.camsSmall);
    el.camsBox.title = t('cams_move');
    el.camsSizeBtn.title = t(prefs.camsSmall ? 'cams_big' : 'cams_small');
    fitCams();
  }
  // Many tiles on a short picture get smaller instead of being cut off at the bottom.
  function fitCams () {
    el.camsBox.style.removeProperty('--cam-fit');
    const n = el.cams.children.length;
    if (el.camsBox.hidden || !n || getComputedStyle(el.cams).flexDirection !== 'column') return; // a phone: one row
    const side = el.camsBox.parentNode;
    let room = side.clientHeight - 8 * (n - 1);
    for (const other of side.children) if (other !== el.camsBox && other.offsetHeight) room -= other.offsetHeight + 10;
    el.camsBox.style.setProperty('--cam-fit', `${Math.max(64, Math.floor((room / n) * 16 / 9))}px`);
  }
  // A short picture (a phone, upright or on its side): the toolbar as a column would hang over
  // the seek bar, so it lies in a row instead.
  function fitToolbar () {
    const was = el.stage.classList.contains('tools-row');
    el.stage.classList.remove('tools-row');
    const row = !!el.toolbar.offsetHeight && el.toolbar.offsetHeight > el.toolbar.parentNode.clientHeight;
    el.stage.classList.toggle('tools-row', row);
    if (row !== was && S.eraser) renderEraserModes();
  }
  new ResizeObserver(() => { fitToolbar(); fitCams(); }).observe(el.stage);
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

  // A camera that is on: large. Someone without a camera: their volume box, as on their name;
  // a right click gives the volume box for anyone.
  el.cams.addEventListener('click', (e) => {
    if (performance.now() - dragEndedAt < 300) return;
    const node = e.target.closest('.cam');
    if (!node) return;
    if (node.classList.contains('live')) showBig(camBig.id === node.dataset.id ? null : node.dataset.id);
    else if (node.classList.contains('others')) openPeerPop(node.dataset.id, node);
  });
  el.cams.addEventListener('contextmenu', (e) => {
    const node = e.target.closest('.cam.others');
    if (!node) return;
    e.preventDefault();
    openPeerPop(node.dataset.id, node);
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
    if (camBig.id === id) el.camBig.classList.toggle('speaking', on);
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
    const parent = stageFull() ? el.stage : document.body;
    if (el.peerPop.parentNode !== parent) parent.appendChild(el.peerPop);
    el.peerPopName.textContent = t('peer_volume', { name: m.name });
    const vol = prefs.peerVolume[m.name];
    el.peerVol.value = typeof vol === 'number' ? vol : 1;
    const grantable = S.isHost && !m.host;
    el.peerGrant.hidden = !grantable;
    el.peerGrant.textContent = t(m.cohost ? 'grant_revoke' : 'grant_give');
    el.peerGrantHint.hidden = !grantable || !!m.cohost;
    el.peerStopShare.hidden = !(amTrusted() && screen.owner === m.id);
    el.peerKick.hidden = !(S.isHost && !m.host);
    el.peerVol.hidden = !m.joined; // still on the join screen: nothing to hear yet
    renderPeerNet(m.id);
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
  el.peerStopShare.addEventListener('click', () => {
    if (popFor) send({ type: 'share_stop', to: popFor });
    el.peerPop.hidden = true;
  });
  el.peerGrant.addEventListener('click', () => {
    const m = memberById(popFor);
    if (m) send({ type: 'grant', to: m.id, value: !m.cohost });
    el.peerPop.hidden = true;
  });
  el.peerKick.addEventListener('click', () => {
    if (popFor) send({ type: 'kick', to: popFor });
    el.peerPop.hidden = true;
  });
  el.peerVol.addEventListener('input', () => {
    const m = memberById(popFor);
    if (!m) return;
    prefs.peerVolume[m.name] = Number(el.peerVol.value); savePrefs();
    const peer = peers.get(m.id);
    if (peer) applyPeerVolume(peer);
  });

  // ---------------------------------------------------------------- screen sharing
  // One screen at a time covers the film for everyone, and the film pauses meanwhile (the
  // server does that). The host and co-hosts share at once; anyone else asks them first. The
  // capture opens on the click (browsers allow it only then) but goes out only once the server
  // says the screen is mine; the picture and sound go on the connections' third and fourth
  // transceivers, so sharing never needs a new offer.
  const amTrusted = () => S.isHost || !!(memberById(S.clientId) || {}).cohost;
  // Phone browsers cannot capture the screen: on a narrow screen the button gives its room away.
  el.screenGroup.classList.toggle('no-share', !(navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia));
  async function toggleScreen () {
    if (screen.stream) { stopMyScreen(true); return; }
    if (!S.joined) return;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
      toast(t('err_screen_unsupported'), 'error'); return;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: { ideal: 30, max: 30 } }, audio: true });
    } catch (err) {
      if (err && err.name !== 'NotAllowedError' && err.name !== 'AbortError') toast(deviceErrorText('screen', err), 'error');
      return; // cancelled in the browser's picker
    }
    const [track] = stream.getVideoTracks();
    if (track && 'contentHint' in track) track.contentHint = 'motion'; // keep the frame rate for videos
    if (track) track.onended = () => { if (screen.stream === stream) stopMyScreen(true); }; // the browser's own "Stop sharing"
    screen.stream = stream;
    screen.asking = true; // until the server's answer: owner, or waiting in the list
    send({ type: 'share_request' });
    renderScreen();
  }
  function stopMyScreen (tell) {
    const stream = screen.stream;
    screen.stream = null;
    screen.asking = false;
    if (stream) stream.getTracks().forEach((tr) => tr.stop());
    if (tell) send({ type: 'share_stop' });
    for (const peer of peers.values()) applyLocalTracks(peer);
    renderScreen();
  }
  function onScreen (msg) {
    const wasMine = screen.owner === S.clientId;
    const wasWaiting = screen.pending.includes(S.clientId);
    screen.owner = msg.owner || null;
    screen.pending = Array.isArray(msg.pending) ? msg.pending : [];
    const mine = screen.owner === S.clientId;
    const waiting = screen.pending.includes(S.clientId);
    if (mine || waiting) screen.asking = false;
    if (screen.stream && !mine && !waiting && !screen.asking) {
      toast(t(wasMine ? 'screen_taken' : wasWaiting ? 'screen_denied' : 'screen_ended'), wasMine ? 'info' : 'error');
      stopMyScreen(false);
      return;
    }
    for (const peer of peers.values()) applyLocalTracks(peer);
    applyFilmVolume();
    renderScreen();
  }
  function renderScreen () {
    const owner = screen.owner;
    const mine = owner === S.clientId;
    const peer = owner && !mine ? peers.get(owner) : null;
    const stream = (mine ? screen.stream : peer && peer.screenStream) || null;
    if (el.screenVideo.srcObject !== stream) {
      el.screenVideo.srcObject = stream;
      if (stream) el.screenVideo.play().catch(() => {});
    }
    el.screenVideo.hidden = !owner;
    el.stage.classList.toggle('sharing', !!owner);
    const who = owner && memberById(owner);
    el.screenTag.hidden = !owner;
    el.screenTag.textContent = mine ? t('screen_mine') : t('screen_by', { name: who ? who.name : '…' });
    el.screenBtn.classList.toggle('on', !!screen.stream && mine);
    el.screenBtn.classList.toggle('pending', !!screen.stream && !mine);
    el.screenBtn.title = t(screen.stream ? (mine ? 'screen_stop' : 'screen_cancel') : 'screen_share');
    renderShareAsks();
    renderCenter();
  }
  // Cards over the picture: mine while I wait for an answer; for the host and co-hosts, one
  // per request, with the answer buttons.
  function shareCard (text) {
    const card = document.createElement('div');
    card.className = 'share-ask';
    const p = document.createElement('span');
    p.textContent = text;
    card.appendChild(p);
    el.shareAsks.appendChild(card);
    return card;
  }
  function cardButtons (card, buttons) {
    const row = document.createElement('div');
    row.className = 'row';
    for (const [label, cls, onClick] of buttons) {
      const b = document.createElement('button');
      b.type = 'button'; b.className = cls; b.textContent = label;
      b.addEventListener('click', onClick);
      row.appendChild(b);
    }
    card.appendChild(row);
  }
  function renderShareAsks () {
    el.shareAsks.replaceChildren();
    if (screen.stream && screen.owner !== S.clientId) {
      const card = shareCard(t('screen_waiting'));
      card.dataset.mine = '1';
      const preview = document.createElement('video');
      preview.muted = true; preview.autoplay = true; preview.playsInline = true;
      preview.srcObject = screen.stream;
      card.appendChild(preview);
      cardButtons(card, [[t('screen_cancel'), 'ghost', () => stopMyScreen(true)]]);
    }
    if (amTrusted()) {
      const owner = screen.owner && memberById(screen.owner);
      for (const id of screen.pending) {
        const m = memberById(id);
        if (!m || id === S.clientId) continue;
        const card = shareCard(t('screen_ask', { name: m.name }));
        card.dataset.from = id;
        if (owner && owner.id !== id) {
          const note = document.createElement('small');
          note.textContent = t('screen_ask_replaces', { name: owner.id === S.clientId ? t('you') : owner.name });
          card.appendChild(note);
        }
        const answer = (allow) => () => send({ type: 'share_answer', to: id, allow });
        cardButtons(card, [[t('screen_deny'), 'ghost', answer(false)], [t('screen_allow'), 'primary', answer(true)]]);
      }
    }
    retuneCard();
    nextCard(); resumeCard();
    el.shareAsks.hidden = !el.shareAsks.children.length;
  }

  // Funnel's relay is shared by the friends coming over it: more of them joined than the stream
  // was made for, and the server asks the host and co-hosts (once per new number) whether to make
  // it again, lighter, where the room is. It never restarts by itself: everyone's film would stop.
  const RETUNE = { ask: null };
  function onRetune (msg) {
    if (!S.media || !(msg.count > 0)) return;
    RETUNE.ask = { count: msg.count, kbps: msg.kbps, mediaKey: S.media.mediaKey };
    renderShareAsks();
  }
  function keepRetune () {
    const ask = RETUNE.ask;
    if (!ask) return;
    // Another film, or the stream is already made for that many: nothing to ask any more.
    if (!S.media || S.media.mediaKey !== ask.mediaKey || (S.media.funnelViewers || 0) >= ask.count) {
      RETUNE.ask = null;
      renderShareAsks();
    }
  }
  function retuneCard () {
    const ask = RETUNE.ask;
    if (!ask || !amTrusted()) return;
    const card = shareCard(t('retune_ask', { n: ask.count, mbps: ((ask.kbps || 0) / 1000).toFixed(1) }));
    card.dataset.retune = String(ask.count);
    const note = document.createElement('small');
    note.textContent = t('retune_note');
    card.appendChild(note);
    const close = () => { RETUNE.ask = null; renderShareAsks(); };
    cardButtons(card, [[t('retune_later'), 'ghost', close], [t('retune_now'), 'primary', () => {
      close();
      api('/api/media/retune', { json: {} }).catch((err) => toast(errorText(err), 'error'));
    }]]);
  }
  el.screenBtn.addEventListener('click', toggleScreen);

  // The screen menu: the quality I share with, and what the shared picture is doing right now,
  // read from the connection's statistics once a second while the menu is open. The browser says
  // why it sends less than asked (qualityLimitationReason): the link or the processor.
  const screenStats = { timer: null, last: new Map() };
  function renderScreenMenu () {
    el.screenQuality.value = SCREEN_QUALITY[prefs.screenQuality] ? prefs.screenQuality : 'auto';
    el.screenQualityHint.textContent = t(`screen_q_${el.screenQuality.value}_hint`);
  }
  el.screenMenuBtn.addEventListener('click', () => {
    el.screenMenu.hidden = !el.screenMenu.hidden;
    clearInterval(screenStats.timer);
    screenStats.last.clear();
    el.screenStats.textContent = '';
    if (el.screenMenu.hidden) return;
    renderScreenMenu();
    readScreenStats();
    screenStats.timer = setInterval(() => {
      if (el.screenMenu.hidden) { clearInterval(screenStats.timer); return; }
      readScreenStats();
    }, 1000);
  });
  el.screenQuality.addEventListener('change', () => {
    prefs.screenQuality = el.screenQuality.value; savePrefs(); renderScreenMenu();
    if (screen.owner === S.clientId) for (const peer of peers.values()) limitSenders(peer);
  });
  async function readScreenStats () {
    const owner = screen.owner;
    const lines = [];
    if (owner === S.clientId) {
      for (const [id, peer] of peers) {
        if (!peer.screenTx) continue;
        const row = await videoStats(peer.screenTx.sender, 'outbound-rtp', id);
        if (row) lines.push([(memberById(id) || {}).name || '…', row]);
      }
    } else if (owner && peers.get(owner) && peers.get(owner).screenTx) {
      const row = await videoStats(peers.get(owner).screenTx.receiver, 'inbound-rtp', owner);
      if (row) lines.push([t('screen_in'), row]);
    }
    if (el.screenMenu.hidden) return;
    el.screenStats.replaceChildren(...(lines.length ? lines : [[null, null]]).map(([who, row]) => {
      const div = document.createElement('div');
      if (!row) { div.textContent = t(owner ? 'screen_stats_wait' : 'screen_stats_none'); return div; }
      div.textContent = `${who}: ${row.text}`;
      if (row.limit) {
        const lim = document.createElement('span');
        lim.className = 'lim';
        lim.textContent = ` · ${t(`screen_limit_${row.limit}`)}`;
        div.append(lim);
      }
      return div;
    }));
  }
  async function videoStats (end, type, key) {
    let report;
    try { report = await end.getStats(); } catch { return null; }
    let rtp = null;
    report.forEach((s) => { if (s.type === type && s.kind === 'video') rtp = s; });
    if (!rtp || !rtp.frameHeight) return null;
    const bytes = type === 'outbound-rtp' ? rtp.bytesSent : rtp.bytesReceived;
    const prev = screenStats.last.get(key + type);
    screenStats.last.set(key + type, { bytes, at: rtp.timestamp });
    const mbps = prev && rtp.timestamp > prev.at ? (bytes - prev.bytes) * 8 / ((rtp.timestamp - prev.at) * 1000) : null;
    const fps = Math.round(rtp.framesPerSecond || 0);
    const text = `${rtp.frameWidth}×${rtp.frameHeight} · ${t('screen_fps', { n: fps })}` +
      (mbps == null ? '' : ` · ${mbps.toFixed(1).replace('.', t('decimal_sep'))} Mbps`);
    const limit = ['bandwidth', 'cpu'].includes(rtp.qualityLimitationReason) ? rtp.qualityLimitationReason : '';
    return { text, limit };
  }

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
    if (AS.list.length) renderAddonSubs(); // added and deleted ones change their buttons
    renderAi();
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

  // ---- timing: every subtitle has its own, for me only (another version of the film puts the
  // Russian one 2 s early and the Turkish one 1 s late). Kept by the subtitle's id, which the
  // server keeps with the film's subtitles; at most ALIGN_KEEP, the least recently used go.
  // A subtitle's time for a film time: (film − offset) / scale; scale (another frame rate)
  // comes with the alignment panel.
  const ALIGN_KEEP = 300;
  const OFFSET_STEPS = [-500, -100, 100, 500];
  const alignOf = (id) => (id && prefs.align[id]) || { offset: 0, scale: 1 };
  const subTime = (id, film) => { const a = alignOf(id); return (film - a.offset / 1000) / (a.scale || 1); };
  function setAlign (id, change) {
    const next = { ...alignOf(id), ...change, used: Date.now() };
    if (!next.offset && next.scale === 1) delete prefs.align[id]; else prefs.align[id] = next;
    const ids = Object.keys(prefs.align);
    if (ids.length > ALIGN_KEEP) {
      ids.sort((a, b) => (prefs.align[a].used || 0) - (prefs.align[b].used || 0));
      for (const old of ids.slice(0, ids.length - ALIGN_KEEP)) delete prefs.align[old];
    }
    savePrefs();
  }
  // The one offset of before, for both subtitles, becomes the chosen ones' own.
  function adoptOldOffset () {
    if (!prefs.offsetMs || !(S.primary || S.secondary)) return;
    for (const id of new Set([S.primary, S.secondary].filter(Boolean))) {
      if (!prefs.align[id]) setAlign(id, { offset: prefs.offsetMs });
    }
    delete prefs.offsetMs;
    savePrefs();
  }
  const fmtOffset = (ms) => `${ms > 0 ? '+' : ''}${(ms / 1000).toFixed(1).replace('.', t('decimal_sep'))} s`;
  function renderOffsets () {
    adoptOldOffset();
    const slots = [['primary', S.primary], ['secondary', S.secondary !== S.primary ? S.secondary : '']].filter(([, id]) => id);
    el.offsetField.hidden = !slots.length;
    el.offsetRows.replaceChildren(...slots.map(([slot, id]) => {
      const track = S.tracks.find((tr) => tr.id === id);
      const box = document.createElement('div');
      box.dataset.slot = slot;
      const label = document.createElement('div');
      label.className = 'offset-label';
      label.textContent = `${t(slot === 'primary' ? 'subs_primary' : 'subs_secondary')}${track ? ` · ${trackLabel(track)}` : ''}`;
      label.title = label.textContent;
      const row = document.createElement('div');
      row.className = 'offset-row';
      const out = document.createElement('output');
      const show = () => { out.textContent = fmtOffset(alignOf(id).offset); };
      const step = (ms) => {
        const b = document.createElement('button');
        b.type = 'button';
        b.dataset.off = String(ms);
        b.textContent = ms ? `${ms > 0 ? '+' : '−'}${(Math.abs(ms) / 1000).toFixed(1).replace('.', t('decimal_sep'))}` : '0';
        if (!ms) b.className = 'ghost';
        b.addEventListener('click', () => {
          setAlign(id, { offset: ms ? Math.round(alignOf(id).offset + ms) : 0, ...(ms ? {} : { scale: 1 }) });
          show();
        });
        return b;
      };
      row.append(step(OFFSET_STEPS[0]), step(OFFSET_STEPS[1]), out, step(OFFSET_STEPS[2]), step(OFFSET_STEPS[3]), step(0));
      show();
      box.append(label, row);
      return box;
    }));
  }
  el.sizeRange.addEventListener('input', () => { prefs.fontSize = Number(el.sizeRange.value); savePrefs(); renderSubStyle(); });
  el.bottomRange.addEventListener('input', () => { prefs.bottom = Number(el.bottomRange.value); savePrefs(); renderSubStyle(); });

  el.searchForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const languages = el.searchLangs.value.split(/[\s,;]+/).map((s) => s.trim().toLowerCase()).filter(Boolean);
    if (!languages.length) return;
    prefs.searchLangs = el.searchLangs.value; savePrefs();
    const btn = el.searchForm.querySelector('button');
    btn.disabled = true; btn.classList.add('busy');
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
    btn.disabled = true; btn.classList.add('busy');
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
    btn.disabled = true; btn.classList.add('busy');
    el.fileList.hidden = true;
    const started = Date.now();
    const tick = () => { el.torrentWait.textContent = t('torrent_wait', { s: Math.round((Date.now() - started) / 1000) }); };
    tick();
    el.torrentWait.hidden = false;
    const clock = setInterval(tick, 1000);
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
      clearInterval(clock);
      el.torrentWait.hidden = true;
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
    pickFileBtn.disabled = true; pickFileBtn.classList.add('busy');
    try {
      const { path } = await api('/api/media/pick', { json: { title: t('pick_file_title') } });
      if (path) { el.pathInput.value = path; openPath(path); }
    } catch (err) {
      toast(errorText(err), 'error');
    } finally {
      pickFileBtn.disabled = false;
    }
  });

  // ---------------------------------------------------------------- next episode and resuming
  // The server finds the video after this one (the same torrent or folder) and keeps it: the
  // page sees only its label (`media.next`) and asks for it, saying which film it saw, so that
  // two clicks at the end of an episode do not skip one. Near the end a card over the picture
  // offers it to whoever may open it. A film opened again starts paused where it was left: the
  // server says so (`resumed`) and anyone may start it from the beginning.
  const NEXT = { offeredFor: null, dismissed: null, film: null };
  const RESUMED = { ask: null, timer: null };
  const NEXT_OFFER_S = 60;
  const nextBtn = $('#nextBtn');
  function canOpenNext () {
    const n = S.media && S.media.next;
    if (!n || !S.canChangeMedia) return false;
    if (n.kind === 'local') return S.isHost;
    if (n.kind === 'library') return S.canLibrary;
    return true;
  }
  function renderNext () {
    const show = canOpenNext();
    nextBtn.hidden = !show;
    if (show) nextBtn.textContent = t('next_episode', { label: S.media.next.label });
  }
  async function openNext () {
    if (!S.media) return;
    NEXT.dismissed = S.media.mediaKey;
    NEXT.offeredFor = null;
    renderShareAsks();
    try {
      await api('/api/media/next', { json: { after: S.media.mediaKey } });
    } catch (err) {
      if (String(err.message) !== 'next_moved') toast(errorText(err), 'error'); // someone was quicker
    }
  }
  nextBtn.addEventListener('click', openNext);
  // Once a second: the last minute of the film (or its end) offers the next episode. "Not now"
  // holds until another film opens; the resume notice goes once the room has left that point.
  setInterval(() => {
    const m = S.media;
    const film = m ? m.mediaKey : null;
    if (film !== NEXT.film) { NEXT.film = film; NEXT.dismissed = null; }
    if (RESUMED.ask && m && Math.abs(expectedPosition() - RESUMED.ask.at) > 5) { RESUMED.ask = null; renderShareAsks(); }
    const near = !!m && m.duration > 0 && expectedPosition() >= m.duration - Math.min(NEXT_OFFER_S, m.duration / 4);
    const key = near && canOpenNext() && NEXT.dismissed !== m.mediaKey ? m.mediaKey : null;
    if (key !== NEXT.offeredFor) { NEXT.offeredFor = key; renderShareAsks(); }
  }, 1000);
  function nextCard () {
    const m = S.media;
    if (!m || !m.next || NEXT.offeredFor !== m.mediaKey) return;
    const card = shareCard(t('next_offer', { label: m.next.label }));
    card.dataset.next = '1';
    const later = () => { NEXT.dismissed = m.mediaKey; NEXT.offeredFor = null; renderShareAsks(); };
    cardButtons(card, [[t('next_later'), 'ghost', later], [t('next_play'), 'primary', openNext]]);
  }
  function onResumed (msg) {
    RESUMED.ask = { at: Number(msg.at) || 0, mediaKey: msg.mediaKey };
    clearTimeout(RESUMED.timer);
    RESUMED.timer = setTimeout(() => { RESUMED.ask = null; renderShareAsks(); }, 20000);
    renderShareAsks();
  }
  function resumeCard () {
    const ask = RESUMED.ask;
    if (!ask) return;
    if (!S.media || S.media.mediaKey !== ask.mediaKey) { RESUMED.ask = null; return; }
    const card = shareCard(t('resumed_at', { at: fmtTime(ask.at) }));
    card.dataset.resume = '1';
    const close = () => { RESUMED.ask = null; renderShareAsks(); };
    cardButtons(card, [[t('resume_ok'), 'ghost', close], [t('resume_restart'), 'primary', () => { close(); seekTo(0); }]]);
  }

  // ---------------------------------------------------------------- film folders
  // The host's LIBRARY_DIRS. The host and the friends the host trusted (co-hosts) pick a video
  // here; the server takes only a folder number and a path inside that folder.
  const LIBRARY_SHOWN = 200;
  const L = { files: [], dirs: [], loaded: false, loading: false, at: 0 };
  async function loadLibrary () {
    if (L.loading) return;
    L.loading = true;
    try {
      const data = await api('/api/library');
      L.files = data.files || [];
      L.dirs = data.dirs || [];
      L.loaded = true;
      L.at = Date.now();
    } catch {
      L.files = []; L.loaded = false; // the right was taken back meanwhile
    } finally {
      L.loading = false;
    }
    renderLibraryList();
  }
  function renderLibraryBox () {
    el.libraryBox.hidden = !(S.canLibrary && (S.libraryConfigured || S.isHost));
    el.libraryFilter.hidden = !S.libraryConfigured;
    el.libraryList.hidden = !S.libraryConfigured;
    if (!S.libraryConfigured) { el.libraryHint.textContent = t('library_not_set'); el.libraryHint.hidden = false; }
  }
  function renderLibraryList () {
    const q = el.libraryFilter.value.trim().toLocaleLowerCase();
    const items = q ? L.files.filter((f) => f.path.toLocaleLowerCase().includes(q)) : L.files;
    el.libraryList.replaceChildren();
    for (const f of items.slice(0, LIBRARY_SHOWN)) {
      const b = document.createElement('button');
      b.type = 'button';
      b.title = `${L.dirs[f.dir] || ''}/${f.path}`;
      b.textContent = `${f.name} `;
      const where = f.path.includes('/') ? f.path.slice(0, f.path.lastIndexOf('/')) : L.dirs[f.dir] || '';
      const small = document.createElement('small');
      small.textContent = `${where} · ${fmtBytes(f.size)}`;
      b.appendChild(small);
      b.addEventListener('click', () => openLibrary(f));
      el.libraryList.appendChild(b);
    }
    let hint = '';
    if (L.loaded && !L.files.length) hint = t('library_empty');
    else if (q && !items.length) hint = t('library_no_match');
    else if (items.length > LIBRARY_SHOWN) hint = t('library_more', { n: items.length });
    el.libraryHint.textContent = hint;
    el.libraryHint.hidden = !hint;
  }
  async function openLibrary (f) {
    try {
      await api('/api/media/open', { json: { library: { dir: f.dir, path: f.path } } });
    } catch (err) {
      toast(errorText(err), 'error');
      loadLibrary(); // moved or deleted since the list was made
    }
  }
  el.libraryFilter.addEventListener('input', renderLibraryList);
  el.libraryFilter.addEventListener('focus', () => { if (Date.now() - L.at > 30000) loadLibrary(); });

  el.closeMedia.addEventListener('click', async () => {
    try { await api('/api/media/close', { method: 'POST' }); } catch (err) { toast(errorText(err), 'error'); }
  });

  async function pollStatus () {
    try {
      const status = await api('/api/status');
      S.isHost = !!status.isHost;
      const could = S.canLibrary;
      S.canLibrary = !!status.canLibrary;
      S.libraryConfigured = !!status.libraryConfigured;
      S.canChangeMedia = status.canChangeMedia !== false;
      if (S.canLibrary && !could && S.libraryConfigured) loadLibrary();
      S.osEnabled = !!status.osEnabled;
      S.torrent = status.torrent;
      S.downloadThrottled = !!status.downloadThrottled;
      OPEN.torrent = status.openingTorrent || null;
      if (S.opening && !status.opening) { S.opening = false; followOpening(); } // missed the end (reconnect)
      renderLoader();
      if (status.progress) S.progress = status.progress;
      renderMediaPanel();
      if (S.isHost) startShare();
      renderUpdate(status.update);
      if (status.ai) { AI.status = status.ai; renderAi(); }
    } catch { /* offline: the websocket indicator already shows it */ }
  }

  // ---------------------------------------------------------------- share card and settings (host only)
  // The friends' link with its QR code, Tailscale's state and what to do about it, and the
  // settings page that stands in for .env. Saving restarts the server (run.py); pages reconnect
  // by themselves, and this one moves to the new address when the port or the key changed.
  const SH = { data: null, timer: null, settings: null, dirs: [], qrFor: null, key: null };
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  async function loadShare () {
    try { SH.data = await api('/api/share'); } catch { return; }
    renderShare();
    if (!el.settingsOverlay.hidden) renderSpeedTest();
  }
  function startShare () {
    if (SH.timer) return;
    el.shareCard.hidden = false;
    loadShare();
    SH.timer = setInterval(loadShare, 5000);
    // The tray menu's "Settings" opens the room with #settings.
    if (location.hash === '#settings') {
      history.replaceState(null, '', location.pathname + location.search);
      openSettings();
    }
  }

  // The light, the text, and what the host can do about it.
  function shareView (d) {
    const ts = d.tailscale || {};
    const share = d.share || {};
    const funnel = d.connection === 'funnel';
    if (d.connection === 'http') return { light: '', text: t('share_http') };
    if (ts.state === 'missing') return { light: 'bad', text: t('ts_missing'), link: [t('ts_download'), ts.downloadUrl] };
    if (ts.state === 'stopped') return { light: 'bad', text: t('ts_stopped'), open: ts.canOpen, retry: true, hint: t('ts_stopped_hint') };
    if (ts.state === 'login') {
      return { light: 'warn', text: t('ts_login'), link: ts.authUrl ? [t('ts_login_link'), ts.authUrl] : null, open: !ts.authUrl && ts.canOpen, retry: true };
    }
    if (share.state === 'consent') {
      return { light: 'warn', text: t(funnel ? 'share_consent_funnel' : 'share_consent_serve'), link: [t('share_consent_link'), share.url], retry: true, hint: t('share_consent_hint') };
    }
    if (share.state === 'failed') return { light: 'bad', text: t('share_failed'), retry: true, hint: (share.lines || []).join(' · ') };
    if (share.state === 'ok') return { light: 'ok', text: t(funnel ? 'share_ok_funnel' : 'share_ok_serve') };
    if (share.state === 'unknown') return { light: '', text: t('share_unknown') };
    return { light: 'warn', text: t('share_not_started'), retry: true }; // Tailscale came up after the start
  }

  function renderShare () {
    const d = SH.data;
    if (!d) return;
    const v = shareView(d);
    el.tsLight.className = `light ${v.light}`;
    el.tsText.textContent = v.text;
    el.tsLink.hidden = !v.link;
    if (v.link) { el.tsLink.textContent = v.link[0]; el.tsLink.href = v.link[1]; }
    el.tsOpen.hidden = !v.open;
    el.shareRetry.hidden = !(v.retry && d.canRestart);
    el.tsHint.textContent = v.hint || '';
    el.tsHint.hidden = !v.hint;
    const link = d.friendLink || '';
    el.friendRow.hidden = !link;
    if (el.friendLink.value !== link) el.friendLink.value = link;
    el.shareHint.textContent = link ? t(`share_hint_${d.connection}`) : t('share_no_link');
    renderQr(link);
  }

  function renderQr (text) {
    el.qrCanvas.hidden = !text || typeof qrcode !== 'function';
    if (el.qrCanvas.hidden || SH.qrFor === text) return;
    SH.qrFor = text;
    const qr = qrcode(0, 'M');
    qr.addData(text);
    qr.make();
    const quiet = 2; // the white border scanners need
    const n = qr.getModuleCount();
    const scale = Math.ceil(264 / (n + quiet * 2));
    const size = (n + quiet * 2) * scale;
    el.qrCanvas.width = size; el.qrCanvas.height = size;
    const ctx = el.qrCanvas.getContext('2d');
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, size, size);
    ctx.fillStyle = '#000';
    for (let r = 0; r < n; r++) {
      for (let c = 0; c < n; c++) if (qr.isDark(r, c)) ctx.fillRect((c + quiet) * scale, (r + quiet) * scale, scale, scale);
    }
  }

  el.copyLink.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(el.friendLink.value);
    } catch {
      el.friendLink.select();
      document.execCommand('copy');
    }
    toast(t('share_copied'));
  });
  el.tsOpen.addEventListener('click', async () => {
    try {
      await api('/api/tailscale/open', { method: 'POST' });
      toast(t('ts_opening'));
      setTimeout(loadShare, 4000);
    } catch (err) { toast(errorText(err), 'error'); }
  });
  el.shareRetry.addEventListener('click', async () => {
    try {
      await api('/api/share/retry', { method: 'POST' });
      toast(t('restarting'));
    } catch (err) { toast(errorText(err), 'error'); }
  });

  // After a restart with a new port or key, this page's address no longer works: wait for the
  // old server to go and the new one to come, then open the new address.
  async function goWhenUp (url) {
    const up = () => fetch(url, { mode: 'no-cors', cache: 'no-store' }).then(() => true, () => false);
    for (let i = 0; i < 20 && await up(); i++) await sleep(500);
    for (let i = 0; i < 60 && !await up(); i++) await sleep(1000);
    location.href = url;
  }
  function afterSave (res) {
    if (!res.restart) { toast(t('settings_saved_manual'), 'info', 9000); return; }
    toast(t('restarting'));
    const target = new URL(res.localLink);
    const key = new URLSearchParams(target.search).get('k');
    if (target.port !== location.port || key !== SH.key) goWhenUp(res.localLink);
  }

  const radio = (name) => (el.settingsForm.querySelector(`input[name=${name}]:checked`) || {}).value;
  function setRadio (name, value) {
    for (const input of el.settingsForm.querySelectorAll(`input[name=${name}]`)) input.checked = input.value === value;
  }

  async function openSettings () {
    let data;
    try { data = await api('/api/settings'); } catch (err) { toast(errorText(err), 'error'); return; }
    SH.settings = data;
    renderStorage();
    renderVersion(data);
    SH.key = new URLSearchParams(new URL(SH.data ? SH.data.localLink : location.href).search).get('k');
    const v = data.values;
    const cur = data.current;
    const locked = new Set(data.locked);
    // A choice set in .env shows what runs now, read-only.
    const pick = (key, current) => (locked.has(key) ? current : v[key]);
    setRadio('connection', pick('connection', cur.connection));
    setRadio('quality', pick('quality', cur.maxCopyKbps ? 'manual' : 'original'));
    el.qualityMbps.value = locked.has('quality') && cur.maxCopyKbps ? cur.maxCopyKbps / 1000 : v.qualityMbps;
    SH.dirs = [...pick('libraryDirs', cur.libraryDirs)];
    setRadio('mediaControl', pick('mediaControl', cur.mediaControl));
    el.osApiKey.value = pick('osApiKey', cur.osApiKey);
    el.osUsername.value = pick('osUsername', cur.osUsername);
    el.osPassword.value = '';
    el.osPassword.placeholder = v.hasPassword ? t('os_password_saved') : '';
    el.port.value = pick('port', cur.port);
    el.torrentUploadLimit.value = pick('torrentUploadLimit', cur.torrentUploadLimit);
    el.iceServers.value = pick('iceServers', cur.iceServers);
    // Two groups: language models, and machine translation services (no model, line by line).
    const presets = data.aiPresets || {};
    const group = (label, ids) => {
      const node = document.createElement('optgroup');
      node.label = label;
      node.append(...ids.map((id) => Object.assign(document.createElement('option'), {
        value: id,
        textContent: id === 'custom' ? t('ai_custom') : presets[id].label + (presets[id].account ? ` · ${t('ai_needs_account')}` : ''),
      })));
      return node;
    };
    const ids = Object.keys(presets);
    el.aiProvider.replaceChildren(
      group(t('ai_group_llm'), ids.filter((id) => !AI_SERVICES.includes(presets[id].protocol))),
      group(t('ai_group_mt'), ids.filter((id) => AI_SERVICES.includes(presets[id].protocol))));
    el.aiProvider.value = pick('aiProvider', cur.aiProvider);
    fillAiPreset();
    if (locked.has('aiProtocol') || v.aiProtocol) el.aiProtocol.value = pick('aiProtocol', cur.aiProtocol) || el.aiProtocol.value;
    if (locked.has('aiBaseUrl') || v.aiBaseUrl) el.aiBaseUrl.value = pick('aiBaseUrl', cur.aiBaseUrl);
    if (locked.has('aiModel') || v.aiModel) el.aiModel.value = pick('aiModel', cur.aiModel);
    el.aiApiKey.value = '';
    setRadio('aiTranslate', pick('aiTranslate', cur.aiTranslate));
    for (const node of el.settingsForm.querySelectorAll('[data-key]')) {
      const isLocked = locked.has(node.dataset.key);
      for (const input of node.querySelectorAll('input, button, select')) input.disabled = isLocked;
      let note = node.querySelector(':scope > .lock-note');
      if (isLocked && !note) {
        note = document.createElement('p');
        note.className = 'hint lock-note';
        node.appendChild(note);
      }
      if (note) { note.hidden = !isLocked; note.textContent = t('set_locked'); }
    }
    el.newKeyBtn.disabled = data.keyLocked;
    el.settingsWarn.textContent = t(!data.canRestart ? 'settings_no_restart' : data.mediaOpen ? 'settings_restart_media' : 'settings_restart');
    el.settingsWarn.hidden = false;
    renderDirs();
    renderQuality();
    renderAiKey();
    renderSpeedTest();
    el.settingsOverlay.hidden = false;
  }
  function closeSettings () { el.settingsOverlay.hidden = true; }

  // ---- the Funnel speed test: the server downloads from its own public link, through the relay
  const SPEED_HEADROOM = 1.2; // a film needs a little more than its bitrate to stay ahead
  function renderSpeedTest () {
    const d = SH.data || {};
    const funnel = d.connection === 'funnel' && /^https:/.test(d.friendLink || '');
    el.speedTestBtn.hidden = !funnel;
    if (!el.speedTestBtn.classList.contains('busy')) {
      el.speedTestOut.textContent = t(funnel ? 'speedtest_hint' : 'speedtest_needs_funnel');
      el.speedTestOut.classList.remove('slow');
    }
  }
  el.speedTestBtn.addEventListener('click', async () => {
    el.speedTestBtn.disabled = true; el.speedTestBtn.classList.add('busy');
    el.speedTestOut.textContent = t('speedtest_running');
    try {
      const r = await api('/api/speedtest/run', { method: 'POST' });
      const film = (n) => fmtMbps(r.mbps / n / SPEED_HEADROOM);
      el.speedTestOut.textContent = t('speedtest_result', { mbps: fmtMbps(r.mbps), one: film(1), two: film(2) }) +
        (r.relay ? '' : ` ${t('speedtest_direct')}`);
    } catch (err) {
      el.speedTestOut.textContent = errorText(err);
    }
    el.speedTestBtn.disabled = false; el.speedTestBtn.classList.remove('busy');
  });

  function renderQuality () {
    el.qualityMbps.closest('.field').hidden = radio('quality') !== 'manual';
  }
  function renderDirs () {
    const locked = !!SH.settings && SH.settings.locked.includes('libraryDirs');
    el.dirList.replaceChildren();
    if (!SH.dirs.length) {
      const li = document.createElement('li');
      li.className = 'hint';
      li.textContent = t('library_dirs_empty');
      el.dirList.appendChild(li);
    }
    for (const dir of SH.dirs) {
      const li = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = dir;
      const del = document.createElement('button');
      del.type = 'button'; del.className = 'ghost'; del.textContent = t('delete'); del.disabled = locked;
      del.addEventListener('click', () => { SH.dirs = SH.dirs.filter((d) => d !== dir); renderDirs(); });
      li.append(name, del);
      el.dirList.appendChild(li);
    }
  }
  function addDir (path) {
    const dir = (path || '').trim().replace(/^["']+|["']+$/g, '');
    if (dir && !SH.dirs.includes(dir)) SH.dirs.push(dir);
    renderDirs();
  }

  function settingsBody () {
    const body = {
      connection: radio('connection'), quality: radio('quality'), qualityMbps: Number(el.qualityMbps.value) || 8,
      libraryDirs: SH.dirs, mediaControl: radio('mediaControl'), port: Number(el.port.value) || 0,
      torrentUploadLimit: Math.max(0, Number(el.torrentUploadLimit.value) || 0), iceServers: el.iceServers.value,
      osApiKey: el.osApiKey.value.trim(), osUsername: el.osUsername.value.trim(),
    };
    if (el.osPassword.value) body.osPassword = el.osPassword.value;
    else if (!body.osUsername) body.osPassword = ''; // no account: forget its password too
    return { ...body, ...aiBody(), aiTranslate: radio('aiTranslate') };
  }

  // ---- the AI fields: a provider is a protocol, an address and a suggested model; choosing
  // one fills them in. The key is never sent back to the page: an empty field keeps the saved
  // one, unless the provider changed (a key belongs to its provider).
  const AI_SERVICES = ['deepl', 'microsoft', 'google', 'libretranslate', 'mymemory'];
  const aiPreset = () => (SH.settings.aiPresets || {})[el.aiProvider.value] || { protocol: 'openai', baseUrl: '', model: '' };
  function fillAiPreset () {
    const preset = aiPreset();
    if (el.aiProvider.value !== 'custom') el.aiProtocol.value = preset.protocol;
    el.aiBaseUrl.value = preset.baseUrl;
    el.aiBaseUrl.placeholder = preset.baseUrl || (el.aiProtocol.value === 'anthropic' ? 'https://api.anthropic.com' : 'https://…/v1');
    el.aiModel.value = preset.model;
    el.aiModels.replaceChildren();
    el.aiTestOut.hidden = true;
    renderAiKey();
  }
  // The fields follow the protocol: a service has no model (Microsoft takes its Azure region
  // there), MyMemory takes an e-mail address instead of a key.
  function renderAiKey () {
    const v = SH.settings.values;
    const protocol = el.aiProtocol.value;
    const service = AI_SERVICES.includes(protocol);
    const same = el.aiProvider.value === v.aiProvider;
    const local = /^https?:\/\/(localhost|127\.0\.0\.1)[:/]/.test(el.aiBaseUrl.value);
    const email = protocol === 'mymemory';
    el.aiKeyLabel.textContent = t(email ? 'ai_email' : 'ai_api_key');
    el.aiApiKey.type = email ? 'email' : 'password';
    el.aiApiKey.placeholder = same && v.hasAiKey ? t('ai_key_saved') : local ? t('ai_key_local')
      : email || protocol === 'libretranslate' ? t('ai_key_optional') : '';
    el.aiModelLabel.textContent = t(protocol === 'microsoft' ? 'ai_region' : service ? 'ai_try_label' : 'ai_model');
    el.aiModel.hidden = service && protocol !== 'microsoft';
    el.aiModel.placeholder = protocol === 'microsoft' ? 'westeurope' : '';
    el.aiModelsBtn.hidden = service;
    const note = `ai_note_${el.aiProvider.value}`;
    el.aiNote.hidden = !(I18N.en[note]);
    el.aiNote.textContent = el.aiNote.hidden ? '' : t(note);
    const locked = SH.settings.locked.includes('aiProtocol');
    el.aiProtocol.disabled = locked || el.aiProvider.value !== 'custom';
  }
  function aiBody () {
    const preset = aiPreset();
    const body = {
      aiProvider: el.aiProvider.value,
      aiProtocol: el.aiProvider.value === 'custom' ? el.aiProtocol.value : '',
      aiBaseUrl: el.aiBaseUrl.value.trim() === preset.baseUrl ? '' : el.aiBaseUrl.value.trim(),
      aiModel: el.aiModel.value.trim() === preset.model ? '' : el.aiModel.value.trim(),
    };
    if (el.aiApiKey.value) body.aiApiKey = el.aiApiKey.value.trim();
    else if (el.aiProvider.value !== SH.settings.values.aiProvider) body.aiApiKey = '';
    return body;
  }
  async function aiCall (path, button, show) {
    button.disabled = true; button.classList.add('busy');
    el.aiTestOut.hidden = false;
    el.aiTestOut.textContent = '…';
    try {
      show(await api(path, { json: { ...aiBody(), aiModel: el.aiModel.value.trim(), lang: prefs.uiLang } }));
    } catch (err) {
      el.aiTestOut.textContent = errorText(err);
    } finally {
      button.disabled = false;
    }
  }
  el.aiProvider.addEventListener('change', fillAiPreset);
  el.aiProtocol.addEventListener('change', renderAiKey);
  el.aiBaseUrl.addEventListener('input', renderAiKey);
  el.aiModelsBtn.addEventListener('click', () => aiCall('/api/settings/ai-models', el.aiModelsBtn, (res) => {
    el.aiModels.replaceChildren(...res.models.map((id) => Object.assign(document.createElement('option'), { value: id })));
    el.aiTestOut.textContent = t('ai_models_found', { n: res.models.length });
    if (!el.aiModel.value && res.models.length) el.aiModel.value = res.models[0];
  }));
  el.aiTestBtn.addEventListener('click', () => aiCall('/api/settings/ai-test', el.aiTestBtn, (res) => {
    el.aiTestOut.textContent = t('ai_test_ok', { text: res.lines.join(' / ') });
  }));
  function settingsError (err) {
    const raw = String(err && err.message ? err.message : err);
    if (raw.startsWith('library_dir_missing:')) return t('err_library_dir_missing', { path: raw.slice(20).trim() });
    if (raw.startsWith('[')) return t('err_settings_invalid'); // a value out of range
    return errorText(err);
  }

  el.settingsBtn.addEventListener('click', openSettings);
  el.settingsClose.addEventListener('click', closeSettings);
  el.settingsCancel.addEventListener('click', closeSettings);
  el.settingsOverlay.addEventListener('mousedown', (e) => { if (e.target === el.settingsOverlay) closeSettings(); });
  el.settingsOverlay.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeSettings(); });
  el.settingsForm.addEventListener('change', (e) => { if (e.target.name === 'quality') renderQuality(); });
  el.dirAdd.addEventListener('click', () => { addDir(el.dirInput.value); el.dirInput.value = ''; });
  el.dirInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); addDir(el.dirInput.value); el.dirInput.value = ''; }
  });
  el.dirPick.addEventListener('click', async () => {
    try {
      const res = await api('/api/settings/pick-folder', { json: { title: t('pick_folder_title') } });
      if (res.path) addDir(res.path);
    } catch (err) { toast(errorText(err), 'error'); }
  });
  el.settingsForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    el.settingsSave.disabled = true; el.settingsSave.classList.add('busy');
    try {
      const res = await api('/api/settings', { json: settingsBody() });
      closeSettings();
      afterSave(res);
    } catch (err) {
      toast(settingsError(err), 'error');
    } finally {
      el.settingsSave.disabled = false;
    }
  });
  // ---- storage: the downloaded torrents pile up film after film; the film playing stays.
  const STORE = { free: 0 };
  async function renderStorage () {
    el.storageInfo.textContent = '…';
    el.storageClean.disabled = true;
    try {
      const s = await api('/api/torrents/storage');
      STORE.free = Math.max(0, s.total - s.kept);
      el.storageInfo.textContent = s.kept
        ? t('set_storage_size_kept', { size: fmtBytes(s.total), kept: fmtBytes(s.kept) })
        : t('set_storage_size', { size: fmtBytes(s.total) });
      el.storageClean.disabled = STORE.free <= 0;
    } catch (err) {
      el.storageInfo.textContent = errorText(err);
    }
  }
  el.storageClean.addEventListener('click', async () => {
    if (!confirm(t('set_storage_confirm', { size: fmtBytes(STORE.free) }))) return;
    el.storageClean.disabled = true;
    el.storageClean.classList.add('busy');
    try {
      const res = await api('/api/torrents/cleanup', { method: 'POST' });
      toast(t(res.failed ? 'set_storage_partly' : 'set_storage_done', { size: fmtBytes(res.freed), n: res.failed }),
        res.failed ? 'error' : 'info');
    } catch (err) {
      toast(errorText(err), 'error');
    } finally {
      el.storageClean.classList.remove('busy');
      renderStorage();
    }
  });

  el.newKeyBtn.addEventListener('click', async () => {
    if (!confirm(t('set_new_key_confirm'))) return;
    try {
      const res = await api('/api/settings/key', { method: 'POST' });
      closeSettings();
      afterSave(res);
    } catch (err) { toast(errorText(err), 'error'); }
  });

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
    el.browseStatus.classList.add('loading');
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
      if (seq === B.seq) { el.browseStatus.textContent = ''; el.browseStatus.classList.remove('loading'); toast(errorText(err), 'error'); }
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
    el.browseStatus.classList.remove('loading');
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
    li.className = text === t('browse_loading') ? 'msg loading' : 'msg';
    li.textContent = text;
    el.streamList.replaceChildren(li);
  }

  // A title can have dozens of sources from several add-ons: they come in one list that can be
  // narrowed by text, add-on and picture quality, and shown a page at a time.
  const STREAM_PAGE = 15;
  const QUALITIES = [ // read from the source's name and description, whatever the add-on
    ['4k', /\b(2160p|4k|uhd)\b/i], ['1080p', /\b1080[pi]\b/i], ['720p', /\b720p\b/i], ['sd', /\b(576p|480p|360p|sd)\b/i],
  ];
  const ST = { list: [], name: '', shown: STREAM_PAGE, quality: '', addon: '' };
  const streamText = (s) => `${s.addon} ${s.name} ${s.detail}`;
  const streamQuality = (s) => (QUALITIES.find(([, re]) => re.test(streamText(s))) || ['other'])[0];

  async function loadStreams (type, id, name) {
    const seq = ++B.streamSeq;
    el.streamTools.hidden = true;
    el.streamMore.hidden = true;
    el.streamCount.textContent = '';
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
    Object.assign(ST, { list: streams.map((s) => ({ ...s, quality: streamQuality(s) })), name, shown: STREAM_PAGE, quality: '', addon: '' });
    el.streamFilter.value = '';
    renderStreamTools();
    renderStreams();
  }

  function renderStreamTools () {
    const addons = [...new Set(ST.list.map((s) => s.addon))];
    el.streamAddon.replaceChildren();
    for (const [value, label] of [['', t('streams_all_addons')], ...addons.map((a) => [a, a])]) {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = value ? `${label} (${ST.list.filter((s) => s.addon === value).length})` : label;
      el.streamAddon.appendChild(option);
    }
    el.streamAddon.value = ST.addon;
    el.streamAddon.hidden = addons.length < 2;
    el.streamQuality.replaceChildren();
    const present = [...QUALITIES.map(([q]) => q), 'other'].filter((q) => ST.list.some((s) => s.quality === q));
    for (const q of present.length > 1 ? ['', ...present] : []) {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = `chip${ST.quality === q ? ' on' : ''}`;
      chip.textContent = q ? `${t(`quality_${q}`)} (${ST.list.filter((s) => s.quality === q).length})` : t('quality_all');
      chip.addEventListener('click', () => { ST.quality = q; ST.shown = STREAM_PAGE; renderStreamTools(); renderStreams(); });
      el.streamQuality.appendChild(chip);
    }
    el.streamTools.hidden = ST.list.length <= 5;
  }

  function filteredStreams () {
    const words = el.streamFilter.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    return ST.list.filter((s) => (!ST.addon || s.addon === ST.addon) && (!ST.quality || s.quality === ST.quality) &&
      words.every((w) => streamText(s).toLocaleLowerCase().includes(w)));
  }

  function renderStreams () {
    const items = filteredStreams();
    if (!items.length) streamMessage(t('streams_no_match'));
    else el.streamList.replaceChildren(...items.slice(0, ST.shown).map(streamItem));
    const shown = Math.min(ST.shown, items.length);
    el.streamCount.textContent = t('streams_count', { shown, total: items.length });
    el.streamMore.hidden = items.length <= ST.shown;
    el.streamMore.textContent = t('streams_more', { n: Math.min(STREAM_PAGE, items.length - ST.shown) });
  }

  function streamItem (s) {
    const li = document.createElement('li');
    const what = document.createElement('span'); what.className = 'what';
    const head = document.createElement('b'); head.textContent = [s.addon, s.name].filter(Boolean).join(' · ');
    const detail = document.createElement('span'); detail.textContent = s.detail;
    what.append(head, detail);
    const kind = document.createElement('span'); kind.className = 'kind';
    kind.textContent = t(s.kind === 'torrent' ? 'stream_torrent' : 'stream_url');
    const open = document.createElement('button'); open.type = 'button'; open.className = 'primary';
    open.textContent = t('stream_open');
    if (!S.canChangeMedia) { open.disabled = true; open.title = t('media_trusted_only'); }
    open.addEventListener('click', async () => {
      open.disabled = true; open.classList.add('busy');
      try {
        await api('/api/media/open', { json: { stream: s.ref } });
        toast(t('stream_opening', { name: ST.name }));
        el.stageWrap.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } catch (err) {
        toast(errorText(err), 'error');
      } finally {
        open.disabled = false;
      }
    });
    li.append(what, kind, open);
    return li;
  }

  el.streamFilter.addEventListener('input', () => { ST.shown = STREAM_PAGE; renderStreams(); });
  el.streamAddon.addEventListener('change', () => { ST.addon = el.streamAddon.value; ST.shown = STREAM_PAGE; renderStreams(); });
  el.streamMore.addEventListener('click', () => { ST.shown += STREAM_PAGE; renderStreams(); });

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
    const btn = el.addonForm.querySelector('button[type="submit"]');
    btn.disabled = true; btn.classList.add('busy');
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
  el.addonsStremio.addEventListener('click', async () => {
    if (!B.canEdit || !confirm(t('addons_stremio_confirm'))) return;
    el.addonsStremio.disabled = true; el.addonsStremio.classList.add('busy');
    try {
      const { added, found } = await api('/api/addons/stremio', { method: 'POST' });
      if (added.length) toast(t('addons_stremio_added', { n: added.length }));
      else toast(t(found ? 'addons_stremio_none' : 'addons_stremio_empty'));
      await loadAddons();
      loadCatalog(true);
    } catch (err) {
      toast(errorText(err), 'error');
    } finally {
      el.addonsStremio.disabled = false;
    }
  });

  // ---- subtitles the add-ons offer for the open film (found by its id and file hash)
  // There can be hundreds, in every language: the viewer's own languages come first, and a
  // page at a time.
  const SUB_PAGE = 8;
  const AS = { list: [], shown: SUB_PAGE, lang: '' };
  const myLangs = () => new Set([prefs.primaryLang, prefs.secondaryLang, ...String(prefs.searchLangs || '').split(',')]
    .map((l) => String(l || '').trim().toLowerCase()).filter(Boolean));

  el.addonSubsBtn.addEventListener('click', async () => {
    el.addonSubsBtn.disabled = true; el.addonSubsBtn.classList.add('busy');
    resetAddonSubs();
    try {
      const { subtitles } = await api('/api/addons/subtitles');
      AS.list = subtitles;
      const mine = myLangs();
      AS.lang = subtitles.some((s) => mine.has(s.lang)) ? 'mine' : '';
      renderAddonSubs();
    } catch (err) {
      toast(errorText(err), 'error');
    } finally {
      el.addonSubsBtn.disabled = false;
    }
  });
  function resetAddonSubs () {
    Object.assign(AS, { list: [], shown: SUB_PAGE, lang: '' });
    el.addonSubsList.replaceChildren();
    el.addonSubsLang.hidden = true;
    el.addonSubsMore.hidden = true;
  }
  function renderAddonSubs () {
    const mine = myLangs();
    const counts = new Map();
    for (const s of AS.list) counts.set(s.lang, (counts.get(s.lang) || 0) + 1);
    el.addonSubsLang.replaceChildren();
    const options = [['', `${t('subs_langs_all')} (${AS.list.length})`]];
    if ([...counts.keys()].some((l) => mine.has(l))) options.unshift(['mine', t('subs_langs_mine')]);
    for (const [lang, n] of [...counts].sort((a, b) => b[1] - a[1])) options.push([lang, `${langName(lang)} (${n})`]);
    for (const [value, label] of options) {
      const option = document.createElement('option');
      option.value = value; option.textContent = label;
      el.addonSubsLang.appendChild(option);
    }
    el.addonSubsLang.value = AS.lang;
    el.addonSubsLang.hidden = counts.size < 2;
    const items = AS.list.filter((s) => !AS.lang || (AS.lang === 'mine' ? mine.has(s.lang) : s.lang === AS.lang));
    if (!items.length) {
      const li = document.createElement('li'); li.textContent = t('subs_addons_none');
      el.addonSubsList.replaceChildren(li);
    } else {
      el.addonSubsList.replaceChildren(...items.slice(0, AS.shown).map(addonSubItem));
    }
    el.addonSubsMore.hidden = items.length <= AS.shown;
    el.addonSubsMore.textContent = t('streams_more', { n: Math.min(SUB_PAGE, items.length - AS.shown) });
  }
  el.addonSubsLang.addEventListener('change', () => { AS.lang = el.addonSubsLang.value; AS.shown = SUB_PAGE; renderAddonSubs(); });
  el.addonSubsMore.addEventListener('click', () => { AS.shown += SUB_PAGE; renderAddonSubs(); });
  function addonSubItem (sub) {
    const li = document.createElement('li');
    const lang = document.createElement('span'); lang.className = 'lang'; lang.textContent = sub.lang.toUpperCase();
    const label = document.createElement('span'); label.className = 'label';
    label.textContent = `${langName(sub.lang)} · ${sub.label || sub.addon}`;
    li.append(lang, label);
    const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'ghost';
    // Already in the room (a track has its key): one click makes it the main subtitle. Deleted
    // from the room: back to "Add", since the list follows the tracks.
    const track = S.tracks.find((tr) => tr.key === sub.key);
    if (track && track.id === S.primary) {
      btn.textContent = t('subs_addons_on');
      btn.disabled = true; // a state, not a wait: no spinner
      li.classList.add('on');
    } else if (track) {
      btn.textContent = t('subs_addons_use');
      btn.addEventListener('click', () => selectTrack('primary', track.id));
    } else {
      btn.textContent = t('addons_add');
      btn.addEventListener('click', async () => {
        btn.disabled = true; btn.classList.add('busy');
        try {
          const added = await api('/api/addons/subtitles', { json: { ref: sub.ref } });
          toast(t('uploaded', { label: added.label }));
          // Trying another one in the same language (the last was out of step, say) switches to it.
          const current = S.tracks.find((tr) => tr.id === S.primary);
          if (!current || current.lang === added.lang) {
            if (!S.tracks.some((tr) => tr.id === added.id)) S.tracks = [...S.tracks, added]; // before the broadcast
            selectTrack('primary', added.id);
          }
        } catch (err) {
          btn.disabled = false;
          toast(errorText(err), 'error');
        }
      });
    }
    li.appendChild(btn);
    return li;
  }

  // ---- translation with a language model (server/translate.py), when no subtitle in the
  // wanted language exists: a subtitle in the room (usually the English one) goes to the
  // provider the host set up, and the result joins everyone's list.
  const AI = { status: { enabled: false, allowed: false, provider: '', busy: null }, asked: null, toast: null };
  const AI_LANGS = ['tr', 'en', 'ru', 'es', 'de', 'fr', 'it', 'pt-br', 'uk', 'ar', 'fa', 'az', 'ja', 'ko', 'zh', 'nl', 'pl'];
  // The subtitle to translate from: English matched by the file's hash first, then any English,
  // then anything matched by hash; translations come last.
  function aiSources (target) {
    const score = (tr) => (tr.source === 'ai' ? 4 : 0) + (tr.lang === 'en' ? 0 : 2) + (tr.hashMatch ? 0 : 1);
    return S.tracks.filter((tr) => tr.lang !== target).sort((a, b) => score(a) - score(b));
  }
  function fillSelect (select, options, wanted) {
    const key = options.map(([value, label]) => `${value}\u0000${label}`).join('\u0001');
    if (select.dataset.options !== key) {
      select.dataset.options = key;
      select.replaceChildren(...options.map(([value, label]) => {
        const option = document.createElement('option');
        option.value = value; option.textContent = label;
        return option;
      }));
    }
    if (options.some(([value]) => value === wanted)) select.value = wanted;
  }
  function renderAi () {
    const st = AI.status;
    el.aiBox.hidden = !S.media;
    const target = el.aiLang.value || prefs.primaryLang || prefs.uiLang;
    const langs = [...new Set([...AI_LANGS, ...myLangs()])];
    fillSelect(el.aiLang, langs.map((code) => [code, langName(code)]), target);
    const sources = aiSources(el.aiLang.value);
    fillSelect(el.aiSource, sources.map((tr) => [tr.id, trackLabel(tr)]), el.aiSource.value || (sources[0] || {}).id);
    let hint;
    if (!st.enabled) hint = t(S.isHost ? 'ai_off_host' : 'ai_off_guest');
    else if (!st.allowed) hint = t('ai_not_allowed');
    else if (!sources.length) hint = t('ai_no_source');
    else hint = t('ai_hint', { provider: st.provider });
    el.aiForm.hidden = !st.enabled || !st.allowed || !sources.length;
    el.aiSettings.hidden = st.enabled || !S.isHost;
    el.aiHint.textContent = hint;
    el.aiGo.disabled = !!st.busy;
  }
  el.aiLang.addEventListener('change', renderAi);
  el.aiSettings.addEventListener('click', openSettings);
  el.aiGo.addEventListener('click', async () => {
    const lang = el.aiLang.value;
    el.aiGo.disabled = true; el.aiGo.classList.add('busy');
    try {
      const res = await api('/api/subtitles/translate', { json: { source: el.aiSource.value, lang } });
      if (res.cached) {
        selectTrack('primary', res.track);
        toast(t('ai_already'));
      } else {
        AI.asked = lang; // made the main subtitle here when it is ready
        AI.status.busy = lang;
      }
    } catch (err) {
      toast(errorText(err), 'error');
    }
    renderAi();
  });
  // One notice follows the translation for everyone, like the steps of opening a film.
  function onAiStatus (msg, params) {
    const lang = langName(params.lang || '');
    let text;
    if (msg.key === 'translating') {
      text = params.total ? t('status_translating', { lang, done: params.done, total: params.total })
        : t('status_translating_start', { lang });
      AI.status.busy = params.lang;
    } else if (msg.key === 'translated') {
      text = t('status_translated', { label: `${lang} · ${params.label}` });
      if (params.missing) text += ` ${t('ai_missing', { n: params.missing })}`;
    } else {
      const key = `err_${params.code}`;
      const known = (I18N[prefs.uiLang] || {})[key] || I18N.en[key];
      text = t('status_translate_failed', { lang, detail: known ? t(key) : params.detail });
    }
    if (!AI.toast || !AI.toast.isConnected) AI.toast = toast(text, 'info', 600000);
    AI.toast.textContent = text;
    if (msg.key !== 'translating') {
      AI.toast.className = `toast ${msg.level === 'error' ? 'error' : 'info'}`;
      const done = AI.toast;
      AI.toast = null;
      setTimeout(() => done.remove(), msg.level === 'error' ? 12000 : 5000);
      AI.status.busy = null;
      if (msg.key === 'translated' && AI.asked === params.lang) selectTrack('primary', params.track);
      if (AI.asked === params.lang) AI.asked = null;
    }
    renderAi();
  }

  // ---------------------------------------------------------------- text chat
  // On a wide screen the chat is a column right of the film, on a phone held upright a box
  // under it; open unless closed (kept in prefs). In fullscreen, in the always-on-top window
  // and in between (a tablet, a phone on its side) the same panel
  // moves over the bottom left of the picture instead, closed until asked for. The server
  // keeps the last messages for those who join later and sends each one back to its sender
  // too, so everyone sees them in the same order. Messages nobody sees (the panel is closed,
  // or the page is scrolled away from it) peek over the picture for a few seconds and count
  // on the button.
  const CHAT = { overlay: false, unread: 0, messages: [] };
  const CHAT_KEEP = 100; // as many as the server keeps
  const CHAT_PEEK_MS = 7000;
  const CHAT_PEEK_MAX = 3;
  // Where the column fits: beside the film on a wide screen, under it on a phone held upright.
  const dockScreen = window.matchMedia('(min-width: 1100px), (max-width: 640px)');

  // Web addresses in a message become links (new tab, no referrer); everything else stays plain
  // text, built node by node, never as HTML. Only http and https: "javascript:" stays text.
  const LINK_RE = /\bhttps?:\/\/[^\s<>"]+/gi;
  const LINK_SHOW = 60;
  function chatLink (raw) {
    let end = raw.replace(/[.,;:!?'"]+$/, '');
    if (end.endsWith(')') && !end.includes('(')) end = end.slice(0, -1); // "(see https://…)"
    let url;
    try { url = new URL(end); } catch { return null; }
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
    const a = document.createElement('a');
    a.className = 'chat-link';
    a.href = url.href;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.title = url.href;
    a.textContent = end.length > LINK_SHOW ? end.slice(0, LINK_SHOW - 16) + '…' + end.slice(-15) : end;
    return { a, used: end.length };
  }
  function chatPieces (textIn) {
    const out = [];
    let at = 0;
    for (const m of String(textIn).matchAll(LINK_RE)) {
      const link = chatLink(m[0]);
      if (!link) continue;
      if (m.index > at) out.push(textIn.slice(at, m.index));
      out.push(link.a);
      at = m.index + link.used;
    }
    if (at < textIn.length) out.push(textIn.slice(at));
    return out;
  }
  function chatLine (msg) {
    const li = document.createElement('li');
    li.className = 'chat-msg';
    li.style.setProperty('--c', msg.color || '#ffffff');
    const name = document.createElement('b');
    name.textContent = msg.name;
    const text = document.createElement('span');
    text.append(...chatPieces(msg.text));
    li.append(name, text);
    li.title = new Date(msg.ts).toLocaleTimeString(prefs.uiLang, { hour: '2-digit', minute: '2-digit' });
    return li;
  }
  function setChatHistory (messages) {
    CHAT.messages = Array.isArray(messages) ? messages.slice(-CHAT_KEEP) : [];
    el.chatLog.replaceChildren(...CHAT.messages.map(chatLine));
    el.chatLog.scrollTop = el.chatLog.scrollHeight;
  }
  const chatDocked = () => el.chatBox.parentNode === el.chatDock;
  const chatOpen = () => (chatDocked() ? prefs.chatDock : CHAT.overlay);
  // In sight: the column while its part of the page is on screen, the panel unless the film
  // is in the corner box (where it is hidden); neither while the tab is behind another one.
  const chatSeen = () => chatOpen() && (!!PIP.win || !document.hidden) &&
    (chatDocked() ? MINI.visible : !el.stage.classList.contains('mini'));
  const PAGE_TITLE = document.title;

  function placeChat () {
    const parent = dockScreen.matches && !stageFull() && !PIP.win ? el.chatDock : el.stage;
    if (el.chatBox.parentNode !== parent) parent.appendChild(el.chatBox);
    renderChat();
  }
  function renderChat () {
    const open = chatOpen();
    const docked = chatDocked();
    el.watch.classList.toggle('docked', docked && open);
    el.chatBox.hidden = !open;
    el.stage.classList.toggle('chat-open', open && !docked);
    if (chatSeen() && CHAT.unread) {
      CHAT.unread = 0;
      el.chatPeek.replaceChildren();
      el.chatLog.scrollTop = el.chatLog.scrollHeight;
    }
    el.chatBtn.classList.toggle('on', open);
    el.chatBadge.hidden = !CHAT.unread;
    el.chatBadge.textContent = CHAT.unread > 99 ? '99+' : String(CHAT.unread);
    el.stage.classList.toggle('chat-unread', CHAT.unread > 0); // the dot while the controls are hidden
    document.title = CHAT.unread ? `(${el.chatBadge.textContent}) ${PAGE_TITLE}` : PAGE_TITLE; // on the tab
  }
  function onChat (msg) {
    CHAT.messages.push(msg);
    if (CHAT.messages.length > CHAT_KEEP) CHAT.messages.shift();
    const log = el.chatLog;
    const atEnd = log.scrollHeight - log.scrollTop - log.clientHeight < 40; // not while reading back
    log.appendChild(chatLine(msg));
    while (log.children.length > CHAT.messages.length) log.firstChild.remove();
    const own = msg.from === S.clientId;
    if (atEnd || own) log.scrollTop = log.scrollHeight;
    if (own || chatSeen()) return;
    CHAT.unread += 1;
    renderChat();
    if (chatOpen() && !chatDocked()) return; // the panel is open, only the corner box hides it
    const node = chatLine(msg);
    el.chatPeek.appendChild(node);
    while (el.chatPeek.children.length > CHAT_PEEK_MAX) el.chatPeek.firstChild.remove();
    setTimeout(() => { node.classList.add('gone'); setTimeout(() => node.remove(), 400); }, CHAT_PEEK_MS);
  }
  function setChat (open) {
    if (chatDocked()) { prefs.chatDock = open; savePrefs(); } else CHAT.overlay = open;
    renderChat();
    if (open) {
      el.chatPeek.replaceChildren();
      el.chatLog.scrollTop = el.chatLog.scrollHeight;
      el.chatInput.focus();
    } else if (el.chatInput.ownerDocument.activeElement === el.chatInput) {
      el.chatInput.blur(); // the keys are the player's again
    }
  }
  el.chatBtn.addEventListener('click', () => setChat(!chatOpen()));
  el.chatClose.addEventListener('click', () => setChat(false));
  el.chatInput.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    e.preventDefault();
    if (chatDocked()) el.chatInput.blur(); else setChat(false); // the column stays, the panel goes
  });
  el.chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = el.chatInput.value.trim();
    if (!text) return;
    if (!S.connected) { toast(t('chat_offline'), 'error'); return; } // the text stays in the box
    send({ type: 'chat', text });
    el.chatInput.value = '';
  });
  dockScreen.addEventListener('change', placeChat);
  document.addEventListener('visibilitychange', () => { if (chatSeen() && CHAT.unread) renderChat(); });
  document.addEventListener('fullscreenchange', placeChat);
  // Back from the corner box: what came meanwhile is now in sight.
  new MutationObserver(() => { if (chatSeen() && CHAT.unread) renderChat(); })
    .observe(el.stage, { attributes: true, attributeFilter: ['class'] });
  placeChat();

  // ---------------------------------------------------------------- join
  el.nameInput.value = prefs.name;
  renderLook();
  el.joinForm.addEventListener('submit', (e) => {
    e.preventDefault();
    prefs.name = el.nameInput.value.trim().slice(0, 24) || '?';
    prefs.uiLang = el.joinLang.value;
    savePrefs();
    S.joined = true;
    el.joinOverlay.hidden = true;
    phoneSync();
    if (S.kicked) { // removed by the host earlier: this is a new connection
      S.kicked = false;
      el.joinNotice.hidden = true;
      connect();
    }
    // Called inside the click, so the browser allows sound for later play() calls
    // and for the poke sounds.
    video.play().then(() => { if (!roomRunning()) video.pause(); }).catch(() => {});
    audio();
    sendHello();
    applyI18n();
  });

  // The host removed me (a ghost of mine, or on purpose): devices off, no reconnecting, and
  // back to the join screen, where joining again opens a new connection.
  function onKicked () {
    if (S.kicked) return;
    S.kicked = true;
    S.joined = false;
    clearTimeout(reconnectTimer);
    closeAllPeers();
    useTrack('mic', null);
    useTrack('cam', null);
    if (screen.stream) stopMyScreen(false);
    video.pause();
    el.joinNotice.hidden = false;
    el.joinOverlay.hidden = false;
    if (S.ws && S.ws.readyState <= WebSocket.OPEN) S.ws.close();
    setConn('disconnected');
  }

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
    renderToolbar(); renderVoice(); renderCams(); renderCatalogs(); renderAddons(); renderShare();
    if (ST.list.length) { renderStreamTools(); renderStreams(); }
    renderAi();
    if (AS.list.length) renderAddonSubs();
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
      chip.classList.toggle('others', !me && (!!m.joined || S.isHost)); // the host can remove a ghost that never joined
      chip.classList.toggle('speaking', speaking.has(m.id));
      const titles = [];
      if (m.buffering) { chip.classList.add('buffering'); titles.push(t('buffering')); }
      chip.textContent = me ? `${m.name} (${t('you')})` : m.name;
      if (m.host || m.cohost) {
        const role = document.createElement('span');
        role.className = 'role';
        role.textContent = t(m.host ? 'role_host' : 'role_cohost');
        chip.appendChild(role);
      }
      // My own state is known here at once; the server's copy comes back a moment later.
      const micOn = me ? !!voice.mic : !!m.mic;
      if (m.joined && !micOn) {
        chip.insertAdjacentHTML('beforeend', MIC_OFF_ICON);
        titles.push(t('mic_muted'));
      }
      chip.dataset.titles = titles.join('\n');
      el.members.appendChild(chip);
      renderNet(m.id);
    }
  }

  function renderCenter () {
    let text = '';
    let clickable = false;
    let note = false;
    if (S.media && !screen.owner && !S.room.loading) {
      if (S.room.waiting && S.room.waiting.length) {
        const names = S.members.filter((m) => S.room.waiting.includes(m.id)).map((m) => m.name);
        text = t('waiting_for', { names: names.join(', ') || '…' });
      } else if (S.autoplayBlocked && S.joined) {
        text = t('autoplay_blocked'); clickable = true;
      } else if (!S.room.playing && S.room.pausedBy && S.room.pausedBy.id !== S.clientId) {
        text = t('paused_by', { name: S.room.pausedBy.name }); note = true;
      }
    }
    el.centerMsg.textContent = text;
    el.centerMsg.classList.toggle('clickable', clickable);
    el.centerMsg.classList.toggle('note', note);
    el.empty.hidden = !!S.media || !!screen.owner || S.opening;
    renderLoader();
    el.centerMsg.hidden = !text || !el.loader.hidden;
  }

  function renderMediaPanel () {
    el.pathForm.hidden = !S.isHost;
    el.hostHint.hidden = S.isHost;
    renderLibraryBox();
    renderMini(); // a film opened or closed while scrolled down
    el.magnetForm.hidden = !S.canChangeMedia;
    el.mediaLockHint.hidden = S.canChangeMedia;
    el.closeMedia.hidden = !S.media || !S.canChangeMedia;
    el.osOff.hidden = S.osEnabled;
    el.addonSubs.hidden = !(S.media && S.media.content);
    el.filmTitle.textContent = S.media ? S.media.title : '';
    renderMediaInfo();
    renderNext();
    renderAudioTracks();
    renderTorrentInfo();
  }

  // A file with several sound tracks (dubbed and original): one choice for the whole room.
  function renderAudioTracks () {
    const tracks = (S.media && S.media.audioTracks) || [];
    el.audioField.hidden = tracks.length < 2;
    if (el.audioField.hidden) return;
    el.audioSel.replaceChildren(...tracks.map((a, i) => {
      const option = document.createElement('option');
      option.value = String(i);
      const lang = a.lang && a.lang !== 'und' ? langName(a.lang) : t('audio_unknown', { n: i + 1 });
      const tech = [(a.codec || '').toUpperCase(), a.channels ? `${a.channels}ch` : ''].filter(Boolean).join(' ');
      option.textContent = [lang, a.title].filter(Boolean).join(' · ') + (tech ? ` (${tech})` : '');
      return option;
    }));
    el.audioSel.value = String(S.media.audioIndex ?? 0);
    el.audioSel.disabled = !S.canChangeMedia;
    el.audioSel.title = S.canChangeMedia ? '' : t('media_trusted_only');
  }
  el.audioSel.addEventListener('change', async () => {
    const index = Number(el.audioSel.value);
    try {
      await api('/api/media/audio', { json: { index } });
    } catch (err) {
      toast(errorText(err), 'error');
      renderAudioTracks();
    }
  });

  // Converting: on the graphics card (which one) or on the CPU.
  const GPU_ENCODERS = { h264_nvenc: 'NVIDIA', h264_qsv: 'Intel', h264_amf: 'AMD', h264_videotoolbox: 'Apple' };
  function encoderText (encoder) {
    if (!encoder) return '';
    return GPU_ENCODERS[encoder] ? t('encoder_gpu', { name: GPU_ENCODERS[encoder] }) : t('encoder_cpu');
  }
  function renderMediaInfo () {
    const m = S.media;
    el.mediaInfo.replaceChildren();
    if (!m) return;
    const parts = [
      m.mode === 'copy' ? t('mode_copy') : [t('mode_transcode'), encoderText(m.encoder)].filter(Boolean).join(' '),
      `${(m.videoCodec || '').toUpperCase()} ${m.width || '?'}×${m.height || '?'}`,
      // An HDR film: converted to normal colours, or sent as it is (it looks pale then).
      m.hdr && m.mode === 'transcode' ? t(m.toneMap ? 'hdr_converted' : 'hdr_unconverted') : '',
      // Converting: the source's bitrate, then the stream's (at most twice the source's video).
      [m.bitrateKbps ? `${(m.bitrateKbps / 1000).toFixed(1)} Mbps` : '',
        m.targetKbps ? `${(m.targetKbps / 1000).toFixed(1)} Mbps` : ''].filter(Boolean).join(' → '),
      // Lowered (or converted at all) because several friends share Funnel's relay.
      m.funnelViewers ? t('funnel_for', { n: m.funnelViewers }) : '',
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
    if (!tor || !S.media || S.media.source !== 'torrent') { el.torrentInfo.replaceChildren(); return; }
    const text = document.createElement('div');
    text.textContent = t('torrent_stats', {
      pct: (tor.progress * 100).toFixed(1),
      down: fmtBytes(tor.downloadSpeed),
      up: fmtBytes(tor.uploadSpeed),
      peers: tor.numPeers,
    }) + (S.downloadThrottled ? ` ${t('torrent_throttled')}` : '');
    const bar = document.createElement('div');
    bar.className = 'dl-bar';
    bar.title = t('torrent_bar');
    bar.appendChild(document.createElement('i')).style.width = `${Math.min(100, tor.progress * 100)}%`;
    el.torrentInfo.replaceChildren(text, bar);
  }

  function trackLabel (track) {
    const name = langName(track.lang);
    // A file's own track is often titled with its language ("English"): no need to say it twice.
    const said = (code) => { try { return new Intl.DisplayNames(['en'], { type: 'language' }).of(code); } catch { return ''; } };
    // ...nor its number when it is the file's only track in that language.
    const alone = /^#\d+$/.test(track.label) && S.tracks.filter((tr) => tr.source === 'embedded' && tr.lang === track.lang).length === 1;
    const plain = track.source === 'embedded' && (alone || [name, said(track.lang)].some((n) => n && n.toLowerCase() === String(track.label).toLowerCase()));
    const label = track.source !== 'embedded' ? track.label : plain ? t('subs_embedded') : `${t('subs_embedded')} · ${track.label}`;
    return `${name} · ${label}${track.hashMatch ? ' ✓' : ''}`;
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
    renderOffsets();
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
      for (const [slot, key] of [[S.primary, 'subs_is_primary'], [S.secondary, 'subs_is_secondary']]) {
        if (slot !== track.id) continue;
        const tag = document.createElement('span'); tag.className = 'badge on'; tag.textContent = t(key);
        li.appendChild(tag);
      }
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
    for (const doc of [document, PIP.win && PIP.win.document].filter(Boolean)) {
      doc.documentElement.style.setProperty('--sub-scale', String(prefs.fontSize / 100));
      doc.documentElement.style.setProperty('--sub-bottom', `${prefs.bottom}%`);
    }
    el.sizeRange.value = prefs.fontSize;
    el.bottomRange.value = prefs.bottom;
  }

  let lastUi = 0;
  // A page's own frames stop while its window is minimized or covered. With the stage in the
  // always-on-top window, that window's frames draw instead, so the subtitles keep up there.
  function frame (now) {
    if (!PIP.win) drawFrame(now);
    requestAnimationFrame(frame);
  }
  function pipFrame (now) {
    if (!PIP.win) return;
    drawFrame(now);
    PIP.win.requestAnimationFrame(pipFrame);
  }
  function drawFrame (now) {
    const g = geom();
    animateBalls(now, g);
    renderStrokes(now, g);
    if (S.media) {
      const film = filmTime();
      setSubText(el.subPrimary, S.primary ? activeText(S.primary, subTime(S.primary, film)) : '');
      setSubText(el.subSecondary, S.secondary && S.secondary !== S.primary ? activeText(S.secondary, subTime(S.secondary, film)) : '');
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
  }

  // ---------------------------------------------------------------- phone: screen awake, lock screen keys
  // Wake lock: while the room plays a film the screen of this page stays on (a phone would dim
  // and lock in the middle of the film). The browser drops the lock when the page is hidden, so
  // it is asked again when the page shows. Only on a secure page (Funnel, Serve, localhost);
  // where there is none, or the browser says no, nothing happens.
  const WAKE = { lock: null, asking: false };
  const wantAwake = () => S.joined && !!S.media && !!S.room.playing && !document.hidden;
  function letSleep () {
    const lock = WAKE.lock;
    WAKE.lock = null;
    if (lock) lock.release().catch(() => {});
  }
  async function keepAwake () {
    if (!wantAwake()) { letSleep(); return; }
    if (WAKE.lock || WAKE.asking || !navigator.wakeLock) return;
    WAKE.asking = true;
    try {
      const lock = await navigator.wakeLock.request('screen');
      lock.addEventListener('release', () => { if (WAKE.lock === lock) WAKE.lock = null; });
      WAKE.lock = lock;
      if (!wantAwake()) letSleep(); // paused while it was being asked
    } catch { /* not allowed (hidden page, battery saver): the screen may sleep */ }
    WAKE.asking = false;
  }

  // Media Session: the lock screen, the notification and headset keys show the film and steer
  // the ROOM, like the buttons. Without handlers the browser would pause only this <video>; the
  // handlers win, and a video paused locally anyway is played again by syncTick.
  const MEDIA_SESSION = 'mediaSession' in navigator ? navigator.mediaSession : null;
  const mediaActions = {
    play: () => { if (S.media && !S.room.playing) send({ type: 'play' }); },
    pause: () => { if (S.media && S.room.playing) send({ type: 'pause' }); },
    seekbackward: (d) => seekTo(expectedPosition() - ((d && d.seekOffset) || 10)),
    seekforward: (d) => seekTo(expectedPosition() + ((d && d.seekOffset) || 10)),
    seekto: (d) => { if (d && Number.isFinite(d.seekTime)) seekTo(d.seekTime); }, // film time, as in the position state
  };
  if (MEDIA_SESSION) {
    for (const [action, handler] of Object.entries(mediaActions)) {
      try { MEDIA_SESSION.setActionHandler(action, handler); } catch { /* an action this browser does not know */ }
    }
  }
  let sessionKey = null;
  function syncMediaSession () {
    if (!MEDIA_SESSION) return;
    const m = S.joined ? S.media : null;
    // The add-on poster when the film came from the browse card, else the app's icon.
    const poster = m && (m.poster || (B.title && m.content && B.title.id === m.content.id && B.title.poster)) || '';
    const key = m ? `${m.mediaKey}|${m.title}|${poster}` : '';
    if (key !== sessionKey && typeof MediaMetadata === 'function') {
      sessionKey = key;
      try {
        MEDIA_SESSION.metadata = !m ? null : new MediaMetadata({
          title: m.title || 'Co-Watch', artist: 'Co-Watch',
          artwork: poster
            ? [{ src: poster }]
            : [{ src: new URL('/static/favicon.svg', location.href).href, sizes: 'any', type: 'image/svg+xml' }],
        });
      } catch { /* a bad artwork address: no metadata rather than an error */ }
    }
    MEDIA_SESSION.playbackState = !m ? 'none' : S.room.playing ? 'playing' : 'paused';
    const duration = m ? Number(m.duration) : 0;
    if (!MEDIA_SESSION.setPositionState) return;
    try {
      if (!(duration > 0 && Number.isFinite(duration))) { MEDIA_SESSION.setPositionState(); return; }
      const position = Math.min(Math.max(0, Number(expectedPosition()) || 0), duration);
      MEDIA_SESSION.setPositionState({ duration, position, playbackRate: S.room.rate > 0 ? S.room.rate : 1 });
    } catch { /* invalid numbers for a moment: the next sync puts them right */ }
  }
  function phoneSync () { keepAwake(); syncMediaSession(); }
  document.addEventListener('visibilitychange', phoneSync);
  setInterval(phoneSync, 3000);

  // ---------------------------------------------------------------- a newer version (server/updates.py)
  // The server asks GitHub once a day; the host's Share card and the settings page say when a
  // newer release is out, with a link to it. Nothing more: no question, no automatic update.
  const UPD = { latest: null };
  function updateLink (u) {
    const a = document.createElement('a');
    a.href = u.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
    a.textContent = t('update_link');
    return a;
  }
  function renderUpdate (u) {
    UPD.latest = u && u.version && /^https:\/\//.test(u.url || '') ? u : null;
    const note = $('#updateNote');
    if (!note) return;
    note.hidden = !UPD.latest;
    if (!UPD.latest) { note.textContent = ''; return; }
    note.textContent = `${t('update_out', { version: UPD.latest.version })} `;
    note.appendChild(updateLink(UPD.latest));
  }
  function renderVersion (data) {
    const node = $('#settingsVersion');
    if (!node || !data.version) return;
    renderUpdate(data.update);
    node.textContent = t('update_this', { version: data.version });
    if (UPD.latest) {
      node.append(' · ', t('update_out', { version: UPD.latest.version }), ' ');
      node.appendChild(updateLink(UPD.latest));
    }
  }

  // For the browser console: cowatchDebug() shows the sync numbers.
  window.cowatchDebug = () => ({
    filmTime: filmTime(), expected: expectedPosition(), drift: filmTime() - expectedPosition(),
    room: S.room, media: S.media, clockOffset: S.clock.offset, rate: video.playbackRate,
    readyState: video.readyState, primary: S.primary, secondary: S.secondary, align: prefs.align,
    frameWatch: { fixes: frameWatch.fixes, reloads: frameWatch.reloads },
    lumaWatch: { step: lumaWatch.step, luma: pictureLuma() },
    resumeAhead: resumeAhead(), bufferingSent: S.bufferingSent,
    screen: {
      owner: screen.owner, pending: screen.pending, mine: !!screen.stream,
      showing: !el.screenVideo.hidden && el.screenVideo.videoWidth > 0 && !el.screenVideo.paused,
      asks: [...el.shareAsks.querySelectorAll('[data-from]')].map((n) => n.dataset.from),
    },
    clientId: S.clientId, members: S.members, tracks: S.tracks, penMode: S.penMode, eraser: S.eraser, eraseWhole: !!prefs.eraseWhole, strokes: strokes.size, balls: [...balls.keys()],
    voice: {
      mic: !!voice.mic, cam: !!voice.cam, camLive: !!(voice.cam && voice.cam.readyState === 'live'),
      duck, filmVolume: video.volume, speaking: [...speaking],
      peers: [...peers.values()].map((p) => {
        const enc = p.videoTx && (p.videoTx.sender.getParameters().encodings || [])[0];
        const screenParams = p.screenTx && p.screenTx.sender.getParameters();
        const screenEnc = screenParams && (screenParams.encodings || [])[0];
        return {
          screenMaxBitrate: screenEnc ? screenEnc.maxBitrate : null, screenDown: screenEnc ? screenEnc.scaleResolutionDownBy : null,
          screenDegradation: screenParams ? screenParams.degradationPreference || null : null,
          id: p.id, polite: p.polite, state: p.pc.connectionState, level: peerLevel(p),
          sending: !!(p.audioTx && p.audioTx.sender.track), sendingVideo: !!(p.videoTx && p.videoTx.sender.track),
          videoMaxBitrate: enc ? enc.maxBitrate : null, videoMaxFramerate: enc ? enc.maxFramerate : null, transceivers: p.pc.getTransceivers().length,
          sendingScreen: !!(p.screenTx && p.screenTx.sender.track),
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
