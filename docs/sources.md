# Universal learning input

Hypercartoon learns from **anything that leads to video**, local or online, in any mix:

```bash
python -m studio learn  ~/shows/MyShow  https://example.org/specials/pilot.mp4  episodes.txt
python -m studio learn  "https://www.youtube.com/playlist?list=PL..."  --name MyShow
python -m studio sources episodes.txt            # dry run: what would be learned, nothing fetched
python -m studio                                  # panel: 1) video  2) folder  3) online (URL, playlist, list, torrent, magnet)
```

| Input | How it is read | Needs |
|---|---|---|
| Local file, folder, glob (`~/shows/*/S01`) | as is, no copy | – |
| Direct URL (`.mp4 .mkv .webm …`, http/https/ftp) | ffmpeg streams it over HTTP (reconnects, ranges) | ffmpeg |
| HLS `.m3u8` / DASH `.mpd` | ffmpeg | ffmpeg |
| YouTube / Vimeo / Dailymotion / Twitch VODs / Archive.org / Bilibili / … video, **playlist or channel** | `yt-dlp` resolves the stream; a channel with several playlists becomes one season per playlist | `pip install yt-dlp` |
| List file: `.txt` (one per line, `url  # title` / `url \| title`), `.csv` (url,title,season,episode), `.json`, `.m3u` | every entry is expanded recursively (a list may contain playlists, folders, magnets) | – |
| Open directory (HTML index of an HTTP server) | walks sub-folders; **folder names give seasons** | – |
| RSS / Atom feed | video enclosures only | – |
| Dropbox, Google Drive, GitHub, S3, GCS, IPFS links | rewritten to direct links (public/shared ones) | – |
| Live / camera streams (`rtsp:// rtmp:// udp:// srt://`) | recorded for `--max-seconds` (default 300 s) | – |
| `.torrent` file or magnet link | metadata first, then **only the video files that are episodes** (samples, trailers, extras and `.nfo` are never requested), one at a time | `pip install libtorrent` or `aria2c` |

Authenticated material you are allowed to see: `--cookies cookies.txt` (yt-dlp).

## What "without downloading" means here

The studio does not keep the original. Each online video is read **once** through ffmpeg and only a compact **proxy** stays in
`<project>/sources/` (default 480 p H.264 + AAC — the engine's training height, `--proxy-height`). Analysis, characters, voices,
mouth convention and the training clips are all made from that proxy, so the pipeline never goes back to the network.
Torrents cannot avoid transferring the bytes; the original file is deleted as soon as its proxy exists.

* `--keep full` remuxes the original quality instead of re-encoding (larger).
* `--max-seconds N` takes only the first N seconds of every item: a quick first look at a huge series.
* `--max-gb N` stops fetching when the sources folder reaches N GB; skipped items are reported.
* Incremental: a fetched item is skipped next time when the URL, ETag/size and options are unchanged, so adding season 2 to a list only fetches season 2.
* One bad link never loses the rest: the phase finishes as *partial* with the failures listed (`sources.json`).

## Seasons and episodes

Names are derived so that the usual corpus inference works unchanged: an `S01E03` / `Cap 3` / `1x03` in a title, an explicit
`season` / `episode` column, a playlist's order, a playlist titled `Temporada 2` (several playlists without numbers become
seasons 1, 2, … in order) or the folder names of an open directory / torrent. When hints collide the order is used instead.
The result is `sources/<Series>/S01/S01E003_<title>.mp4`. `--name` fixes the series name.

## A real test: a YouTube playlist

`python -m studio learn "https://www.youtube.com/watch?v=…&list=PL…" --max-seconds 90` on a 23-video public playlist (a *Simpsons*
Spanish-dub compilation): the playlist was expanded by yt-dlp, **6 videos had been removed by a copyright claim and were reported, not fatal**
(the sources phase finished as *partial* with the reasons), 17 were fetched as 480 p proxies (≈ 7 MB per 90 s; the originals were never stored)
and the whole learning pipeline ran on them (25.5 min of material, 816 training clips). Findings that changed the code:

* one YouTube stream arrives at only **≈ 2× real time** (828 s for 17 × 90 s fetched one by one), so online items are now fetched
  **in parallel** (`--fetch-workers`, default 4; a `--max-gb` budget forces one at a time);
* unavailable / removed / private videos are never retried and their messages are cleaned up;
* a second run on the same playlist took **88 s instead of 16 min**: sources already fetched are skipped, scanning and overlay
  reports are cached.

## Limits

* Verified here with a real local HTTP server (ranges, indexes, feeds, lists, retries, size budget) and the real learning
  phases; **yt-dlp and the torrent backends are tested with fakes** (command construction, selection, parsing), not against
  YouTube or a live swarm. Sites change; keep `yt-dlp` updated.
* DRM-protected services (Netflix, Disney+, …) are not supported and never will be.
* Quality of the learning is bounded by the proxy: 480 p cannot teach details finer than 480 p. Use `--keep full` for more.
* Fetching and training on material you do not have rights to is your responsibility; this is a reader, not a licence.
