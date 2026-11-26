import json
import os
import subprocess

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from studio import overlays as OV
from studio import script as SC

W, H = 480, 270


def _font(sz):
    for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            pass
    pytest.skip("no TrueType font to render synthetic text")


def _cartoon(shot, t):
    r = np.random.default_rng(shot)
    img = Image.new("RGB", (W, H), tuple(int(x) for x in r.integers(40, 220, 3)))
    d = ImageDraw.Draw(img)
    for k in range(4):
        cx, cy = int(r.integers(40, W - 40) + 8 * np.sin(t + k)), int(r.integers(40, H - 40))
        d.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], fill=tuple(int(x) for x in r.integers(30, 255, 3)), outline=(0, 0, 0), width=3)
        for ex in (-10, 3):
            d.ellipse([cx + ex, cy - 10, cx + ex + 7, cy - 3], fill=(255, 255, 255), outline=(0, 0, 0))
    return img


def _subtitle(img, text, y=225):
    d, f = ImageDraw.Draw(img), _font(17)
    x = (W - d.textlength(text, font=f)) / 2
    for dx in (-2, -1, 0, 1, 2):
        for dy in (-2, -1, 0, 1, 2):
            d.text((x + dx, y + dy), text, font=f, fill=(0, 0, 0))
    d.text((x, y), text, font=f, fill=(255, 255, 255))


def _logo(img):
    d = ImageDraw.Draw(img)
    d.rectangle([W - 90, 8, W - 8, 34], outline=(255, 255, 255), width=2)
    d.text((W - 84, 12), "TOON TV", font=_font(14), fill=(255, 255, 255))


