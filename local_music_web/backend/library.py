# Library management: scan folder, load/save library JSON, browse filesystem
import os
import re
import hashlib
import json
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

from pathvalidate import sanitize_filename

# 避免并发读写同一库时读到半截或误判为 404
_library_io_lock = threading.Lock()

try:
    from mutagen import File as MutagenFile
except Exception:
    MutagenFile = None

from .models import (
    LibraryData,
    SongEntry,
    SearchTaskState,
    DownloadTaskState,
    SearchResultBySource,
    SearchResultItem,
    BestChoice,
)

# Supported audio extensions
AUDIO_EXT = {".mp3", ".flac", ".m4a", ".wav", ".aac", ".ogg"}

# Where to store library JSON files (relative to backend dir or absolute)
def _libraries_dir() -> str:
    base = Path(__file__).resolve().parent
    lib_dir = base.parent / "libraries"
    lib_dir.mkdir(parents=True, exist_ok=True)
    return str(lib_dir)


def _library_path(library_id: str) -> str:
    return os.path.join(_libraries_dir(), f"{library_id}.json")


def library_id_from_path(folder_path: str) -> str:
    normalized = os.path.normpath(os.path.abspath(folder_path))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def get_browse_roots() -> list[dict]:
    """Return list of root paths for folder picker (name, path, is_dir=True)."""
    roots = []
    if os.name == "nt":
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            p = f"{letter}:\\"
            if os.path.exists(p):
                roots.append({"name": p, "path": p, "is_dir": True})
    else:
        roots.append({"name": "/", "path": "/", "is_dir": True})
    return roots


def browse_path(path: str) -> list[dict]:
    """List directories (and optionally files) under path. Only dirs for folder picker."""
    if not path or not os.path.isdir(path):
        return []
    result = []
    try:
        for entry in sorted(Path(path).iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            try:
                name = entry.name
                full = str(entry.resolve())
                result.append({"name": name, "path": full, "is_dir": entry.is_dir()})
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        return []
    return result


def _read_audio_meta(file_path: str) -> tuple[str, str, Optional[float]]:
    """Return (song_name, singers, duration_seconds)."""
    song_name = ""
    singers = ""
    duration_seconds: Optional[float] = None
    if MutagenFile:
        try:
            f = MutagenFile(file_path)
            if f.tags:
                # Common tag names
                if hasattr(f.tags, "get"):
                    song_name = (f.tags.get("TIT2") or f.tags.get("\xa9nam") or f.tags.get("title")) or ""
                    if isinstance(song_name, list):
                        song_name = song_name[0] if song_name else ""
                    song_name = str(song_name).strip() if song_name else ""
                    artists = f.tags.get("TPE1") or f.tags.get("\xa9ART") or f.tags.get("artist") or ""
                    if isinstance(artists, list):
                        artists = ", ".join(str(a) for a in artists) if artists else ""
                    singers = str(artists).strip() if artists else ""
            if f.info and hasattr(f.info, "length") and f.info.length:
                duration_seconds = float(f.info.length)
        except Exception:
            pass
    if not song_name:
        song_name = Path(file_path).stem
    return song_name, singers, duration_seconds


def _duration_display(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0:
        return ""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def scan_folder(folder_path: str) -> LibraryData:
    """Scan folder for audio files, build or merge library. Preserves existing search/choice/download state by song id (file_path)."""
    folder_path = os.path.normpath(os.path.abspath(folder_path))
    if not os.path.isdir(folder_path):
        raise NotADirectoryError(folder_path)
    lib_id = library_id_from_path(folder_path)
    existing = load_library(lib_id) if os.path.exists(_library_path(lib_id)) else None

    songs_map: dict[str, SongEntry] = {}
    if existing and existing.folder_path == folder_path:
        for s in existing.songs:
            songs_map[s.id] = s

    unrecognized: list[str] = []
    for root, _dirs, files in os.walk(folder_path, topdown=True):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            full = os.path.join(root, f)
            if ext not in AUDIO_EXT:
                unrecognized.append(full)
                continue
            rel = os.path.relpath(full, folder_path)
            sid = hashlib.sha256(full.encode("utf-8")).hexdigest()[:12]
            if sid in songs_map:
                # refresh basic info, keep search/choice/download
                entry = songs_map[sid]
                song_name, singers, dur = _read_audio_meta(full)
                entry.file_path = full
                entry.file_name = f
                if song_name:
                    entry.song_name = song_name
                if singers:
                    entry.singers = singers
                if dur is not None:
                    entry.duration_seconds = dur
                    entry.duration_display = _duration_display(dur)
                continue
            song_name, singers, dur = _read_audio_meta(full)
            songs_map[sid] = SongEntry(
                id=sid,
                file_path=full,
                file_name=f,
                song_name=song_name or Path(f).stem,
                singers=singers or "",
                duration_seconds=dur,
                duration_display=_duration_display(dur),
                status="pending",
                search_result=[],
                best_choice=None,
                downloaded_at=None,
                error_message=None,
            )
    songs = list(songs_map.values())
    songs.sort(key=lambda x: (x.file_path.lower(),))

    search_task = existing.search_task if existing else SearchTaskState()
    download_task = existing.download_task if existing else DownloadTaskState()
    lib = LibraryData(
        library_id=lib_id,
        folder_path=folder_path,
        updated_at=datetime.utcnow().isoformat() + "Z",
        songs=songs,
        search_task=search_task,
        download_task=download_task,
        unrecognized_files=unrecognized[:500],
    )
    save_library(lib)
    return lib


def load_library(library_id: str) -> Optional[LibraryData]:
    path = _library_path(library_id)
    with _library_io_lock:
        if not os.path.exists(path):
            return None
        for attempt in range(2):
            try:
                with open(path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                return LibraryData(**data)
            except Exception:
                if attempt == 0:
                    import time
                    time.sleep(0.15)
                else:
                    return None
    return None


def save_library(lib: LibraryData) -> None:
    path = _library_path(lib.library_id)
    tmp = path + ".tmp"
    with _library_io_lock:
        with open(tmp, "w", encoding="utf-8") as fp:
            fp.write(lib.model_dump_json(indent=2, exclude_none=False))
        os.replace(tmp, path)


def list_libraries() -> list[dict]:
    """Return list of {library_id, folder_path, updated_at} for all stored libraries."""
    lib_dir = _libraries_dir()
    result = []
    for f in os.listdir(lib_dir):
        if not f.endswith(".json"):
            continue
        lib_id = f[:-5]
        lib = load_library(lib_id)
        if lib:
            result.append({
                "library_id": lib_id,
                "folder_path": lib.folder_path,
                "updated_at": lib.updated_at,
                "songs_count": len(lib.songs),
            })
    result.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return result
