// Co-Watch torrent helper.
// Turns a magnet link into a Range-capable HTTP stream on localhost so ffmpeg can read it
// while the torrent is still downloading. Only the Python server talks to this process.

import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import WebTorrent from 'webtorrent'

const HOST = process.env.HELPER_HOST || '127.0.0.1'
const PORT = Number(process.env.HELPER_PORT || 8890)
const DOWNLOAD_DIR = path.resolve(process.env.TORRENT_DIR || path.join(process.cwd(), 'data', 'torrents'))
const PARENT_PID = Number(process.env.PARENT_PID || 0)

// Limits are in KB/s; 0 or a negative value means "no limit".
const kbToRate = (value, fallback) => {
  const n = Number(value)
  const kb = Number.isFinite(n) && value !== undefined && value !== '' ? n : fallback
  return kb > 0 ? Math.round(kb * 1024) : -1
}
const UPLOAD_LIMIT = kbToRate(process.env.TORRENT_UPLOAD_LIMIT, 64)
const DOWNLOAD_LIMIT = kbToRate(process.env.TORRENT_DOWNLOAD_LIMIT, 0)
const METADATA_TIMEOUT_MS = 120_000
const HEAD_TAIL_BYTES = 2 * 1024 * 1024

const VIDEO_EXT = new Set(['.mkv', '.mp4', '.m4v', '.avi', '.mov', '.webm', '.ts', '.m2ts', '.wmv', '.mpg', '.mpeg', '.flv'])

const log = (...args) => console.log('[torrent]', ...args)

fs.mkdirSync(DOWNLOAD_DIR, { recursive: true })

const client = new WebTorrent({ uploadLimit: UPLOAD_LIMIT, downloadLimit: DOWNLOAD_LIMIT })
client.on('error', (err) => log('client error:', err?.message || err))

class HttpError extends Error {
  constructor (status, message) {
    super(message)
    this.status = status
  }
}

function json (res, status, body) {
  const data = JSON.stringify(body)
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': Buffer.byteLength(data) })
  res.end(data)
}

async function readJson (req) {
  let raw = ''
  for await (const chunk of req) {
    raw += chunk
    if (raw.length > 64 * 1024) throw new HttpError(413, 'body too large')
  }
  if (!raw) return {}
  try {
    return JSON.parse(raw)
  } catch {
    throw new HttpError(400, 'invalid JSON')
  }
}

function fileInfo (f, index) {
  return {
    index,
    name: f.name,
    path: f.path,
    length: f.length,
    isVideo: VIDEO_EXT.has(path.extname(f.name).toLowerCase()),
    progress: Number(f.progress.toFixed(4))
  }
}

function torrentInfo (t) {
  return {
    infoHash: t.infoHash,
    name: t.name || null,
    ready: Boolean(t.ready),
    length: t.length || 0,
    progress: Number((t.progress || 0).toFixed(4)),
    downloaded: t.downloaded || 0,
    downloadSpeed: Math.round(t.downloadSpeed || 0),
    uploadSpeed: Math.round(t.uploadSpeed || 0),
    numPeers: t.numPeers || 0,
    files: t.ready ? t.files.map(fileInfo) : []
  }
}

function waitReady (t, ms) {
  if (t.ready) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      clearTimeout(timer)
      t.removeListener('ready', onReady)
      t.removeListener('error', onError)
    }
    const onReady = () => { cleanup(); resolve() }
    const onError = (err) => { cleanup(); reject(err instanceof Error ? err : new Error(String(err))) }
    const timer = setTimeout(() => {
      cleanup()
      reject(new HttpError(504, 'torrent metadata timeout (no peers yet?)'))
    }, ms)
    t.once('ready', onReady)
    t.once('error', onError)
  })
}

const MAGNET_RE = /^(magnet:\?.*xt=urn:bt[im]h:|[a-f0-9]{40}$|[a-z2-7]{32}$)/i

async function addTorrent (body) {
  const magnet = typeof body.magnet === 'string' ? body.magnet.trim() : ''
  if (!MAGNET_RE.test(magnet)) throw new HttpError(400, 'invalid magnet link')

  let t = await client.get(magnet)
  if (!t) {
    t = client.add(magnet, { path: DOWNLOAD_DIR, deselect: true })
    t.on('error', (err) => log('torrent error:', err?.message || err))
    t.on('warning', (err) => log('torrent warning:', err?.message || err))
  }
  // Optional explicit peers ("ip:port"), mainly for local testing.
  const peers = Array.isArray(body.peers) ? body.peers.filter((p) => typeof p === 'string') : []
  if (peers.length) {
    const addPeers = () => peers.forEach((p) => t.addPeer(p))
    if (t.infoHash) addPeers()
    else t.once('infoHash', addPeers)
  }
  await waitReady(t, METADATA_TIMEOUT_MS)
  log('ready:', t.name, `(${t.files.length} files)`)
  return torrentInfo(t)
}

// Select one file for download and fetch its head and tail first:
// container headers, the MKV seek index and the OpenSubtitles hash all live there.
function prepareFile (t, fileIndex) {
  const f = t.files[fileIndex]
  if (!f) throw new HttpError(404, 'unknown file index')
  t.files.forEach((other, i) => { if (i !== fileIndex) other.deselect() })
  f.select()

  if (f.length > 0) {
    const pl = t.pieceLength
    const span = Math.min(f.length, HEAD_TAIL_BYTES)
    const headStart = Math.floor(f.offset / pl)
    const headEnd = Math.floor((f.offset + span - 1) / pl)
    const tailStart = Math.floor((f.offset + f.length - span) / pl)
    const tailEnd = Math.floor((f.offset + f.length - 1) / pl)
    t.critical(headStart, headEnd)
    t.critical(tailStart, tailEnd)
  }
  log('prepared:', f.name)
  return torrentInfo(t)
}

