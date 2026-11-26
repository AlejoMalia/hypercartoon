"""Universal learning input. Anything that can lead to video is an input: local files / folders / globs, direct URLs (http, ftp,
HLS .m3u8, DASH .mpd), YouTube / Vimeo / Archive.org / Twitch ... videos, playlists and channels (via yt-dlp), lists of URLs
(.txt .csv .json .m3u), open directories (HTML index pages), RSS feeds, cloud share links (Dropbox, Google Drive, GitHub, S3, GCS,
IPFS), live streams (rtsp / rtmp / udp / srt, with a time limit) and torrents / magnet links.

How the "no full download" goal is met: remote material is read ONCE through ffmpeg and only a compact local *proxy*
(default 480 p H.264 + AAC, the engine's training height) is kept; the original is never stored (torrents have to fetch the bytes
but the original file is deleted right after its proxy is made). Everything downstream (analysis, characters, voices, dataset)
then works on those proxies, with seasons/episodes inferred from the names this module gives them.
Not supported: DRM-protected streams (Netflix, Disney+ ...). Using material you have no rights to is your responsibility."""
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from studio import corpus as C
from studio.ingest import VIDEO_EXT, list_videos

AUDIO_EXT = (".wav", ".mp3", ".flac", ".m4a", ".ogg", ".opus", ".aac", ".wma", ".aiff")
URL_VIDEO_EXT = VIDEO_EXT + (".ts", ".m2ts", ".flv", ".mpg", ".mpeg", ".wmv", ".3gp", ".ogv")
YTDLP_HOSTS = ("youtube.com", "youtu.be", "vimeo.com", "dailymotion.com", "twitch.tv", "archive.org", "bilibili.com", "tiktok.com",
               "facebook.com", "instagram.com", "twitter.com", "x.com", "reddit.com", "rumble.com", "odysee.com", "ok.ru",
               "nicovideo.jp", "peertube.tv", "bitchute.com", "vk.com", "streamable.com", "ted.com", "pbs.org", "rtve.es")
LIVE_SCHEMES = ("rtsp", "rtsps", "rtmp", "rtmps", "rtmpe", "udp", "srt", "rtp", "mms", "mmsh")
LIST_EXT = (".txt", ".csv", ".json", ".m3u", ".lst", ".list")
FEED_EXT = (".rss", ".xml", ".atom")
SAMPLE_BYTES = 80 * 1024 * 1024


def list_media(path: str, audio: bool = False):
    """Video files (and audio files when `audio`) under a folder, or the file itself."""
    if os.path.isfile(path):
        return [path]
    ext = VIDEO_EXT + (AUDIO_EXT if audio else ())
    return sorted(os.path.join(r, f) for r, _, fs in os.walk(path) for f in sorted(fs) if f.lower().endswith(ext))


class SourceError(RuntimeError):
    pass


@dataclass
class Options:
    name: str = ""                      # series name (default: inferred from the input)
    proxy_height: int = 480             # kept local height; the engine trains at 480
    keep: str = "proxy"                 # proxy = small re-encode | full = lossless remux/original quality
    max_seconds: float = 0.0            # only the first N seconds of every item (0 = all); required for live streams
    max_gb: float = 0.0                 # stop fetching when the sources folder reaches this size (0 = no limit)
    crf: int = 23
    cookies: str = ""                   # cookies.txt for yt-dlp (age/region/login gated material you are allowed to see)
    headers: Dict[str, str] = field(default_factory=dict)
    user_agent: str = "Mozilla/5.0 (hypercartoon)"
    retries: int = 2
    timeout: float = 20.0
    keep_torrent_original: bool = False
    audio_only: bool = False            # keep only the soundtrack (voice libraries): .wav 24 kHz mono instead of a video proxy
    fetch_workers: int = 4              # online videos are read in parallel (one ffmpeg each); a single YouTube stream arrives at ~2x real time
    live_default_seconds: float = 300.0
    # hooks (tests and advanced use): ytdlp_factory(opts)->obj.extract_info(url, download=False); torrent_backend; fetch_text(url)->str
    ytdlp_factory: Optional[Callable] = None
    torrent_backend: Optional[object] = None
    fetch_text: Optional[Callable] = None
    probe: Optional[Callable] = None


@dataclass
class Item:
    uri: str                            # what to read: path, URL or magnet
    kind: str                           # local | http | stream | live | ytdlp | torrent
    title: str = ""
    rel: str = ""                       # output path under the sources folder ("" = use as is)
    season: int = 0
    episode: int = 0
    extra: dict = field(default_factory=dict)


@dataclass
class Prepared:
    root: str
    paths: List[str]
    records: List[dict]
    errors: List[str]
    remote: bool

    def summary(self) -> str:
        return f"{len(self.paths)} vídeo(s) listos" + (f", {len(self.errors)} con error" if self.errors else "")


# ---- classification -------------------------------------------------------------------------------------------
def slug(s: str, n: int = 60) -> str:
    s = re.sub(r"[^\w\-. ]+", "", s, flags=re.U).strip().replace(" ", "_")
    return re.sub(r"_+", "_", s)[:n].strip("._") or "item"


def _host(url: str) -> str:
    h = urllib.parse.urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    return h[4:] if h.startswith("www.") else h


