import { useState, useEffect, useCallback, useRef } from 'react'
import {
  pickFolder,
  getBrowseRoots,
  browsePath,
  scanFolder,
  getLibraryState,
  getLibraryList,
  searchControl,
  downloadControl,
  selectChoice,
  resetDownloads,
  resetSearchErrors,
  resetAllToPending,
  getTaskStatus,
  streamUrl,
  previewUrl,
} from './api'
import './App.css'

const STATUS_COLOR = {
  pending: '#e74c3c',
  searched: '#2ecc71',
  selected: '#3498db',
  downloaded: '#9b59b6',
  error: '#f1c40f',
}

function FolderPicker({ onSelect, onClose }) {
  const [roots, setRoots] = useState([])
  const [stack, setStack] = useState([])
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setError('')
    getBrowseRoots()
      .then(setRoots)
      .catch((e) => {
        const msg = e?.message || String(e)
        if (msg.includes('ECONNREFUSED') || msg.includes('fetch'))
          setError('无法连接后端。请先在项目根目录另开终端执行：\nuvicorn local_music_web.backend.main:app --reload --host 127.0.0.1 --port 8000')
        else
          setError(msg)
      })
  }, [])

  const currentPath = stack.length ? stack[stack.length - 1].path : null

  const load = useCallback(async (path) => {
    if (!path) {
      setEntries(roots)
      return
    }
    setLoading(true)
    setError('')
    try {
      const list = await browsePath(path)
      setEntries(list)
    } catch (e) {
      setError(e.message)
      setEntries([])
    } finally {
      setLoading(false)
    }
  }, [roots])

  useEffect(() => {
    if (currentPath === null && roots.length) setEntries(roots)
    else if (currentPath) load(currentPath)
  }, [currentPath, roots, load])

  const open = (entry) => {
    if (!entry.is_dir) return
    setStack((s) => [...s, entry])
  }
  const back = () => setStack((s) => s.slice(0, -1))
  const chooseFolder = () => {
    if (currentPath) onSelect(currentPath)
    onClose()
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal folder-picker" onClick={(e) => e.stopPropagation()}>
        <h3>选择文件夹</h3>
        <p className="modal-hint">从下面列表逐级点进目录，最后点「选择当前文件夹」即可（需先启动后端）。</p>
        <div className="breadcrumb">
          <button type="button" onClick={() => setStack([])}>根目录</button>
          {stack.map((e, i) => (
            <span key={e.path}>
              <span className="sep">/</span>
              <button type="button" onClick={() => setStack(stack.slice(0, i + 1))}>{e.name}</button>
            </span>
          ))}
        </div>
        {error && <p className="error error-block">{error}</p>}
        <div className="browse-list">
          {loading && <p>加载中...</p>}
          {!loading && !error && roots.length === 0 && <p>正在连接后端...</p>}
          {!loading && entries.filter((e) => e.is_dir).map((e) => (
            <button key={e.path} type="button" className="browse-item" onClick={() => open(e)}>
              📁 {e.name}
            </button>
          ))}
        </div>
        <div className="modal-actions">
          <button type="button" onClick={chooseFolder} disabled={!currentPath} title={currentPath || ''}>
            {currentPath ? '选择当前文件夹' : '请先点击上方目录进入'}
          </button>
          <button type="button" onClick={onClose}>取消</button>
        </div>
      </div>
    </div>
  )
}

function StatusLight({ status }) {
  return (
    <span
      className="status-light"
      style={{ backgroundColor: STATUS_COLOR[status] || STATUS_COLOR.pending }}
      title={status}
    />
  )
}