def _credits(img):
    img.paste((0, 0, 0), [0, 0, W, H])
    d, f = ImageDraw.Draw(img), _font(16)
    for k, t in enumerate(["Dirigido por Ana Lopez", "Producido por Estudio Sol", "Música de Pablo Ruiz", "Guion de Marta Gil", "Gracias por ver"]):
        d.text((W // 2 - d.textlength(t, font=f) / 2, 40 + 38 * k), t, font=f, fill=(255, 255, 255))


def _frames(n=120, subs=True, logo=False, credits=(), bars=False):
    out = []
    for i in range(n):
        img = _cartoon(i // 4, i * 0.5)
        if i in credits:
            _credits(img)
        else:
            if subs and (i % 10) < 6:
                _subtitle(img, ["Hola, ¿cómo estás hoy amigo?", "Vamos a la playa ahora mismo", "No puedo creerlo, es increíble"][(i // 10) % 3])
            if logo:
                _logo(img)
        a = np.asarray(img).copy()
        if bars:
            a[:30] = 0
            a[-30:] = 0
        out.append(a)
    return out


def test_clean_animation_is_left_alone():
    rep = OV.analyze_frames(_frames(subs=False), 2.0)
    assert OV.clean(rep) and rep["text_frame_ratio"] == 0.0 and OV.describe_es(rep).startswith("sin texto")


def test_burned_in_subtitles_are_found_with_band_and_timing():
    rep = OV.analyze_frames(_frames(subs=True), 2.0)
    assert rep["subtitle_bands"] and rep["subtitle_bands"][0][1] > 0.75   # bottom band
    assert not rep["static"] and not rep["text_segments"]
    assert 0.45 < rep["text_frame_ratio"] < 0.75                              # on 6 of every 10 frames
    on = {int(t * 2) for a, b in rep["subtitle_intervals"] for t in np.arange(a, b, 0.5)}
    assert all(i in on for i in range(120) if i % 10 < 6)


def test_logo_is_static_not_a_subtitle():
    rep = OV.analyze_frames(_frames(subs=False, logo=True), 2.0)
    assert len(rep["static"]) == 1
    x0, y0, x1, y1 = rep["static"][0]["box"]
    assert x0 > 0.7 and y1 < 0.25                                             # top-right corner
    assert not rep["subtitle_intervals"], "the letters of a logo must not count as subtitles"


def test_credits_become_excluded_segments_and_subtitles_stay_masked():
    rep = OV.analyze_frames(_frames(subs=True, credits=range(40, 52)), 2.0)
    assert len(rep["text_segments"]) == 1
    a, b = rep["text_segments"][0]
    assert 19 <= a <= 21 and 25 <= b <= 27
    assert OV.overlaps_excluded(rep, 18.0, 3.0) and not OV.overlaps_excluded(rep, 0.0, 3.0)
    assert rep["subtitle_intervals"]


def test_letterbox_bars_are_detected():
    rep = OV.analyze_frames(_frames(subs=False, bars=True), 2.0)
    assert rep["bars"] and abs(rep["bars"][1] - 30 / H) < 0.02 and abs(rep["bars"][3] - (1 - 30 / H)) < 0.02
    assert not rep["static"]  # the bar edge itself is not a logo


def test_static_content_alone_is_not_called_a_logo():
    fr = [_frames(1, subs=False)[0]] * 40   # a held frame: nothing changes, so nothing can be told apart
    assert OV.analyze_frames(fr, 2.0)["static"] == []


def test_loss_mask_zeroes_the_overlay_on_the_latent_grid():
    rep = OV.analyze_frames(_frames(subs=True, logo=True), 2.0)
    m = OV.clip_loss_mask(rep, (1920, 1080), 0.0, 3.0)
    assert m.shape == (13, 60, 90) and set(np.unique(m)) <= {0.0, 1.0}
    assert m[:, :12, 70:].min() == 0.0                    # the logo's corner never carries gradient
    assert m[:, 20:35, 30:60].min() == 1.0                # the middle of the picture always does
    t_on = next(t for t in range(13) if m[t, 50:57, 30:60].min() == 0.0)   # subtitles: masked while they are shown...
    assert 0 <= t_on < 13
    assert (m[:, :, :].mean() < 1.0)
    cards = OV.analyze_frames(_frames(subs=False, credits=range(0, 12)), 2.0)
    full = OV.clip_loss_mask(cards, (1920, 1080), 0.0, 3.0)
    assert full[0].max() == 0.0                           # a title card is fully ignored if it is ever inside a clip


def test_loss_mask_follows_the_bar_crop_and_centre_crop():
    rep = OV.empty_report()
    rep.update(bars=[0.0, 0.2, 1.0, 0.8], static=[{"box": [0.0, 0.0, 0.1, 0.1], "kind": "logo"}])  # logo inside the cropped bar
    m = OV.clip_loss_mask(rep, (1920, 1080), 0.0, 3.0)
    assert m.min() == 1.0                                  # it is cut away with the bar, so nothing is left to mask
    rep["static"] = [{"box": [0.4, 0.25, 0.5, 0.35], "kind": "logo"}]   # source px 768-960 x 270-378 -> scaled x0.74, minus the bar and centre crop
    m = OV.clip_loss_mask(rep, (1920, 1080), 0.0, 3.0)
    assert m[:, 6:14, 30:42].min() == 0.0 and m[:, 40:, :].min() == 1.0


def test_ffmpeg_filter_modes():
    rep = OV.empty_report()
    rep.update(bars=[0.0, 0.1, 1.0, 0.9], static=[{"box": [0.8, 0.05, 0.98, 0.2], "kind": "logo"}], subtitle_bands=[[0.2, 0.86, 0.8, 0.94]])
    assert OV.ffmpeg_filter(rep, "off", (1280, 720)) == ""
    assert OV.ffmpeg_filter(rep, "mask", (1280, 720)).startswith("crop=1280:576:0:72") and "delogo" not in OV.ffmpeg_filter(rep, "mask", (1280, 720))
    assert "delogo=" in OV.ffmpeg_filter(rep, "delogo", (1280, 720))
    c = OV.ffmpeg_filter(rep, "crop", (1280, 720))
    assert c.startswith("crop=1280:") and int(c.split(":")[1]) < 576      # the bottom subtitle band is cut away too


def test_captions_never_mention_text_or_logos():
    for dirty, clean in [("A fox runs. The subtitles read 'hola amigo' at the bottom.", "A fox runs."),
                         ("a bear waves, with a channel logo in the corner, in a forest", "a bear waves, in a forest"),
                         ("Credits roll over a black screen.", "")]:
        out = OV.sanitize_caption(dirty)
        assert not any(w in out.lower() for w in ("subtitle", "logo", "credit")), out
        assert out == clean or clean in out
    assert OV.sanitize_caption("a fox jumps over a log") == "a fox jumps over a log"


def test_every_generated_segment_carries_the_negative_text():
    segs, _ = SC.to_segments([SC.Scene("a fox in a kitchen", 6, True, "blurry")], "style")
    assert len(segs) == 2 and all("subtitles" in s["neg_text"] and "watermark" in s["neg_text"] and s["neg_text"].startswith("blurry") for s in segs)
    segs, _ = SC.to_segments([SC.Scene("a fox", 3, True)], "style")
    assert segs[0]["neg_text"] == OV.NEGATIVE_TEXT


# ---- through ffmpeg and the dataset builder -----------------------------------------------------------------------------
def _write_video(path, frames, fps=2):
    import imageio

    w = imageio.get_writer(path, fps=fps, codec="libx264", macro_block_size=1)
    for f in frames:
        w.append_data(f)
    w.close()


def test_scan_video_through_ffmpeg(tmp_path):
    p = str(tmp_path / "ep.mp4")
    _write_video(p, _frames(subs=True, logo=True), fps=2)
    rep = OV.scan_video(p, fps=2.0)
    assert len(rep["static"]) == 1 and rep["subtitle_intervals"] and rep["video"] == p
    assert OV.score_video_intrusion(p)["intrusion"] > 0.4
    clean = str(tmp_path / "clean.mp4")
    _write_video(clean, _frames(subs=False), fps=2)
    assert OV.score_video_intrusion(clean)["intrusion"] == 0.0


def test_dataset_builder_drops_title_cards_masks_clips_and_cleans_captions(tmp_path):
    from studio import corpus as C
    from studio import learning as L
    from studio import pipeline as PL
    from studio.dataset import build_training_set

    show = tmp_path / "Show" / "S01"
    show.mkdir(parents=True)
    fr = _frames(n=160, subs=True, logo=True, credits=range(100, 124))   # 80 s at 2 fps; credits at 50-62 s
    _write_video(str(show / "E01.mp4"), fr, fps=2)
    ws = str(tmp_path / "ws")
    ctx = {"input": str(tmp_path / "Show"), "ws": ws, "device": "cpu", "workers": 1, "vision": False}
    phases = [p for p in L.LEARNING_PHASES if p.key in ("sources", "scan", "corpus", "profile", "overlays")]
    outs = PL.run(phases, ctx)
    assert [o.status for o in outs] == ["ok"] * 5, [(o.key, o.note) for o in outs]
    assert "logo" in outs[-1].note.lower() or "incrustados" in outs[-1].note
    assert os.path.exists(os.path.join(ws, "overlays", "index.json"))
    r = build_training_set(ws, [3], with_control=False)
    ov = r["overlays"]
    assert ov["videos_with_reports"] == 1 and ov["clips_dropped"] >= 3 and ov["clips_with_masked_area"] >= 1
    rows = [json.loads(l) for l in open(os.path.join(ws, "dataset", "train_3s.jsonl"))]
    assert rows and all("loss_mask" in x for x in rows)
    from hypercartoon.models.cogvideo.control_data import load_loss_mask

    m = load_loss_mask(os.path.join(ws, "dataset", rows[0]["loss_mask"]))
    assert m.shape == (13, 60, 90) and m.min() == 0.0 and m.max() == 1.0
    clips = json.load(open(os.path.join(ws, "dataset", "clips_3s.json")))
    assert all(not (50 - 0.5 < c["start"] + 0 < 62 + 0.5) for c in clips) and not any(50.5 <= c["start"] <= 61.5 for c in clips)
    sh = open(os.path.join(ws, "dataset", "make_clips_3s.sh")).read()
    assert "scale=720:480" in sh
    # mode off: nothing dropped, no masks
    r2 = build_training_set(ws, [3], with_control=False, overlay_mode="off")
    assert r2["overlays"]["clips_dropped"] == 0
    assert not any("loss_mask" in json.loads(l) for l in open(os.path.join(ws, "dataset", "train_3s.jsonl")))
    # delogo mode adds the filter to the cut command
    build_training_set(ws, [3], with_control=False, overlay_mode="delogo")
    assert "delogo=" in open(os.path.join(ws, "dataset", "make_clips_3s.sh")).read()


def test_phase_can_be_turned_off(tmp_path):
    from studio import pipeline as PL
    from studio.learning import ph_overlays

    with pytest.raises(PL.Skip):
        ph_overlays({"overlay_mode": "off", "vids": {}, "ws": str(tmp_path)}, lambda *a: None)
