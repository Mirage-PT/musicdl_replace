# Pydantic models and library data structures for local music web API
from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


# ----- API request/response -----
class ScanFolderRequest(BaseModel):
    path: str


class BrowseRequest(BaseModel):
    path: str = ""


class SearchControlRequest(BaseModel):
    library_id: str
    action: str  # start | pause | continue | stop


class DownloadControlRequest(BaseModel):
    library_id: str
    action: str  # start | pause | continue


class SelectChoiceRequest(BaseModel):
    library_id: str
    song_id: str
    source: Optional[str] = None  # "qq" | "netease"
    index: Optional[int] = None  # index in that source list; null = clear choice


class ResetDownloadsRequest(BaseModel):
    library_id: str


class ResetSearchErrorsRequest(BaseModel):
    library_id: str


# ----- Browse -----
class BrowseEntry(BaseModel):
    name: str
    path: str
    is_dir: bool


# ----- Library / Song (stored in JSON) -----
class SearchResultItem(BaseModel):
    song_name: str = ""
    singers: str = ""
    album: str = ""
    duration: str = ""
    file_size: str = ""
    ext: str = ""
    download_url: Optional[str] = None
    # For frontend: audition/preview link if any
    raw: dict = Field(default_factory=dict)  # full song_info.todict() for download


class SearchResultBySource(BaseModel):
    source: str  # "qq" | "netease"
    items: list[SearchResultItem] = Field(default_factory=list)


class BestChoice(BaseModel):
    source: str
    index: int
    raw: dict  # SongInfo.todict() for download


class SongEntry(BaseModel):
    id: str = ""
    file_path: str = ""
    file_name: str = ""
    song_name: str = ""
    singers: str = ""
    duration_seconds: Optional[float] = None
    duration_display: str = ""
    status: str = "pending"  # pending | searched | selected | downloaded | error
    search_result: list[SearchResultBySource] = Field(default_factory=list)
    best_choice: Optional[BestChoice] = None
    downloaded_at: Optional[str] = None
    error_message: Optional[str] = None


class SearchTaskState(BaseModel):
    status: str = "idle"  # idle | running | paused
    current_index: int = 0
    total: int = 0


class DownloadTaskState(BaseModel):
    status: str = "idle"
    current_index: int = 0
    total: int = 0
    completed_count: int = 0
    current_song_name: Optional[str] = None  # 正在下载的歌曲，如 "歌名 - 歌手"


class LibraryData(BaseModel):
    library_id: str = ""
    folder_path: str = ""
    updated_at: str = ""
    songs: list[SongEntry] = Field(default_factory=list)
    search_task: SearchTaskState = Field(default_factory=SearchTaskState)
    download_task: DownloadTaskState = Field(default_factory=DownloadTaskState)
    unrecognized_files: list[str] = Field(default_factory=list)
