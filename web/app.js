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
  };
  const video = el.video;

  // ---------------------------------------------------------------- preferences
  const PREFS_KEY = 'cowatch.prefs.v1';
  const DEFAULT_PREFS = {
    name: '', uiLang: detectUiLang(), primaryLang: '', secondaryLang: '', offsetMs: 0,
    fontSize: 100, bottom: 8, searchLangs: '', volume: 1, muted: false,
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
      if (S.joined) send({ type: 'hello', name: prefs.name });
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
        S.progress = msg.progress;
        applyMedia(msg.media);
        applyTracks(msg.tracks || []);
        renderAll();
        break;
      case 'pong': onPong(msg); break;
      case 'state': S.room = msg; renderControls(); renderCenter(); break;
      case 'members': S.members = msg.members || []; renderMembers(); renderCenter(); break;
      case 'media': applyMedia(msg.media); break;
      case 'progress': S.progress = msg; renderMediaInfo(); break;
      case 'subtitles': applyTracks(msg.tracks || []); break;
      case 'status': onStatus(msg); break;
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
  el.stage.addEventListener('dblclick', (e) => { if (!el.controls.contains(e.target)) toggleFullscreen(); });
  el.stage.addEventListener('click', (e) => {
    if (el.controls.contains(e.target)) return;
    if (S.autoplayBlocked) { video.play().catch(() => {}); return; }
    // On touch screens a tap only reveals the controls; pausing for everyone needs the button.
    if (e.pointerType && e.pointerType !== 'mouse') return;
    togglePlay();
  });

  document.addEventListener('keydown', (e) => {
    const tag = (e.target && e.target.tagName) || '';
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(tag) || !S.joined) return;
    if (e.code === 'Space' || e.key === 'k') { e.preventDefault(); togglePlay(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); seekTo(expectedPosition() - 10); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); seekTo(expectedPosition() + 10); }
    else if (e.key === 'f') toggleFullscreen();
    else if (e.key === 'm') el.muteBtn.click();
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
    // Called inside the click, so the browser allows sound for later play() calls.
    video.play().then(() => { if (!roomRunning()) video.pause(); }).catch(() => {});
    send({ type: 'hello', name: prefs.name });
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
  });

  // ---------------------------------------------------------------- start
  applyI18n();
  connect();
  pollStatus();
  setInterval(pollStatus, 3000);
  setInterval(syncTick, 250);
  requestAnimationFrame(frame);
})();