def normalize(entry: str) -> str:
    """Rewrite share/storage links to something a plain GET (or ffmpeg) can read."""
    s = entry.strip().strip("'\"")
    p = urllib.parse.urlparse(s)
    sc = p.scheme.lower()
    if sc == "ipfs":
        return "https://ipfs.io/ipfs/" + (p.netloc + p.path).lstrip("/")
    if sc == "s3":
        return f"https://{p.netloc}.s3.amazonaws.com/{p.path.lstrip('/')}"
    if sc == "gs":
        return f"https://storage.googleapis.com/{p.netloc}/{p.path.lstrip('/')}"
    if sc == "file":
        return urllib.parse.unquote(p.path)
    h = _host(s)
    if h == "dropbox.com":
        q = dict(urllib.parse.parse_qsl(p.query))
        q["dl"] = "1"
        return p._replace(netloc="www.dropbox.com", query=urllib.parse.urlencode(q)).geturl()
    if h == "drive.google.com":
        m = re.search(r"/file/d/([\w-]+)", p.path) or re.search(r"[?&]id=([\w-]+)", s)
        if m:
            return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    if h == "github.com" and "/blob/" in p.path:
        return "https://raw.githubusercontent.com" + p.path.replace("/blob/", "/", 1)
    return s


def _probe_type(url: str, o: "Options") -> str:
    if o.probe:
        return o.probe(url)
    hdr = {"User-Agent": o.user_agent, **o.headers}
    for method, extra in (("HEAD", {}), ("GET", {"Range": "bytes=0-0"})):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method=method, headers={**hdr, **extra}), timeout=o.timeout) as r:
                return (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        except Exception:
            continue
    return ""


def classify(entry: str, o: Optional["Options"] = None) -> str:
    """-> local | torrent | live | http | stream | ytdlp | list | feed | page"""
    o = o or Options()
    s = normalize(entry)
    low = s.lower().split("?")[0].split("#")[0]
    if s.lower().startswith("magnet:") or low.endswith(".torrent"):
        return "torrent"
    p = urllib.parse.urlparse(s)
    sc = p.scheme.lower()
    if len(sc) <= 1 or sc not in ("http", "https", "ftp", "ftps", "sftp") + LIVE_SCHEMES:
        return "local"
    if sc in LIVE_SCHEMES:
        return "live"
    h = _host(s)
    if any(h == x or h.endswith("." + x) for x in YTDLP_HOSTS):
        return "ytdlp"
    path = p.path.lower()
    if path.endswith((".m3u8", ".mpd")):
        return "stream"
    if path.endswith(URL_VIDEO_EXT + AUDIO_EXT):
        return "http"
    if path.endswith(LIST_EXT):
        return "list"
    if path.endswith(FEED_EXT):
        return "feed"
    ct = _probe_type(s, o)
    if ct.startswith("video/") or ct in ("application/octet-stream", "binary/octet-stream"):
        return "http"
    if ct in ("application/vnd.apple.mpegurl", "application/x-mpegurl", "application/dash+xml"):
        return "stream"
    if "xml" in ct or "rss" in ct or "atom" in ct:
        return "feed"
    if ct in ("text/plain", "application/json", "text/csv"):
        return "list"
    return "page"


# ---- text helpers ---------------------------------------------------------------------------------------------
def fetch_text(url: str, o: Options, limit: int = 8_000_000) -> str:
    if o.fetch_text:
        return o.fetch_text(url)
    req = urllib.request.Request(url, headers={"User-Agent": o.user_agent, **o.headers})
    with urllib.request.urlopen(req, timeout=o.timeout) as r:
        return r.read(limit).decode(r.headers.get_content_charset() or "utf-8", "replace")


def read_list(text: str, name: str = "") -> List[dict]:
    """A list file -> [{'uri', 'title', 'season', 'episode'}]. Formats: one entry per line (`# comment`, `uri  # title`,
    `uri | title`), CSV with a header (url/uri/link, title/name, season, episode), JSON (strings or objects), M3U / M3U8 playlists."""
    t = text.lstrip("﻿")
    s = t.strip()
    low = name.lower()
    out: List[dict] = []
    if s[:1] in "[{" or low.endswith(".json"):
        data = json.loads(s)
        data = data.get("items") or data.get("videos") or data.get("urls") or [] if isinstance(data, dict) else data
        for d in data:
            if isinstance(d, str):
                out.append({"uri": d})
            elif isinstance(d, dict):
                u = d.get("url") or d.get("uri") or d.get("link") or d.get("path")
                if u:
                    out.append({"uri": u, "title": d.get("title") or d.get("name") or "", "season": int(d.get("season") or 0), "episode": int(d.get("episode") or 0)})
        return out
    if s.startswith("#EXTM3U") or low.endswith(".m3u"):
        title = ""
        for ln in t.splitlines():
            ln = ln.strip()
            if ln.startswith("#EXTINF"):
                title = ln.split(",", 1)[-1].strip()
            elif ln and not ln.startswith("#"):
                out.append({"uri": ln, "title": title})
                title = ""
        return out
    lines = [ln.strip() for ln in t.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if low.endswith(".csv") and lines and not re.match(r"\w+://|magnet:", lines[0]):
        import csv
        import io

        for row in csv.DictReader(io.StringIO("\n".join(lines))):
            r = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            u = r.get("url") or r.get("uri") or r.get("link") or r.get("path")
            if u:
                out.append({"uri": u, "title": r.get("title") or r.get("name") or "", "season": int(r.get("season") or 0),
                            "episode": int(r.get("episode") or 0)})
        return out
    for ln in lines:
        ttl = ""
        for sep in (" | ", "  # ", "\t"):
            if sep in ln:
                ln, ttl = [x.strip() for x in ln.split(sep, 1)]
                break
        out.append({"uri": ln, "title": ttl})
    return out


def _links(page: str) -> List[str]:
    return [html.unescape(h) for h in re.findall(r"""href\s*=\s*["']([^"'#]+)["']""", page, flags=re.I)]


def index_videos(url: str, o: Options, depth: int = 3, seen: Optional[set] = None) -> List[Tuple[str, str]]:
    """Open directory listing (Apache / nginx / python http.server style): [(video url, relative path)] walking sub-folders."""
    seen = seen if seen is not None else set()
    if url in seen or depth < 0:
        return []
    seen.add(url)
    base = url if url.endswith("/") else url + "/"
    found: List[Tuple[str, str]] = []
    for h in _links(fetch_text(base, o)):
        if h.startswith(("?", "mailto:", "javascript:")) or h in ("../", "./", "/"):
            continue
        full = urllib.parse.urljoin(base, h)
        if not full.startswith(base):  # never leave the listing
            continue
        rel = urllib.parse.unquote(full[len(base):])
        if full.lower().split("?")[0].endswith(URL_VIDEO_EXT):
            found.append((full, rel))
        elif full.endswith("/"):
            found += [(u, urllib.parse.unquote(h.rstrip("/")) + "/" + r) for u, r in index_videos(full, o, depth - 1, seen)]
    return sorted(found, key=lambda x: x[1])


def feed_videos(text: str) -> Tuple[str, List[dict]]:
    """RSS / Atom: (feed title, [{'uri', 'title'}]) of enclosures that are video (or have a video extension)."""
    title = html.unescape((re.search(r"<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", text, re.S) or [None, ""])[1]).strip()
    out = []
    for blk in re.findall(r"<(?:item|entry)\b.*?</(?:item|entry)>", text, re.S):
        t = html.unescape((re.search(r"<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", blk, re.S) or [None, ""])[1]).strip()
        for m in re.finditer(r"<(?:enclosure|link|media:content)\b[^>]*>", blk, re.S):
            tag = m.group(0)
            u = re.search(r"""(?:url|href)\s*=\s*["']([^"']+)["']""", tag)
            ty = re.search(r"""type\s*=\s*["']([^"']+)["']""", tag)
            if u and ((ty and ty.group(1).startswith("video")) or u.group(1).lower().split("?")[0].endswith(URL_VIDEO_EXT)):
                out.append({"uri": html.unescape(u.group(1)), "title": t})
                break
    return title, out


# ---- yt-dlp ---------------------------------------------------------------------------------------------------
class _Quiet:
    """yt-dlp prints errors itself; the studio reports them in the panel instead."""

    def debug(self, m): ...
    def info(self, m): ...
    def warning(self, m): ...
    def error(self, m): ...


def _ytdlp(o: Options, extra: dict):
    base = {"quiet": True, "no_warnings": True, "skip_download": True, "logger": _Quiet()}
    if o.cookies:
        base["cookiefile"] = o.cookies
    base.update(extra)
    if o.ytdlp_factory:
        return o.ytdlp_factory(base)
    try:
        import yt_dlp
    except Exception as e:
        raise SourceError("falta yt-dlp para YouTube, listas de reproducción y otras webs: pip install yt-dlp") from e
    return yt_dlp.YoutubeDL(base)


def _entry_url(e: dict) -> str:
    u = e.get("webpage_url") or e.get("url") or ""
    if u and not re.match(r"\w+://", u) and e.get("id"):
        u = f"https://www.youtube.com/watch?v={e['id']}"
    return u or (f"https://www.youtube.com/watch?v={e['id']}" if e.get("id") else "")


def ytdlp_expand(url: str, o: Options, depth: int = 2) -> Tuple[str, List[List[dict]]]:
    """-> (title, groups) where a group is one playlist's entries [{'uri','title','index'}]; a channel yields several groups."""
    info = _ytdlp(o, {"extract_flat": "in_playlist"}).extract_info(url, download=False)
    if not info:
        raise SourceError(f"yt-dlp no devolvió nada para {url}")
    title = info.get("title") or ""
    if info.get("_type") != "playlist" and not info.get("entries"):
        return title, [[{"uri": _entry_url(info) or url, "title": title, "index": 1, "duration": info.get("duration")}]]
    entries = [e for e in (info.get("entries") or []) if e]
    if entries and all(e.get("_type") == "playlist" or e.get("ie_key") in ("YoutubeTab",) for e in entries) and depth > 0:
        groups = []
        for e in entries:
            sub_t, sub = ytdlp_expand(_entry_url(e), o, depth - 1)
            for g in sub:
                for it in g:
                    it["group"] = e.get("title") or sub_t
            groups += sub
        return title, groups
    return title, [[{"uri": _entry_url(e), "title": e.get("title") or "", "index": e.get("playlist_index") or i, "duration": e.get("duration")}
                    for i, e in enumerate(entries, 1) if _entry_url(e)]]


def ytdlp_resolve(url: str, o: Options) -> Tuple[List[Tuple[str, dict]], float]:
    """Direct media URL(s) (+ headers) for one video, within the proxy height; video and audio may be separate inputs."""
    h = o.proxy_height if o.keep == "proxy" else 0
    fmt = "ba/b" if o.audio_only else f"bv*[height<={h}]+ba/b[height<={h}]/b" if h else "bv*+ba/b"
    try:
        info = _ytdlp(o, {"format": fmt, "noplaylist": True}).extract_info(url, download=False)
    except SourceError:
        raise
    except Exception as e:  # yt-dlp's DownloadError: unavailable / removed / private / geo-blocked ...
        raise SourceError(re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*[\w-]+:\s*)?", "", str(e)).strip()[:200]) from e
    if not info:
        raise SourceError(f"yt-dlp no pudo resolver {url}")
    if info.get("_has_drm") or any(f.get("has_drm") for f in info.get("formats") or []):
        raise SourceError("protegido con DRM: no se puede leer")
    fs = info.get("requested_formats") or [info]
    ins = [(f["url"], f.get("http_headers") or {}) for f in fs if f.get("url")]
    if not ins:
        raise SourceError(f"yt-dlp no encontró un flujo para {url}")
    return ins, float(info.get("duration") or 0)


# ---- torrents -------------------------------------------------------------------------------------------------
def torrent_video_files(files: List[Tuple[int, str, int]]) -> List[Tuple[int, str, int]]:
    """Keep video files, drop samples / trailers / extras."""
    keep = []
    for i, path, size in files:
        low = path.lower()
        if not low.endswith(VIDEO_EXT + (".ts", ".m2ts", ".flv", ".mpg", ".mpeg", ".wmv", ".ogv")):
            continue
        if re.search(r"(^|[/\\._ -])(sample|trailer|extras?|featurette)([/\\._ -]|$)", low) and size < SAMPLE_BYTES * 4:
            continue
        keep.append((i, path, size))
    return keep


class LibtorrentBackend:
    """pip install libtorrent. Metadata first, then only the chosen file is requested, sequentially."""

    def __init__(self, tmp: str, timeout: float = 240.0):
        import libtorrent as lt

        self.lt, self.tmp, self.timeout = lt, tmp, timeout
        self.ses = lt.session({"listen_interfaces": "0.0.0.0:6881"})

    def _add(self, uri: str, save: str):
        lt = self.lt
        p = lt.parse_magnet_uri(uri) if uri.lower().startswith("magnet:") else lt.add_torrent_params()
        if not uri.lower().startswith("magnet:"):
            p.ti = lt.torrent_info(uri)
        p.save_path = save
        return self.ses.add_torrent(p)

    def files(self, uri: str):
        os.makedirs(self.tmp, exist_ok=True)
        h, t0 = self._add(uri, self.tmp), time.time()
        while not h.status().has_metadata:
            if time.time() - t0 > self.timeout:
                self.ses.remove_torrent(h)
                raise SourceError("el torrent no devolvió metadatos (sin semillas o magnet inválido)")
            time.sleep(0.5)
        ti = h.torrent_file()
        fs = ti.files()
        out = [(i, fs.file_path(i), fs.file_size(i)) for i in range(fs.num_files())]
        self.ses.remove_torrent(h)
        return out

    def fetch(self, uri: str, index: int, dest_dir: str, progress=None) -> str:
        os.makedirs(dest_dir, exist_ok=True)
        h = self._add(uri, dest_dir)
        t0 = time.time()
        while not h.status().has_metadata:
            if time.time() - t0 > self.timeout:
                raise SourceError("el torrent no devolvió metadatos")
            time.sleep(0.5)
        ti = h.torrent_file()
        n = ti.files().num_files()
        h.prioritize_files([4 if i == index else 0 for i in range(n)])
        h.set_flags(self.lt.torrent_flags.sequential_download)
        size, path = ti.files().file_size(index), ti.files().file_path(index)
        last, stalled = 0, time.time()
        while h.file_progress()[index] < size:
            cur = h.file_progress()[index]
            if cur > last:
                last, stalled = cur, time.time()
            elif time.time() - stalled > self.timeout:
                self.ses.remove_torrent(h)
                raise SourceError("la descarga del torrent está parada (sin semillas)")
            progress and progress(cur / max(size, 1))
            time.sleep(1.0)
        self.ses.remove_torrent(h)
        return os.path.join(dest_dir, path)


_ARIA_FILE = re.compile(r"^\s*(\d+)\|(.+?)\s*$")
_ARIA_SIZE = re.compile(r"^\s*\|.*\(([\d,]+)\)\s*$")


def parse_aria2_listing(text: str) -> List[Tuple[int, str, int]]:
    """Output of `aria2c -S file.torrent` -> [(index, path, bytes)]."""
    out, cur = [], None
    for ln in text.splitlines():
        m = _ARIA_FILE.match(ln)
        if m and not ln.lstrip().startswith("|"):
            cur = (int(m.group(1)), re.sub(r"^\./", "", m.group(2)))
            continue
        s = _ARIA_SIZE.match(ln)
        if s and cur:
            out.append((cur[0], cur[1], int(s.group(1).replace(",", ""))))
            cur = None
    return out


class Aria2Backend:
    """aria2c on PATH (brew install aria2). Used when libtorrent is not installed."""

    def __init__(self, tmp: str, timeout: float = 240.0):
        self.exe, self.tmp, self.timeout = shutil.which("aria2c"), tmp, timeout
        if not self.exe:
            raise SourceError("no hay backend de torrents: pip install libtorrent  o  brew/apt install aria2")

    def _torrent_file(self, uri: str) -> str:
        os.makedirs(self.tmp, exist_ok=True)
        if not uri.lower().startswith("magnet:"):
            return uri
        before = set(os.listdir(self.tmp))
        r = subprocess.run([self.exe, "--bt-metadata-only=true", "--bt-save-metadata=true", "--seed-time=0", "-d", self.tmp, uri],
                           capture_output=True, text=True, timeout=self.timeout)
        new = [f for f in os.listdir(self.tmp) if f.endswith(".torrent") and f not in before] or [f for f in os.listdir(self.tmp) if f.endswith(".torrent")]
        if r.returncode != 0 or not new:
            raise SourceError("aria2c no obtuvo los metadatos del magnet")
        return os.path.join(self.tmp, new[0])

    def files(self, uri: str):
        t = self._torrent_file(uri)
        r = subprocess.run([self.exe, "-S", t], capture_output=True, text=True, timeout=60)
        fl = parse_aria2_listing(r.stdout)
        if not fl:
            raise SourceError("no pude leer la lista de ficheros del torrent")
        return fl

    def fetch(self, uri: str, index: int, dest_dir: str, progress=None) -> str:
        t = self._torrent_file(uri)
        files = dict((i, p) for i, p, _ in self.files(uri))
        os.makedirs(dest_dir, exist_ok=True)
        pr = subprocess.Popen([self.exe, f"--select-file={index}", "--seed-time=0", "--file-allocation=none", "--summary-interval=1",
                               "--bt-stop-timeout=%d" % int(self.timeout), "-d", dest_dir, t], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for ln in pr.stdout:
            m = re.search(r"\((\d+)%\)", ln)
            if m and progress:
                progress(int(m.group(1)) / 100)
        if pr.wait() != 0:
            raise SourceError("aria2c falló descargando el fichero del torrent")
        return os.path.join(dest_dir, files[index])


def get_torrent_backend(o: Options, tmp: str):
    if o.torrent_backend:
        return o.torrent_backend
    try:
        return LibtorrentBackend(tmp)
    except ImportError:
        return Aria2Backend(tmp)


# ---- expansion ------------------------------------------------------------------------------------------------
class Resolver:
    def __init__(self, o: Optional[Options] = None, ws: str = "."):
        self.o, self.ws = o or Options(), ws
        self._backend = None

    def backend(self):
        if self._backend is None:
            self._backend = get_torrent_backend(self.o, os.path.join(self.ws, "sources", "_torrents"))
        return self._backend

    # one entry -> (group title, [Item])  (each group is a "season" candidate)
    def expand_entry(self, entry: str, depth: int = 0) -> List[Tuple[str, List[Item]]]:
        o, e = self.o, entry.strip().strip("'\"")
        if not e:
            return []
        kind = classify(e, o)
        e = normalize(e)
        if kind == "local":
            return self._local(os.path.expanduser(e))
        if kind == "live":
            return [("", [Item(e, "live", title=_host(e) or "live")])]
        if kind in ("http", "stream"):
            return [("", [Item(e, kind, title=os.path.splitext(os.path.basename(urllib.parse.urlparse(e).path))[0] or _host(e))])]
        if kind == "ytdlp":
            title, groups = ytdlp_expand(e, o)
            res = []
            for g in groups:
                gt = (g[0].get("group") if g and g[0].get("group") else title) if len(groups) > 1 else title
                res.append((gt, [Item(d["uri"], "ytdlp", title=d.get("title") or "", episode=0,
                                      extra={"index": d.get("index"), "duration": d.get("duration")}) for d in g]))
            return res
        if kind in ("list", "feed", "page") and depth > 2:
            raise SourceError(f"listas anidadas demasiado profundas: {e}")
        if kind == "list":
            text = fetch_text(e, o) if re.match(r"\w+://", e) else open(e, encoding="utf-8").read()
            return self._from_list(read_list(text, e), os.path.basename(e), depth)
        if kind == "feed":
            ft, items = feed_videos(fetch_text(e, o))
            if not items:
                raise SourceError(f"el feed no contiene vídeos: {e}")
            return [(ft, [Item(i["uri"], classify(i["uri"], o), title=i["title"]) for i in items])]
        if kind == "page":
            vids = index_videos(e, o)
            if vids:
                gt = urllib.parse.unquote(e.rstrip("/").rsplit("/", 1)[-1])
                return [(gt, [Item(u, "http", title=os.path.splitext(os.path.basename(r))[0], rel=_mp4(r)) for u, r in vids])]
            try:  # a normal web page with embedded video: let yt-dlp's generic extractor try
                title, groups = ytdlp_expand(e, o)
                return [(title, [Item(d["uri"], "ytdlp", title=d["title"]) for g in groups for d in g])]
            except SourceError:
                raise
            except Exception as ex:
                raise SourceError(f"no encuentro vídeo en la página {e} ({ex})")
        if kind == "torrent":
            return self._torrent(e)
        raise SourceError(f"entrada no reconocida: {entry}")

    def _local(self, p: str) -> List[Tuple[str, List[Item]]]:
        import glob

        if any(ch in p for ch in "*?[") and not os.path.exists(p):
            hits = sorted(glob.glob(p, recursive=True))
            if not hits:
                raise SourceError(f"el patrón no encuentra nada: {p}")
            return [x for h in hits for x in self._local(h)]
        if not os.path.exists(p):
            raise SourceError(f"no existe: {p}")
        if os.path.isdir(p):
            top = os.path.basename(os.path.abspath(p).rstrip("/"))
            vids = list_media(p, self.o.audio_only)
            return [(top, [Item(v, "local", title=os.path.splitext(os.path.basename(v))[0], rel=_mp4(os.path.join(top, os.path.relpath(v, p)), keep_ext=True)) for v in vids])]
        if p.lower().endswith(LIST_EXT):
            return self._from_list(read_list(open(p, encoding="utf-8").read(), p), os.path.basename(p), 0)
        return [("", [Item(os.path.abspath(p), "local", title=os.path.splitext(os.path.basename(p))[0])])]

    def _from_list(self, rows: List[dict], name: str, depth: int) -> List[Tuple[str, List[Item]]]:
        base = os.path.splitext(name)[0]
        simple, groups = [], []
        for r in rows:
            sub = self.expand_entry(r["uri"], depth + 1)
            single = len(sub) == 1 and len(sub[0][1]) == 1 and not sub[0][1][0].rel
            for gt, items in sub:
                if single:
                    it = items[0]
                    it.title = r.get("title") or it.title
                    it.season, it.episode = r.get("season", 0), r.get("episode", 0)
                    simple.append(it)
                else:
                    groups.append((gt, items))
        return ([(base, simple)] if simple else []) + groups

    def _torrent(self, uri: str) -> List[Tuple[str, List[Item]]]:
        if re.match(r"https?://", uri, re.I):  # a remote .torrent file
            d = os.path.join(self.ws, "sources", "_torrents")
            os.makedirs(d, exist_ok=True)
            dst = os.path.join(d, hashlib.sha1(uri.encode()).hexdigest()[:12] + ".torrent")
            if not os.path.exists(dst):
                req = urllib.request.Request(uri, headers={"User-Agent": self.o.user_agent})
                with urllib.request.urlopen(req, timeout=self.o.timeout) as r, open(dst, "wb") as f:
                    shutil.copyfileobj(r, f)
            uri = dst
        files = torrent_video_files(self.backend().files(uri))
        if not files:
            raise SourceError("el torrent no contiene vídeos")
        top = ""
        m = re.search(r"[?&]dn=([^&]+)", uri)
        if m:
            top = urllib.parse.unquote_plus(m.group(1))
        return [(top, [Item(uri, "torrent", title=os.path.splitext(os.path.basename(p))[0], rel=_mp4(p),
                            extra={"index": i, "size": s, "torrent_path": p}) for i, p, s in files])]

    # all entries -> flat Items with final rel/season/episode
    def resolve(self, entries: List[str]) -> List[Item]:
        groups: List[Tuple[str, List[Item]]] = []
        singles: List[Item] = []
        for e in entries:
            for gt, items in self.expand_entry(e):
                if len(items) == 1 and not items[0].rel and not gt:
                    singles.append(items[0])
                else:
                    groups.append((gt, items))
        if singles:
            groups.insert(0, ("", singles))
        return self._name(groups)

    def _name(self, groups: List[Tuple[str, List[Item]]]) -> List[Item]:
        o = self.o
        first = next((g for g, _ in groups if g), "")
        remote = [it for _, its in groups for it in its if it.kind != "local"]
        series = slug(o.name or first or (f"online_{_host(remote[0].uri) or 'fuente'}" if remote else "local"), 50)
        out, next_season = [], 1
        multi = len([1 for _, its in groups if its]) > 1
        for gt, items in groups:
            if not items:
                continue
            hint = C._SEASON.search(gt or "") if gt and len(gt) <= 40 else None
            gseason = int(hint.group(1)) if hint else 0
            if not gseason:
                gseason = next_season if multi else 1
            next_season = max(next_season, gseason) + 1
            # episode numbers: explicit > title hint > order, falling back to order when hints collide
            nums = []
            for k, it in enumerate(items, 1):
                ses, ep = it.season, it.episode
                m = C._SXE.search(it.title)
                if m and not ep:
                    ses, ep = int(m.group(1) or m.group(3)), int(m.group(2) or m.group(4))
                elif not ep and (me := C._EP.search(it.title)):
                    ep = int(me.group(1))
                if not ep and it.extra.get("index"):
                    ep = int(it.extra["index"])
                nums.append((ses or gseason, ep or k))
            if len(set(nums)) != len(nums):
                nums = [(s, k) for k, (s, _) in enumerate(nums, 1)]
            for it, (ses, ep) in zip(items, nums):
                it.season, it.episode = ses, ep
                if not it.rel:
                    it.rel = f"{series}/S{ses:02d}/S{ses:02d}E{ep:03d}_{slug(it.title)}.mp4"
                elif it.kind != "local":  # keep a real top-level show folder, otherwise put it under the series
                    parts = it.rel.replace("\\", "/").split("/")
                    if len(parts) == 1 or C._SEASON.fullmatch(parts[0]):
                        it.rel = f"{slug(o.name) if o.name else slug(gt or series, 50)}/{it.rel}"
                out.append(it)
        if o.audio_only:
            for it in out:
                if it.kind != "local":
                    it.rel = re.sub(r"\.\w+$", ".wav", it.rel)
        seen = set()
        for it in out:  # two items must never share an output file
            base = it.rel
            n = 1
            while it.rel in seen:
                n += 1
                it.rel = re.sub(r"(\.\w+)$", rf"_{n}\1", base)
            seen.add(it.rel)
        return out


def _mp4(rel: str, keep_ext: bool = False) -> str:
    rel = rel.replace("\\", "/")
    return rel if keep_ext else os.path.splitext(rel)[0] + ".mp4"


# ---- fetching -------------------------------------------------------------------------------------------------
def _ff() -> str:
    from studio.audio import _ffmpeg

    return _ffmpeg()


def probe_duration(inp: str, headers: Optional[dict] = None) -> float:
    cmd = [_ff(), "-hide_banner"] + _net_in(inp, headers or {}, Options()) + ["-i", inp]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception:
        return 0.0
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def _net_in(url: str, headers: dict, o: Options) -> List[str]:
    sc = urllib.parse.urlparse(url).scheme.lower()
    a: List[str] = []
    if sc in ("http", "https"):
        a += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5", "-rw_timeout", "30000000", "-user_agent", o.user_agent]
        hh = {**o.headers, **(headers or {})}
        hh.pop("User-Agent", None)
        if hh:
            a += ["-headers", "".join(f"{k}: {v}\r\n" for k, v in hh.items())]
    elif sc in ("rtsp", "rtsps"):
        a += ["-rtsp_transport", "tcp", "-rw_timeout", "30000000"]
    return a


def build_ffmpeg_cmd(inputs: List[Tuple[str, dict]], out_tmp: str, o: Options, live: bool = False, hls: bool = False) -> List[str]:
    """One ffmpeg pass: read the remote stream(s), keep a proxy (or a lossless remux), write the local file."""
    cmd = [_ff(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin", "-progress", "pipe:1", "-nostats"]
    for url, hdr in inputs:
        cmd += _net_in(url, hdr, o) + ["-i", url]
    if o.audio_only:
        limit = o.max_seconds or (o.live_default_seconds if live else 0)
        return cmd + (["-t", f"{limit:g}"] if limit else []) + ["-vn", "-sn", "-dn", "-map", f"{len(inputs) - 1}:a:0", "-ac", "1", "-ar", "24000",
                                                                  "-c:a", "pcm_s16le", "-f", "wav", out_tmp]
    if len(inputs) == 2:
        cmd += ["-map", "0:v:0", "-map", "1:a:0?"]
    else:
        cmd += ["-map", "0:v:0", "-map", "0:a:0?"]
    cmd += ["-sn", "-dn"]
    limit = o.max_seconds or (o.live_default_seconds if live else 0)
    if limit:
        cmd += ["-t", f"{limit:g}"]
    if o.keep == "full":
        cmd += ["-c", "copy"] + (["-bsf:a", "aac_adtstoasc"] if hls else [])
    else:
        cmd += ["-vf", f"scale=-2:'min({int(o.proxy_height)},ih)'", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(o.crf),
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k"]
    return cmd + ["-movflags", "+faststart", "-f", "mp4", out_tmp]


def run_ffmpeg(cmd: List[str], duration: float, progress=None) -> None:
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    err = []
    for ln in p.stdout:
        ln = ln.strip()
        m = re.match(r"out_time_(?:us|ms)=(\d+)", ln)
        if m:
            if progress and duration:
                progress(min(0.99, int(m.group(1)) / 1e6 / duration))
        elif "=" not in ln:
            err.append(ln)
    if p.wait() != 0:
        raise SourceError("ffmpeg no pudo leer la fuente: " + " ".join(err[-4:]))


def _sidecar(path: str) -> str:
    return path + ".src.json"


def _remote_tag(url: str, o: Options) -> str:
    if not url.startswith(("http://", "https://")) or o.probe:
        return ""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers={"User-Agent": o.user_agent, **o.headers}), timeout=o.timeout) as r:
            return "|".join(r.headers.get(k, "") for k in ("ETag", "Last-Modified", "Content-Length"))
    except Exception:
        return ""


def dir_size(d: str) -> int:
    return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(d) for f in fs if os.path.isfile(os.path.join(r, f)))


class Fetcher:
    def __init__(self, res: Resolver, dest_root: str):
        self.res, self.o, self.root = res, res.o, dest_root

    def fetch(self, it: Item, progress=None) -> str:
        o, dst = self.o, os.path.join(self.root, it.rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if it.kind == "local":
            return self._link(it.uri, dst)
        spec = {"uri": it.uri, "keep": o.keep, "h": o.proxy_height, "t": o.max_seconds, "crf": o.crf}
        if it.kind == "torrent":
            spec["i"] = it.extra.get("index")
        tag = _remote_tag(it.uri, o) if it.kind == "http" else ""
        side = _sidecar(dst)
        if os.path.exists(dst) and os.path.exists(side):
            old = json.load(open(side))
            if all(old.get(k) == v for k, v in spec.items()) and (not tag or old.get("tag") in ("", tag)):
                return dst  # already fetched, unchanged
        last = None
        for attempt in range(o.retries + 1):
            try:
                self._fetch_once(it, dst, progress)
                json.dump({**spec, "tag": tag, "fetched": time.time()}, open(side, "w"))
                return dst
            except SourceError as e:
                last = e
                if re.search(r"DRM|falta |no hay backend|unavailable|removed|private|copyright|not available|sign in|members-only|confirm your age", str(e), re.I):
                    break
                time.sleep(min(2.0 * (attempt + 1), 6.0))
        raise last

    def _link(self, src: str, dst: str) -> str:
        if os.path.lexists(dst):
            if os.path.realpath(dst) == os.path.realpath(src):
                return dst
            os.remove(dst)
        try:
            os.symlink(os.path.abspath(src), dst)
        except OSError:
            shutil.copy2(src, dst)
        return dst

    def _fetch_once(self, it: Item, dst: str, progress) -> None:
        o, tmp = self.o, dst + ".part"
        try:
            if it.kind == "torrent":
                src = self.res.backend().fetch(it.uri, it.extra["index"], os.path.join(self.root, "_torrents", "data"), progress)
                self._ff_to([(src, {})], tmp, 0.0, False, False, None)
                if not o.keep_torrent_original:
                    try:
                        os.remove(src)
                    except OSError:
                        pass
            elif it.kind == "ytdlp":
                ins, dur = ytdlp_resolve(it.uri, o)
                self._ff_to(ins, tmp, dur or it.extra.get("duration") or 0, False, any(".m3u8" in u for u, _ in ins), progress)
            else:
                live = it.kind == "live"
                dur = 0.0 if live else probe_duration(it.uri)
                self._ff_to([(it.uri, {})], tmp, dur, live, it.kind == "stream", progress)
            os.replace(tmp, dst)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def _ff_to(self, ins, tmp, dur, live, hls, progress):
        cmd = build_ffmpeg_cmd(ins, tmp, self.o, live=live, hls=hls)
        lim = self.o.max_seconds or (self.o.live_default_seconds if live else 0)
        run_ffmpeg(cmd, min(dur, lim) if lim and dur else (lim or dur), progress)


# ---- public entry points --------------------------------------------------------------------------------------
def is_plain_local(inputs: List[str], o: Optional[Options] = None) -> bool:
    """One existing local file or folder (no list file): the original zero-copy path."""
    if len(inputs) != 1:
        return False
    p = os.path.expanduser(inputs[0].strip().strip("'\""))
    return os.path.exists(p) and not (os.path.isfile(p) and p.lower().endswith(LIST_EXT)) and classify(p, o) == "local"


def preview(inputs: List[str], o: Optional[Options] = None, ws: str = ".") -> List[Item]:
    """What would be learned, without fetching anything (lists are expanded; torrents need their metadata)."""
    return Resolver(o, ws).resolve(inputs)


def prepare(inputs: List[str], ws: str, o: Optional[Options] = None, progress=None) -> Prepared:
    """Resolve every input and make it available as local files. Plain local input is returned untouched."""
    o = o or Options()
    if is_plain_local(inputs, o) and not o.audio_only:
        p = os.path.abspath(os.path.expanduser(inputs[0].strip().strip("'\"")))
        paths = list_videos(p)
        return Prepared(p if os.path.isdir(p) else os.path.dirname(p), paths,
                        [{"uri": v, "kind": "local", "path": v, "status": "ok"} for v in paths], [], False)
    res = Resolver(o, ws)
    items = res.resolve(inputs)
    if not items:
        raise SourceError("las fuentes no contienen ningún vídeo")
    root = os.path.join(ws, "sources")
    os.makedirs(root, exist_ok=True)
    fx = Fetcher(res, root)
    recs: List[dict] = [None] * len(items)  # type: ignore
    done = [0]
    lock = threading.Lock()

    def one(k: int, it: Item):
        rec = {"uri": it.uri, "kind": it.kind, "title": it.title, "rel": it.rel, "season": it.season, "episode": it.episode}
        if o.max_gb and it.kind != "local" and dir_size(root) > o.max_gb * 1e9:
            rec.update(status="omitido", note=f"límite de {o.max_gb:g} GB de la carpeta de fuentes")
        else:
            try:
                rec.update(status="ok", path=fx.fetch(it))
            except Exception as e:  # one bad item never loses the others
                rec.update(status="error", note=str(e))
        with lock:
            recs[k] = rec
            done[0] += 1
            progress and progress(done[0] / len(items), it.title or it.uri)

    serial = [(k, it) for k, it in enumerate(items) if it.kind in ("local", "torrent")]   # the torrent session is not shared between threads
    par = [(k, it) for k, it in enumerate(items) if it.kind not in ("local", "torrent")]
    if par:
        with ThreadPoolExecutor(max_workers=1 if o.max_gb else max(1, min(o.fetch_workers, len(par)))) as ex:  # a size budget is checked item by item
            list(ex.map(lambda t: one(*t), par))
    for k, it in serial:
        one(k, it)
    paths = [r["path"] for r in recs if r["status"] == "ok"]
    errs = [f"{r['title'] or r['uri']}: {r['note']}" for r in recs if r["status"] != "ok"]
    json.dump({"inputs": inputs, "items": recs}, open(os.path.join(ws, "sources.json"), "w"), indent=1, ensure_ascii=False)
    if not paths:
        raise SourceError("no se pudo obtener ningún vídeo: " + "; ".join(errs[:3]))
    return Prepared(root, sorted(paths), recs, errs, True)


def project_name(inputs: List[str]) -> str:
    """A folder-friendly name for the project from the first input."""
    e = inputs[0].strip().strip("'\"")
    if re.match(r"\w{2,}://", e) or e.lower().startswith("magnet:"):
        m = re.search(r"[?&]dn=([^&]+)", e)
        if m:
            return slug(urllib.parse.unquote_plus(m.group(1)), 40)
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(e).query))
        last = os.path.splitext(urllib.parse.urlparse(e).path.rstrip("/").rsplit("/", 1)[-1])[0]
        return slug(q.get("list") or q.get("v") or last or _host(e), 40)
    return slug(os.path.splitext(os.path.basename(os.path.abspath(os.path.expanduser(e)).rstrip("/")))[0], 40)
