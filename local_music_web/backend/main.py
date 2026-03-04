# FastAPI app: browse, scan, library, search control, download control, select choice
import os
import sys

# Project root for musicdl import when running from backend dir
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

from .models import (
    ScanFolderRequest,
    SearchControlRequest,
    DownloadControlRequest,
    SelectChoiceRequest,
    ResetDownloadsRequest,
    ResetSearchErrorsRequest,
    LibraryData,
    SongEntry,
    BestChoice,
)
from . import library
from . import search_task
from . import download_task
from . import pick_folder as pick_folder_module

app = FastAPI(title="Local Music Web API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----- Browse -----
@app.get("/api/local/browse/roots")
def browse_roots():
    return library.get_browse_roots()


@app.get("/api/local/browse")
def browse_path(path: str = ""):
    if not path:
        return library.get_browse_roots()
    return library.browse_path(path)


# ----- 系统级选择文件夹（会弹出系统对话框，请求会阻塞到用户选完或取消） -----
@app.post("/api/local/pick-folder")
def api_pick_folder():
    path = pick_folder_module.pick_folder()
    return {"path": path}


# ----- Library -----
@app.post("/api/local/scan")
def scan_folder(body: ScanFolderRequest):
    try:
        lib = library.scan_folder(body.path)
        return {"ok": True, "library_id": lib.library_id, "library": lib.model_dump()}
    except NotADirectoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/local/library-state")
def get_library_state(library_id: str):
    lib = library.load_library(library_id)
    if not lib:
        raise HTTPException(status_code=404, detail="library not found")
    # 若库文件里任务状态是 running，但实际没有在跑（例如上次 Ctrl+C 退出），则改回 idle
    if lib.search_task.status == "running" and not search_task.is_search_running_for(library_id):
        lib.search_task.status = "idle"
        library.save_library(lib)
    if lib.download_task.status == "running" and not download_task.is_download_running_for(library_id):
        lib.download_task.status = "idle"
        lib.download_task.current_song_name = None
        library.save_library(lib)
    return lib.model_dump()


@app.get("/api/local/library-list")
def get_library_list():
    return library.list_libraries()


# ----- Search -----
@app.post("/api/local/search-control")
def search_control_api(body: SearchControlRequest):
    out = search_task.search_control(body.library_id, body.action)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error", "error"))
    return out


@app.get("/api/local/task-status")
def get_task_status(library_id: str):
    lib = library.load_library(library_id)
    if not lib:
        raise HTTPException(status_code=404, detail="library not found")
    return {
        "search_task": lib.search_task.model_dump(),
        "download_task": lib.download_task.model_dump(),
    }


# ----- Select best choice -----
@app.post("/api/local/select-choice")
def select_choice(body: SelectChoiceRequest):
    lib = library.load_library(body.library_id)
    if not lib:
        raise HTTPException(status_code=404, detail="library not found")
    for entry in lib.songs:
        if entry.id != body.song_id:
            continue
        if body.source is None or body.index is None:
            entry.best_choice = None
            entry.status = "searched" if entry.search_result else "pending"
        else:
            for sr in entry.search_result:
                if sr.source != body.source:
                    continue
                if 0 <= body.index < len(sr.items):
                    item = sr.items[body.index]
                    raw = getattr(item, "raw", None) or {}
                    entry.best_choice = BestChoice(source=body.source, index=body.index, raw=raw)
                    entry.status = "selected"
                    break
        library.save_library(lib)
        return {"ok": True, "song": entry.model_dump()}
    raise HTTPException(status_code=404, detail="song not found")


# ----- Download -----
@app.post("/api/local/download-control")
def download_control_api(body: DownloadControlRequest):
    out = download_task.download_control(body.library_id, body.action)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error", "error"))
    return out


@app.get("/api/local/download-status")
def get_download_status(library_id: str):
    s = download_task.get_download_status(library_id)
    if s is None:
        raise HTTPException(status_code=404, detail="library not found")
    return s


# ----- Reset downloads -----
@app.post("/api/local/reset-search-errors")
def reset_search_errors(body: ResetSearchErrorsRequest):
    lib = library.load_library(body.library_id)
    if not lib:
        raise HTTPException(status_code=404, detail="library not found")
    n = 0
    for entry in lib.songs:
        if entry.status == "error":
            entry.status = "pending"
            entry.error_message = None
            n += 1
    library.save_library(lib)
    return {"ok": True, "reset_count": n}


@app.post("/api/local/reset-all-to-pending")
def reset_all_to_pending(body: ResetSearchErrorsRequest):
    """将所有歌曲状态改为待搜索（pending），清空搜索结果与错误，便于重新开始遍历搜索"""
    lib = library.load_library(body.library_id)
    if not lib:
        raise HTTPException(status_code=404, detail="library not found")
    for entry in lib.songs:
        entry.status = "pending"
        entry.search_result = []
        entry.best_choice = None
        entry.error_message = None
        entry.downloaded_at = None
    lib.search_task.status = "idle"
    lib.search_task.current_index = 0
    library.save_library(lib)
    return {"ok": True, "reset_count": len(lib.songs)}


@app.post("/api/local/reset-downloads")
def reset_downloads(body: ResetDownloadsRequest):
    lib = library.load_library(body.library_id)
    if not lib:
        raise HTTPException(status_code=404, detail="library not found")
    for entry in lib.songs:
        if entry.status == "downloaded":
            entry.status = "selected" if entry.best_choice else "searched" if entry.search_result else "pending"
            entry.downloaded_at = None
    library.save_library(lib)
    return {"ok": True}


# ----- Stream audio (for local playback) -----
def _media_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {"": "application/octet-stream", ".mp3": "audio/mpeg", ".flac": "audio/flac", ".m4a": "audio/mp4", ".wav": "audio/wav"}.get(ext, "application/octet-stream")


@app.get("/api/local/stream")
def stream_audio(library_id: str, song_id: str):
    lib = library.load_library(library_id)
    if not lib:
        raise HTTPException(status_code=404, detail="library not found")
    for entry in lib.songs:
        if entry.id == song_id and os.path.exists(entry.file_path):
            return FileResponse(entry.file_path, media_type=_media_type(entry.file_path))
    raise HTTPException(status_code=404, detail="file not found")


# ----- Preview search result (stream remote audio by proxy) -----
def _media_type_by_ext(ext: str) -> str:
    return {".mp3": "audio/mpeg", ".flac": "audio/flac", ".m4a": "audio/mp4", ".wav": "audio/wav"}.get(
        ("." + ext.lstrip(".")).lower(), "audio/mpeg"
    )


@app.get("/api/local/preview")
def preview_search_result(library_id: str, song_id: str, source: str, index: int):
    """Preview search result by HTTP redirect to remote audio URL (keeps seek / progress bar)."""
    lib = library.load_library(library_id)
    if not lib:
        raise HTTPException(status_code=404, detail="library not found")
    for entry in lib.songs:
        if entry.id != song_id:
            continue
        for sr in entry.search_result or []:
            if sr.source != source or not (0 <= index < len(sr.items)):
                continue
            item = sr.items[index]
            url = getattr(item, "download_url", None) or (item.raw or {}).get("download_url")
            if not url or not str(url).startswith("http"):
                raise HTTPException(status_code=404, detail="no preview url")
            # 302 重定向到真实音频 URL，让浏览器直接请求远程音频，支持拖拽/进度条
            return RedirectResponse(url=str(url), status_code=302)
    raise HTTPException(status_code=404, detail="song or result not found")


# Serve frontend in production (optional)
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="assets")
    @app.get("/{path:path}")
    def serve_spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        f = os.path.join(_frontend_dist, path)
        if path and os.path.isfile(f):
            return FileResponse(f)
        return FileResponse(os.path.join(_frontend_dist, "index.html"))