function App() {
  const [library, setLibrary] = useState(null)
  const [libraryId, setLibraryId] = useState(() => localStorage.getItem('local_music_library_id') || '')
  const [showFolderPicker, setShowFolderPicker] = useState(false)
  const [pickingFolder, setPickingFolder] = useState(false)
  const [selectedSong, setSelectedSong] = useState(null)
  const [playerSrc, setPlayerSrc] = useState(null)
  const [playerTitle, setPlayerTitle] = useState('')
  const [polling, setPolling] = useState(false)
  const [error, setError] = useState('')
  const audioRef = useRef(null)

  const refreshLibrary = useCallback(async () => {
    if (!libraryId) return
    try {
      const data = await getLibraryState(libraryId)
      setLibrary(data)
      setError('')
    } catch (e) {
      const msg = e?.message || ''
      if (msg === 'LIBRARY_NOT_FOUND') {
        localStorage.removeItem('local_music_library_id')
        setLibraryId('')
        setLibrary(null)
        setError('之前的库已不存在，请重新选择文件夹')
      } else {
        setError(msg)
      }
    }
  }, [libraryId])

  useEffect(() => {
    if (libraryId) {
      localStorage.setItem('local_music_library_id', libraryId)
      refreshLibrary()
    } else {
      setLibrary(null)
    }
  }, [libraryId, refreshLibrary])

  useEffect(() => {
    if (!polling || !libraryId) return
    const id = setInterval(refreshLibrary, 1500)
    return () => clearInterval(id)
  }, [polling, libraryId, refreshLibrary])

  const handleSelectFolder = async (path) => {
    setError('')
    try {
      const res = await scanFolder(path)
      setLibraryId(res.library_id)
      setLibrary(res.library)
    } catch (e) {
      setError(e.message)
    }
    setShowFolderPicker(false)
  }

  const handlePickFolderClick = async () => {
    setError('')
    setPickingFolder(true)
    try {
      const path = await pickFolder()
      if (path) await handleSelectFolder(path)
    } catch (e) {
      setError(e?.message || '选择文件夹失败')
    } finally {
      setPickingFolder(false)
    }
  }

  const searchStart = async () => {
    setError('')
    try {
      await searchControl(libraryId, 'start')
      setPolling(true)
      await refreshLibrary()
    } catch (e) {
      const msg = e?.message || ''
      try {
        const j = JSON.parse(msg)
        setError(j.detail || msg)
      } catch {
        setError(msg)
      }
    }
  }
  const searchPause = async () => {
    try {
      await searchControl(libraryId, 'pause')
      setPolling(false)
      await refreshLibrary()
    } catch (e) {
      setError(e.message)
    }
  }
  const searchStop = async () => {
    try {
      await searchControl(libraryId, 'stop')
      setPolling(false)
      await refreshLibrary()
    } catch (e) {
      setError(e.message)
    }
  }
  const searchContinue = async () => {
    try {
      await searchControl(libraryId, 'continue')
      setPolling(true)
      await refreshLibrary()
    } catch (e) {
      setError(e.message)
    }
  }

  const downloadStart = async () => {
    setError('')
    try {
      await downloadControl(libraryId, 'start')
      setPolling(true)
      await refreshLibrary()
    } catch (e) {
      setError(e.message)
    }
  }
  const downloadPause = () => downloadControl(libraryId, 'pause').then(refreshLibrary)

  useEffect(() => {
    if (library?.search_task?.status === 'idle' && library?.download_task?.status === 'idle') setPolling(false)
  }, [library?.search_task?.status, library?.download_task?.status])

  const handleSelectChoice = async (songId, source, index) => {
    if (!library) return
    const song = library.songs.find((s) => s.id === songId)
    const isSelected = song?.best_choice && song.best_choice.source === source && song.best_choice.index === index
    try {
      const res = await selectChoice(libraryId, songId, isSelected ? null : source, isSelected ? null : index)
      if (res?.song) {
        // 本地立即更新列表与当前选中项，避免等待整库刷新带来的 1～2 秒延迟
        setLibrary((prev) => {
          if (!prev) return prev
          const nextSongs = prev.songs.map((s) => (s.id === res.song.id ? res.song : s))
          return { ...prev, songs: nextSongs }
        })
        setSelectedSong((prev) => (prev?.id === res.song.id ? res.song : prev))
      }
      // 后台同步一次完整库状态，确保与后端最终一致
      refreshLibrary()
    } catch (e) {
      setError(e.message)
    }
  }

  const playLocal = (song) => {
    if (!libraryId) return
    const src = streamUrl(libraryId, song.id)
    const title = `${song.song_name || song.file_name} - ${song.singers}`
    setPlayerSrc(src)
    setPlayerTitle(title)
  }
  const playPreview = (songId, source, index, item) => {
    if (!libraryId) return
    const src = previewUrl(libraryId, songId, source, index)
    const title = `${item.song_name} - ${item.singers}`
    setPlayerSrc(src)
    setPlayerTitle(title)
  }

  const songs = library?.songs ?? []
  const searchTask = library?.search_task ?? {}
  const downloadTask = library?.download_task ?? {}
  const searchedCount = songs.filter((s) => ['searched', 'selected', 'downloaded'].includes(s.status)).length
  const selectedCount = songs.filter((s) => ['selected', 'downloaded'].includes(s.status)).length
  const total = songs.length
  const searchingSong = (() => {
    const i = Number.isFinite(searchTask?.current_index) ? searchTask.current_index : 0
    if (!songs.length) return null
    const safe = Math.min(Math.max(i, 0), songs.length - 1)
    return songs[safe] || null
  })()

  return (
    <div className="app">
      <header className="top-bar">
        <div className="path-row">
          <span className="folder-path">{library?.folder_path || '未选择文件夹'}</span>
          <button
            type="button"
            className="btn primary"
            onClick={handlePickFolderClick}
            disabled={pickingFolder}
          >
            {pickingFolder ? '请在弹出的对话框中选择…' : '选择文件夹'}
          </button>
          <button type="button" className="btn secondary" onClick={() => setShowFolderPicker(true)} title="若系统对话框不可用可改用逐级浏览">
            逐级浏览
          </button>
        </div>
        {error && <p className="error">{error}</p>}
        <div className="controls">
          <button type="button" onClick={searchStart} disabled={!libraryId || searchTask.status === 'running'}>开始遍历搜索</button>
          <button type="button" onClick={searchPause} disabled={searchTask.status !== 'running'}>暂停</button>
          <button type="button" onClick={searchStop} disabled={!libraryId || (searchTask.status !== 'running' && searchTask.status !== 'paused')} title="彻底停止搜索，状态变为空闲">停止</button>
          <button type="button" onClick={searchContinue} disabled={!libraryId || searchTask.status === 'running'}>继续</button>
          <button
            type="button"
            onClick={async () => { await resetAllToPending(libraryId); refreshLibrary() }}
            disabled={!libraryId || searchTask.status === 'running'}
            title="将所有歌曲改为「待搜索」、清空搜索结果与错误，然后可点「开始遍历搜索」从头搜"
          >
            全部重置为待搜索
          </button>
          <button
            type="button"
            onClick={async () => { await resetSearchErrors(libraryId); refreshLibrary() }}
            disabled={!libraryId || searchTask.status === 'running'}
            title="仅将状态为「错误」的歌曲改回「待搜索」"
          >
            仅错误项重置
          </button>
          <span className="progress">
            搜索: {searchedCount}/{total} ({total ? Math.round((searchedCount / total) * 100) : 0}%) | 已选择: {selectedCount}/{total}
          </span>
          {searchTask.status === 'running' && (
            <span className="task-badge running" title="搜索进行中">
              正在搜索：{searchingSong?.song_name || searchingSong?.file_name || '…'}
            </span>
          )}
          {searchTask.status === 'paused' && (
            <span className="task-badge paused" title="已暂停，可点继续">
              搜索已暂停
            </span>
          )}
          <button type="button" className="btn primary" onClick={downloadStart} disabled={!libraryId || downloadTask.status === 'running'}>
            下载所有最佳选择
          </button>
          <button type="button" onClick={downloadPause} disabled={downloadTask.status !== 'running'}>暂停下载</button>
          {downloadTask.status === 'running' && downloadTask.current_song_name && (
            <span className="downloading-now">
              正在下载: {downloadTask.current_song_name}
            </span>
          )}
          <button type="button" onClick={async () => { await resetDownloads(libraryId); refreshLibrary() }} disabled={!libraryId}>重置已下载</button>
        </div>
      </header>

      <div className="main">
        <aside className="song-list">
          <h3>歌曲列表 ({songs.length})</h3>
          <ul>
            {songs.map((song) => (
              <li
                key={song.id}
                className={selectedSong?.id === song.id ? 'selected' : ''}
                onClick={() => setSelectedSong(song)}
              >
                <StatusLight status={song.status} />
                <button
                  type="button"
                  className="play-btn"
                  onClick={(e) => { e.stopPropagation(); playLocal(song) }}
                  title="播放"
                >
                  ▶
                </button>
                <span className="song-title">{song.song_name || song.file_name}</span>
                <span className="song-artist">{song.singers}</span>
              </li>
            ))}
          </ul>
        </aside>
        <section className="detail">
          {selectedSong ? (
            <>
              <h3>歌曲信息</h3>
              <div className="detail-play-row">
                <button
                  type="button"
                  className="btn primary play-local-btn"
                  onClick={() => playLocal(selectedSong)}
                  title="播放本地文件"
                >
                  ▶ 播放本地
                </button>
              </div>
              <div className="song-info-grid">
                <div className="info-card">
                  <div className="info-label">歌名</div>
                  <div className="info-value">{selectedSong.song_name || '—'}</div>
                </div>
                <div className="info-card">
                  <div className="info-label">歌手</div>
                  <div className="info-value">{selectedSong.singers || '—'}</div>
                </div>
                <div className="info-card">
                  <div className="info-label">时长</div>
                  <div className="info-value">{selectedSong.duration_display || '—'}</div>
                </div>
                <div className="info-card">
                  <div className="info-label">状态</div>
                  <div className={`info-pill status-${selectedSong.status || 'pending'}`}>{selectedSong.status || 'pending'}</div>
                </div>
                <div className="info-card info-wide">
                  <div className="info-label">文件名</div>
                  <div className="info-value mono">{selectedSong.file_name || '—'}</div>
                </div>
                {selectedSong.status === 'error' && selectedSong.error_message && (
                  <div className="info-card info-wide error-card">
                    <div className="info-label">失败原因</div>
                    <div className="info-value error-message">{selectedSong.error_message}</div>
                  </div>
                )}
              </div>
              {selectedSong.search_result?.length > 0 && (
                <>
                  <h4>搜索结果</h4>
                  {(() => {
                    const qq = selectedSong.search_result?.find((x) => x.source === 'qq') || { source: 'qq', items: [] }
                    const netease = selectedSong.search_result?.find((x) => x.source === 'netease') || { source: 'netease', items: [] }
                    const renderCol = (sr, title) => (
                      <div className="search-col">
                        <div className="search-col-header">{title}</div>
                        <div className="result-cards">
                          {(sr.items || []).map((item, idx) => {
                            const isBest = selectedSong.best_choice?.source === sr.source && selectedSong.best_choice?.index === idx
                            const extLabel = (item.ext || '').trim() ? `.${(item.ext || '').replace(/^\./, '')}` : ''
                            return (
                              <div key={idx} className={`result-card ${isBest ? 'best' : ''}`}>
                                <div className="result-card-main">
                                  <button
                                    type="button"
                                    className="result-play-btn"
                                    onClick={() => playPreview(selectedSong.id, sr.source, idx, item)}
                                    title="试听"
                                  >
                                    ▶
                                  </button>
                                  <div className="result-card-info">
                                    <span className="result-title">{item.song_name} — {item.singers}</span>
                                    <span className="result-meta">
                                      {item.duration}{item.file_size ? ` · ${item.file_size}` : ''}{extLabel ? ` · ${extLabel}` : ''}
                                    </span>
                                  </div>
                                </div>
                                <button
                                  type="button"
                                  className={`result-select-btn ${isBest ? 'selected' : ''}`}
                                  onClick={() => handleSelectChoice(selectedSong.id, sr.source, idx)}
                                >
                                  {isBest ? '已选择' : '设为最佳'}
                                </button>
                              </div>
                            )
                          })}
                          {(!sr.items || sr.items.length === 0) && (
                            <div className="empty-hint">暂无结果</div>
                          )}
                        </div>
                      </div>
                    )
                    return (
                      <div className="search-columns">
                        {renderCol(qq, 'QQ音乐')}
                        {renderCol(netease, '网易云音乐')}
                      </div>
                    )
                  })()}
                </>
              )}
            </>
          ) : (
            <p className="placeholder">左侧点击一首歌曲查看详情</p>
          )}
        </section>
      </div>

      <footer className="player-bar">
        <div className="player-meta">
          <div className="player-meta-line">
            <span className={`player-dot ${playerSrc ? 'active' : ''}`} />
            <span className="player-status">{playerSrc ? '正在播放' : '未在播放'}</span>
          </div>
          <div className="now-playing" title={playerTitle || '暂无正在播放的歌曲'}>
            {playerTitle || '暂无正在播放的歌曲'}
          </div>
        </div>
        <audio
          ref={audioRef}
          src={playerSrc || ''}
          controls
          className="audio-control"
          autoPlay
        />
      </footer>

      {showFolderPicker && (
        <FolderPicker onSelect={handleSelectFolder} onClose={() => setShowFolderPicker(false)} />
      )}
    </div>
  )
}

export default App
