const API = import.meta.env.VITE_API_BASE || ''

export async function getBrowseRoots() {
  const r = await fetch(`${API}/api/local/browse/roots`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function browsePath(path) {
  const r = await fetch(`${API}/api/local/browse?path=${encodeURIComponent(path)}`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

/** 弹出系统选择文件夹对话框（后端会调系统 API，请求会阻塞到用户选完或取消） */
export async function pickFolder() {
  const r = await fetch(`${API}/api/local/pick-folder`, { method: 'POST' })
  if (!r.ok) throw new Error(await r.text())
  const data = await r.json()
  return data.path || null
}

export async function scanFolder(path) {
  const r = await fetch(`${API}/api/local/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function getLibraryState(libraryId, retries = 2) {
  for (let i = 0; i <= retries; i++) {
    const r = await fetch(`${API}/api/local/library-state?library_id=${encodeURIComponent(libraryId)}`)
    if (r.status === 404) {
      if (i < retries) {
        await new Promise((r) => setTimeout(r, 300))
        continue
      }
      throw new Error('LIBRARY_NOT_FOUND')
    }
    if (!r.ok) throw new Error(await r.text())
    return r.json()
  }
  throw new Error('LIBRARY_NOT_FOUND')
}

export async function getLibraryList() {
  const r = await fetch(`${API}/api/local/library-list`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function searchControl(libraryId, action) {
  const r = await fetch(`${API}/api/local/search-control`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ library_id: libraryId, action }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function downloadControl(libraryId, action) {
  const r = await fetch(`${API}/api/local/download-control`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ library_id: libraryId, action }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function selectChoice(libraryId, songId, source, index) {
  const r = await fetch(`${API}/api/local/select-choice`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ library_id: libraryId, song_id: songId, source: source ?? null, index: index ?? null }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function resetDownloads(libraryId) {
  const r = await fetch(`${API}/api/local/reset-downloads`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ library_id: libraryId }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function resetSearchErrors(libraryId) {
  const r = await fetch(`${API}/api/local/reset-search-errors`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ library_id: libraryId }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

/** 全部重置为待搜索，清空搜索结果与错误，可重新开始遍历搜索 */
export async function resetAllToPending(libraryId) {
  const r = await fetch(`${API}/api/local/reset-all-to-pending`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ library_id: libraryId }),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function getTaskStatus(libraryId) {
  const r = await fetch(`${API}/api/local/task-status?library_id=${encodeURIComponent(libraryId)}`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export function streamUrl(libraryId, songId) {
  return `${API}/api/local/stream?library_id=${encodeURIComponent(libraryId)}&song_id=${encodeURIComponent(songId)}`
}

/** 搜索结果试听流 URL（后端代理） */
export function previewUrl(libraryId, songId, source, index) {
  return `${API}/api/local/preview?library_id=${encodeURIComponent(libraryId)}&song_id=${encodeURIComponent(songId)}&source=${encodeURIComponent(source)}&index=${encodeURIComponent(index)}`
}