function parseRange (header, size) {
  if (!header) return null
  const m = /^bytes=(\d*)-(\d*)$/.exec(header.trim())
  if (!m || (m[1] === '' && m[2] === '')) return { invalid: true }
  let start
  let end = size - 1
  if (m[1] === '') {
    start = Math.max(0, size - Number(m[2]))
  } else {
    start = Number(m[1])
    if (m[2] !== '') end = Math.min(Number(m[2]), size - 1)
  }
  if (start >= size || start > end) return { invalid: true }
  return { start, end }
}

async function streamFile (t, fileIndex, req, res) {
  const f = t.files[fileIndex]
  if (!f) throw new HttpError(404, 'unknown file index')
  const size = f.length

  const range = parseRange(req.headers.range, size)
  if (range?.invalid) {
    res.writeHead(416, { 'Content-Range': `bytes */${size}` })
    return res.end()
  }
  const start = range ? range.start : 0
  const end = range ? range.end : size - 1
  const headers = {
    'Content-Type': f.type || 'application/octet-stream',
    'Accept-Ranges': 'bytes',
    'Content-Length': end - start + 1,
    'Cache-Control': 'no-store'
  }
  if (range) headers['Content-Range'] = `bytes ${start}-${end}/${size}`
  res.writeHead(range ? 206 : 200, headers)
  if (req.method === 'HEAD' || size === 0) return res.end()

  if (end === 0) {
    // webtorrent treats end=0 as "until the end of the file", so read two bytes and trim.
    const buf = new Uint8Array(await f.arrayBuffer({ start: 0, end: 1 }))
    return res.end(Buffer.from(buf.subarray(0, 1)))
  }

  const stream = f.createReadStream({ start, end })
  res.on('close', () => stream.destroy())
  stream.on('error', (err) => {
    log('stream error:', err?.message || err)
    res.destroy()
  })
  stream.pipe(res)
}

async function route (req, res) {
  const url = new URL(req.url, 'http://localhost')
  const parts = url.pathname.split('/').filter(Boolean)

  if (req.method === 'GET' && url.pathname === '/health') {
    return json(res, 200, { ok: true, torrents: client.torrents.length })
  }
  if (req.method === 'POST' && url.pathname === '/torrents') {
    return json(res, 200, await addTorrent(await readJson(req)))
  }
  if (req.method === 'POST' && url.pathname === '/throttle') {
    const body = await readJson(req)
    if (body.download !== undefined) client.throttleDownload(kbToRate(body.download, 0))
    if (body.upload !== undefined) client.throttleUpload(kbToRate(body.upload, 0))
    return json(res, 200, { ok: true })
  }
  if (parts[0] === 'torrents' && parts[1]) {
    const t = await client.get(parts[1])
    if (!t) throw new HttpError(404, 'unknown torrent')

    if (parts.length === 2 && req.method === 'GET') return json(res, 200, torrentInfo(t))
    if (parts.length === 2 && req.method === 'DELETE') {
      await client.remove(t.infoHash, { destroyStore: false })
      return json(res, 200, { ok: true })
    }
    if (parts[2] === 'prepare' && req.method === 'POST') {
      if (!t.ready) throw new HttpError(409, 'torrent metadata not ready')
      const body = await readJson(req)
      return json(res, 200, prepareFile(t, Number(body.fileIndex)))
    }
    if (parts[2] === 'files' && parts[3] !== undefined && (req.method === 'GET' || req.method === 'HEAD')) {
      if (!t.ready) throw new HttpError(409, 'torrent metadata not ready')
      return streamFile(t, Number(parts[3]), req, res)
    }
  }
  throw new HttpError(404, 'not found')
}

const server = http.createServer((req, res) => {
  route(req, res).catch((err) => {
    const status = err instanceof HttpError ? err.status : 500
    if (status >= 500) log('error:', err?.message || err)
    if (!res.headersSent) json(res, status, { error: err?.message || String(err) })
    else res.destroy()
  })
})

// A helper from the previous run may still be shutting down: retry for a while.
let listenRetries = 0
server.on('error', (err) => {
  if (err.code === 'EADDRINUSE' && listenRetries < 15) {
    listenRetries += 1
    setTimeout(() => server.listen(PORT, HOST), 1000)
    return
  }
  log(`cannot listen on ${HOST}:${PORT}: ${err.message}`)
  process.exit(1)
})
server.listen(PORT, HOST, () => {
  log(`listening on http://${HOST}:${PORT} (upload limit: ${UPLOAD_LIMIT < 0 ? 'none' : `${Math.round(UPLOAD_LIMIT / 1024)} KB/s`})`)
})

function shutdown () {
  log('shutting down')
  server.close()
  client.destroy(() => process.exit(0))
  setTimeout(() => process.exit(0), 3000).unref()
}
process.on('SIGINT', shutdown)
process.on('SIGTERM', shutdown)

// Exit together with the Python server, even if it was killed without cleanup.
if (PARENT_PID > 0) {
  setInterval(() => {
    try {
      process.kill(PARENT_PID, 0)
    } catch {
      shutdown()
    }
  }, 5000).unref()
}
