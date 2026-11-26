import http.server
import json
import os
import shutil
import subprocess
import threading

import pytest

from studio import corpus as C
from studio import learning as L
from studio import pipeline as PL
from studio import sources as S
from studio.audio import _ffmpeg
from studio.ingest import load_manifest

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") or os.path.exists(_ffmpeg())), reason="needs ffmpeg")


def _make(path, secs=3, size="320x240", color="red"):
    subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=16:duration={secs}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", "-movflags", "+faststart", path], check=True)


class _H(http.server.SimpleHTTPRequestHandler):
    """Static server with Range support and a request log (ffmpeg seeks with ranges)."""
    log = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        _H.log.append(("GET", self.path, self.headers.get("Range")))
        path = self.translate_path(self.path)
        rng = self.headers.get("Range")
        if os.path.isfile(path) and rng and rng.startswith("bytes="):
            data = open(path, "rb").read()
            a, b = rng[6:].split("-")
            a = int(a or 0)
            b = int(b) if b else len(data) - 1
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {a}-{b}/{len(data)}")
            self.send_header("Content-Length", str(b - a + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Type", self.guess_type(path))
            self.end_headers()
            self.wfile.write(data[a : b + 1])
        else:
            super().do_GET()

    def do_HEAD(self):
        _H.log.append(("HEAD", self.path, None))
        super().do_HEAD()


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "site"
    (root / "Show" / "Season 1").mkdir(parents=True)
    (root / "Show" / "Season 2").mkdir(parents=True)
    for rel in ("Show/Season 1/ep1.mp4", "Show/Season 1/ep2.mp4", "Show/Season 2/ep1.mp4", "clip.mp4"):
        _make(str(root / rel), secs=6)
    (root / "notes.txt.bak").write_text("x")
    (root / "feed.xml").write_text(
        '<rss><channel><title>Mi Feed</title><item><title>Uno</title><enclosure url="http://HOST/clip.mp4" type="video/mp4"/></item>'
        '<item><title>Texto</title><enclosure url="http://HOST/notes.mp3" type="audio/mpeg"/></item></channel></rss>')
    handler = lambda *a, **k: _H(*a, directory=str(root), **k)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    (root / "feed.xml").write_text((root / "feed.xml").read_text().replace("http://HOST", base))
    _H.log.clear()
    yield base, root
    srv.shutdown()


def _height(path):
    import imageio

    r = imageio.get_reader(path, "ffmpeg")
    h = r.get_meta_data()["size"][1]
    r.close()
    return h


# ---- classification, rewriting, list formats ---------------------------------------------------------------------
def test_classify_every_kind():
    o = S.Options(probe=lambda u: "text/html")
    cases = {
        "/tmp/a.mp4": "local", "C:\\videos\\a.mp4": "local", "magnet:?xt=urn:btih:abc": "torrent", "https://x.org/a.torrent": "torrent",
        "https://youtu.be/abc": "ytdlp", "https://www.youtube.com/playlist?list=PL1": "ytdlp", "https://archive.org/details/foo": "ytdlp",
        "https://x.org/v/a.mkv?token=1": "http", "https://x.org/live/master.m3u8": "stream", "https://x.org/list.txt": "list",
        "https://x.org/feed.rss": "feed", "rtsp://cam/stream": "live", "udp://239.0.0.1:1234": "live", "https://x.org/watch": "page",
        "ipfs://bafyabc/ep1.mp4": "http", "s3://bucket/ep1.mp4": "http", "gs://bucket/ep1.mp4": "http",
    }
    for entry, kind in cases.items():
        assert S.classify(entry, o) == kind, entry
    assert S.classify("https://x.org/stream", S.Options(probe=lambda u: "video/mp4")) == "http"
    assert S.classify("https://x.org/s", S.Options(probe=lambda u: "application/vnd.apple.mpegurl")) == "stream"


def test_share_links_are_rewritten():
    assert S.normalize("https://www.dropbox.com/s/abc/ep1.mp4?dl=0").endswith("dl=1")
    assert S.normalize("https://drive.google.com/file/d/AbC_123/view?usp=sharing") == "https://drive.google.com/uc?export=download&id=AbC_123"
    assert S.normalize("https://github.com/u/r/blob/main/a.mp4") == "https://raw.githubusercontent.com/u/r/main/a.mp4"
    assert S.normalize("ipfs://bafy/a.mp4") == "https://ipfs.io/ipfs/bafy/a.mp4"
    assert S.normalize("s3://b/k/a.mp4") == "https://b.s3.amazonaws.com/k/a.mp4"
    assert S.normalize("file:///tmp/a%20b.mp4") == "/tmp/a b.mp4"


def test_list_formats():
    txt = "# my show\nhttps://x/a.mp4  # Pilot\nhttps://x/b.mp4 | Second\n\nhttps://x/c.mp4\n"
    r = S.read_list(txt, "l.txt")
    assert [(x["uri"], x["title"]) for x in r] == [("https://x/a.mp4", "Pilot"), ("https://x/b.mp4", "Second"), ("https://x/c.mp4", "")]
    j = S.read_list(json.dumps([{"url": "https://x/a.mp4", "title": "A", "season": 2, "episode": 5}, "https://x/b.mp4"]), "l.json")
    assert j[0]["season"] == 2 and j[0]["episode"] == 5 and j[1]["uri"] == "https://x/b.mp4"
    c = S.read_list("url,title,season\nhttps://x/a.mp4,Uno,3\n", "l.csv")
    assert c == [{"uri": "https://x/a.mp4", "title": "Uno", "season": 3, "episode": 0}]
    m = S.read_list("#EXTM3U\n#EXTINF:10,Primero\nhttps://x/a.mp4\n#EXTINF:10,Segundo\nhttps://x/b.mp4\n", "l.m3u")
    assert [x["title"] for x in m] == ["Primero", "Segundo"]


# ---- real HTTP: streaming proxy, no original stored ---------------------------------------------------------------
def test_http_video_becomes_a_proxy_without_storing_the_original(site, tmp_path):
    base, _ = site
    ws = str(tmp_path / "ws")
    o = S.Options(proxy_height=120, name="Demo")
    pr = S.prepare([f"{base}/clip.mp4"], ws, o)
    assert pr.remote and len(pr.paths) == 1 and not pr.errors
    p = pr.paths[0]
    assert p.startswith(os.path.join(ws, "sources")) and p.endswith(".mp4")
    assert _height(p) == 120  # scaled down from 240
    assert os.path.getsize(p) > 1000
    assert not any(f.endswith(".part") for _, _, fs in os.walk(ws) for f in fs)
    # it really streamed over HTTP, using ranges
    assert any(m == "GET" for m, _, _ in _H.log)


def test_second_run_does_not_refetch(site, tmp_path):
    base, _ = site
    ws = str(tmp_path / "ws")
    o = S.Options(proxy_height=120, name="Demo")
    S.prepare([f"{base}/clip.mp4"], ws, o)
    n = sum(1 for m, _, _ in _H.log if m == "GET")
    S.prepare([f"{base}/clip.mp4"], ws, o)
    assert sum(1 for m, _, _ in _H.log if m == "GET") == n  # unchanged -> only HEAD checks


def test_max_seconds_and_full_mode(site, tmp_path):
    base, _ = site
    pr = S.prepare([f"{base}/clip.mp4"], str(tmp_path / "a"), S.Options(proxy_height=120, max_seconds=1))
    import imageio

    r = imageio.get_reader(pr.paths[0], "ffmpeg")
    assert r.get_meta_data()["duration"] <= 1.2
    r.close()
    pf = S.prepare([f"{base}/clip.mp4"], str(tmp_path / "b"), S.Options(keep="full"))
    assert _height(pf.paths[0]) == 240  # remux keeps the original height


def test_open_directory_gets_seasons_from_its_structure(site, tmp_path):
    base, _ = site
    ws = str(tmp_path / "ws")
    pr = S.prepare([f"{base}/Show/"], ws, S.Options(proxy_height=96))
    assert len(pr.paths) == 3 and not pr.errors
    vids = {p: type("V", (), {"duration": 2.0})() for p in pr.paths}
    corpus = C.build_corpus(vids, pr.root)
    assert list(corpus) == ["Show"] and sorted(corpus["Show"]) == [1, 2]
    assert [len(corpus["Show"][1]), len(corpus["Show"][2])] == [2, 1]


def test_list_file_of_urls_and_feed_and_mixed_local(site, tmp_path):
    base, root = site
    lst = tmp_path / "eps.txt"
    lst.write_text(f"{base}/clip.mp4 | Pilot S01E01\n{base}/Show/Season 1/ep2.mp4 | Segundo S01E02\n")
    local = tmp_path / "Local Show" / "S03"
    local.mkdir(parents=True)
    _make(str(local / "E01.mp4"), secs=2)
    ws = str(tmp_path / "ws")
    pr = S.prepare([str(lst), f"{base}/feed.xml", str(tmp_path / "Local Show")], ws, S.Options(proxy_height=96, name="Mezcla"))
    assert not pr.errors and len(pr.paths) == 4  # 2 listed + 1 feed video (the audio enclosure is skipped) + 1 local
    kinds = sorted(r["kind"] for r in pr.records)
    assert kinds.count("local") == 1
    rels = [r["rel"] for r in pr.records]
    assert any("S01E001_Pilot" in x or "S01E01" in x for x in rels)
    local_path = next(r["path"] for r in pr.records if r["kind"] == "local")
    assert os.path.islink(local_path) or os.path.exists(local_path)
    assert json.load(open(os.path.join(ws, "sources.json")))["items"]


def test_one_bad_url_does_not_lose_the_rest(site, tmp_path):
    base, _ = site
    pr = S.prepare([f"{base}/clip.mp4", f"{base}/missing.mp4"], str(tmp_path / "ws"), S.Options(proxy_height=96, retries=0))
    assert len(pr.paths) == 1 and len(pr.errors) == 1 and "missing" in pr.errors[0]
    with pytest.raises(S.SourceError):
        S.prepare([f"{base}/missing.mp4"], str(tmp_path / "ws2"), S.Options(retries=0))


def test_size_budget_stops_fetching(site, tmp_path):
    base, _ = site
    pr = S.prepare([f"{base}/clip.mp4", f"{base}/Show/Season 1/ep1.mp4"], str(tmp_path / "ws"), S.Options(proxy_height=96, max_gb=1e-9))
    assert len(pr.paths) == 1 and any("límite" in e for e in pr.errors)


def test_plain_local_input_is_untouched(tmp_path):
    d = tmp_path / "Show"
    (d / "S01").mkdir(parents=True)
    _make(str(d / "S01" / "E01.mp4"), secs=2)
    pr = S.prepare([str(d)], str(tmp_path / "ws"))
    assert not pr.remote and pr.root == str(d) and not os.path.exists(tmp_path / "ws" / "sources")


# ---- yt-dlp (fake extractor serving real local URLs) -----------------------------------------------------------------
class FakeYDL:
    def __init__(self, opts, base):
        self.opts, self.base = opts, base

    def extract_info(self, url, download=False):
        if "playlist" in url:
            return {"_type": "playlist", "title": "Mi Serie T2", "entries": [
                {"id": "a", "title": "Capítulo 1", "url": f"https://www.youtube.com/watch?v=a", "playlist_index": 1},
                {"id": "b", "title": "Capítulo 2", "url": f"https://www.youtube.com/watch?v=b", "playlist_index": 2}]}
        assert self.opts.get("format")
        return {"id": "x", "title": "v", "duration": 2, "url": f"{self.base}/clip.mp4", "http_headers": {"X-Test": "1"}}


def test_youtube_playlist_and_video_via_ytdlp(site, tmp_path):
    base, _ = site
    o = S.Options(proxy_height=96, ytdlp_factory=lambda opts: FakeYDL(opts, base))
    items = S.preview(["https://www.youtube.com/playlist?list=PL1"], o)
    assert [i.rel.split("/")[-1][:9] for i in items] == ["S02E001_C", "S02E002_C"]  # "T2" in the title -> season 2
    pr = S.prepare(["https://www.youtube.com/playlist?list=PL1"], str(tmp_path / "ws"), o)
    assert len(pr.paths) == 2 and not pr.errors
    assert all(_height(p) == 96 for p in pr.paths)


def test_channel_with_several_playlists_makes_one_season_each(site, tmp_path):
    base, _ = site

    class Chan(FakeYDL):
        def extract_info(self, url, download=False):
            if "channel" in url:
                return {"_type": "playlist", "title": "Canal", "entries": [
                    {"_type": "playlist", "title": "Temporada 1", "url": "https://www.youtube.com/playlist?list=A"},
                    {"_type": "playlist", "title": "Temporada 2", "url": "https://www.youtube.com/playlist?list=B"}]}
            n = "A" if "list=A" in url else "B"
            return {"_type": "playlist", "title": "T" + n, "entries": [{"id": n + "1", "title": f"{n} uno", "url": f"https://www.youtube.com/watch?v={n}1"}]}

    items = S.preview(["https://www.youtube.com/channel/UC1"], S.Options(ytdlp_factory=lambda opts: Chan(opts, base)))
    assert sorted({i.season for i in items}) == [1, 2]


def test_missing_ytdlp_gives_install_hint(tmp_path, monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "yt_dlp", None)
    with pytest.raises(S.SourceError, match="pip install yt-dlp"):
        S.preview(["https://youtu.be/abc"], S.Options())


# ---- torrents (fake backend; the real ones need a swarm) -------------------------------------------------------------
class FakeTorrent:
    def __init__(self, src):
        self.src, self.fetched = src, []

    def files(self, uri):
        return [(0, "Show.S01/S01E01.mkv", 5 * 10**8), (1, "Show.S01/Sample/sample.mkv", 10**6), (2, "Show.S01/S01E02.mkv", 5 * 10**8),
                (3, "Show.S01/readme.nfo", 100), (4, "Show.S01/Extras/making.mkv", 10**7)]

    def fetch(self, uri, index, dest_dir, progress=None):
        os.makedirs(dest_dir, exist_ok=True)
        dst = os.path.join(dest_dir, f"{index}.mkv")
        shutil.copy(self.src, dst)
        self.fetched.append(index)
        return dst


def test_torrent_picks_episodes_only_proxies_and_deletes_the_original(site, tmp_path):
    base, root = site
    fake = FakeTorrent(str(root / "clip.mp4"))
    ws = str(tmp_path / "ws")
    pr = S.prepare(["magnet:?xt=urn:btih:abc&dn=Mi+Show"], ws, S.Options(proxy_height=96, torrent_backend=fake))
    assert fake.fetched == [0, 2]  # sample, extras and nfo never requested
    assert len(pr.paths) == 2 and not pr.errors
    assert not os.path.exists(os.path.join(ws, "sources", "_torrents", "data", "0.mkv"))  # original removed after the proxy
    assert all(p.endswith(".mp4") and _height(p) == 96 for p in pr.paths)
    corpus = C.build_corpus({p: type("V", (), {"duration": 2.0})() for p in pr.paths}, pr.root)
    assert len(next(iter(corpus.values()))[1]) == 2


def test_aria2_listing_parser():
    out = """Files:
idx|path/length
===+===========================================================================
  1|./Show/S01E01.mkv
   |500MiB (524,288,000)
---+---------------------------------------------------------------------------
  2|./Show/readme.nfo
   |100B (100)
---+---------------------------------------------------------------------------
"""
    assert S.parse_aria2_listing(out) == [(1, "Show/S01E01.mkv", 524288000), (2, "Show/readme.nfo", 100)]


def test_no_torrent_backend_has_a_clear_message(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "libtorrent", None)
    monkeypatch.setattr(shutil, "which", lambda n: None)
    with pytest.raises(S.SourceError, match="backend de torrents"):
        S.get_torrent_backend(S.Options(), "/tmp/x")


# ---- ffmpeg command, live streams, project name ---------------------------------------------------------------------
def test_ffmpeg_command_shapes():
    c = S.build_ffmpeg_cmd([("https://x/a.mp4", {"Referer": "r"})], "/tmp/o.mp4", S.Options(proxy_height=360))
    assert "-reconnect" in c and "-headers" in c and any("min(360,ih)" in a for a in c) and c[-1] == "/tmp/o.mp4"
    two = S.build_ffmpeg_cmd([("https://v", {}), ("https://a", {})], "/tmp/o.mp4", S.Options())
    assert "1:a:0?" in two
    live = S.build_ffmpeg_cmd([("rtsp://cam/s", {})], "/tmp/o.mp4", S.Options(), live=True)
    assert "-rtsp_transport" in live and "-t" in live and live[live.index("-t") + 1] == "300"
    full = S.build_ffmpeg_cmd([("https://x/m.m3u8", {})], "/tmp/o.mp4", S.Options(keep="full"), hls=True)
    assert "copy" in full and "aac_adtstoasc" in full


def test_project_names():
    assert S.project_name(["https://www.youtube.com/playlist?list=PL123"]) == "PL123"
    assert S.project_name(["magnet:?xt=urn:btih:a&dn=Mi+Show+S01"]) == "Mi_Show_S01"
    assert S.project_name(["/data/My Show/"]) == "My_Show"


# ---- end to end: online input through the real learning phases --------------------------------------------------------
def test_learning_phases_run_on_online_material(site, tmp_path):
    base, _ = site
    lst = tmp_path / "show.txt"
    lst.write_text(f"{base}/Show/Season 1/ep1.mp4\n{base}/Show/Season 1/ep2.mp4\n{base}/Show/Season 2/ep1.mp4\n")
    ws = str(tmp_path / "ws")
    ctx = {"input": str(lst), "inputs": [str(lst)], "source_options": S.Options(proxy_height=96, name="Online"), "ws": ws,
           "device": "cpu", "workers": 1, "vision": False}
    phases = [p for p in L.LEARNING_PHASES if p.key in ("sources", "scan", "corpus", "profile")]
    outs = PL.run(phases, ctx)
    assert [o.status for o in outs] == ["ok"] * 4, [(o.key, o.note) for o in outs]
    assert len(load_manifest(os.path.join(ws, "manifest.json"))) == 3
    corpus = json.load(open(os.path.join(ws, "corpus.json")))
    assert len(corpus) == 1 and sum(len(e) for s in corpus.values() for e in s.values()) == 3


def test_terminal_online_option_and_cli_dry_run(site, tmp_path, capsys):
    import io

    from studio import cli, tui

    base, _ = site
    lst = tmp_path / "show.txt"
    lst.write_text(f"{base}/Show/Season 1/ep1.mp4\n{base}/Show/Season 1/ep2.mp4\n")
    cli.main(["--workdir", str(tmp_path / "w"), "sources", str(lst), "--name", "Dry"])
    assert "Dry/S01/S01E001_" in capsys.readouterr().out and not os.path.exists(tmp_path / "w" / "sources")
    answers = iter(["3", str(lst), ""])
    out = io.StringIO()
    rc = tui.main(["--out", str(tmp_path / "proj"), "--proxy-height", "96", "--no-create"], inp=lambda p="": next(answers), out=out)
    text = out.getvalue()
    assert "PROCESO COMPLETADO" in text or "ERRORES" in text
    assert os.path.exists(tmp_path / "proj" / "sources.json") and rc in (0, 1)
    kit = json.load(open(tmp_path / "proj" / "episode_kit.json"))
    assert kit["source"]["remote"] is True
