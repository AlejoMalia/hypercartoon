import io
import json
import os
import stat

import imageio
import numpy as np
import pytest

from hypercartoon.infra.step_cache import StepCache
from studio import dataset as DS
from studio import episode as EP
from studio import ingest as IG
from studio import postprocess as PP
from studio import tui
from studio.lips import rhubarb as RB
from studio.lips import visemes as V
from studio.lips.style import MouthStyle

rng = np.random.default_rng(3)


# ---- TeaCache-style step cache ---------------------------------------------------------------------------------------
def test_step_cache_skips_only_when_change_is_small_and_forces_first_and_last():
    c = StepCache(threshold=0.05, streams=1, warmup=1)
    c.reset(total_calls=8)
    base = rng.normal(size=(4, 8))
    calls = []
    for step in range(8):
        stream = c.begin_call()
        probe = base * (1 + 0.001 * step)  # barely changes
        skip = c.decide(stream, probe)
        calls.append(skip)
        if not skip:
            c.store(stream, probe * 0.1)
    assert calls[0] is False and calls[-1] is False  # warm-up and last step always compute
    assert sum(calls) >= 3
    c2 = StepCache(threshold=0.05, streams=1)
    c2.reset(total_calls=6)
    out = []
    for step in range(6):
        s = c2.begin_call()
        sk = c2.decide(s, base * (1 + 0.5 * step))  # large change each step -> never skip
        out.append(sk)
        if not sk:
            c2.store(s, base)
    assert not any(out)
    assert StepCache(0.0).enabled is False


def test_step_cache_keeps_one_residual_per_cfg_stream():
    c = StepCache(threshold=1.0, streams=2, warmup=1)
    c.reset(total_calls=8)
    a, b = np.ones((2, 2)), 5 * np.ones((2, 2))
    seen = []
    for step in range(4):
        for stream_probe, res in ((a, "uncond"), (b, "cond")):
            s = c.begin_call()
            sk = c.decide(s, stream_probe)
            if sk:
                seen.append((s, c.residual(s)))
            else:
                c.store(s, res)
    assert seen and all((s == 0 and r == "uncond") or (s == 1 and r == "cond") for s, r in seen)
    assert c.stats()["skipped"] == len(seen)


# ---- Rhubarb ------------------------------------------------------------------------------------------------------------
CUES = {"metadata": {}, "mouthCues": [{"start": 0.0, "end": 0.2, "value": "X"}, {"start": 0.2, "end": 0.5, "value": "D"},
                                      {"start": 0.5, "end": 0.7, "value": "A"}, {"start": 0.7, "end": 1.0, "value": "C"}]}


def test_rhubarb_cues_to_track_and_validation():
    cues = RB.parse_cues(json.dumps(CUES))
    assert [c[2] for c in cues] == ["X", "D", "A", "C"]
    tr = RB.cues_track(cues, 1.0, 20)
    assert len(tr) == 20 and tr[0] == 0.0 and tr[6] == V.OPEN["AI"] and tr[12] == V.OPEN["MBP"] and tr[16] == V.OPEN["E"]
    assert [s for _, _, s in RB.shape_names(cues)] == ["REST", "AI", "MBP", "E"]
    with pytest.raises(ValueError):
        RB.parse_cues({"mouthCues": [{"start": 0, "end": 1, "value": "Z"}]})


def _fake_rhubarb(tmp_path):
    exe = tmp_path / "rhubarb"
    exe.write_text("#!/bin/bash\nout=''\nwhile [ $# -gt 0 ]; do if [ \"$1\" = '-o' ]; then out=$2; shift; fi; shift; done\n"
                   f"cat > \"$out\" <<'EOF'\n{json.dumps(CUES)}\nEOF\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return str(exe)


def test_rhubarb_binary_runs_and_mouth_for_clip_prefers_it(tmp_path, monkeypatch):
    exe = _fake_rhubarb(tmp_path)
    wav = str(tmp_path / "a.wav")
    from studio.sound.mix import write_wav

    write_wav(wav, np.zeros(16000, np.float32), 16000)
    assert [c[2] for c in RB.run_rhubarb(wav, "hola", binary=exe)] == ["X", "D", "A", "C"]
    monkeypatch.setenv("HYPERCARTOON_RHUBARB", exe)
    trk, method = EP.mouth_for_clip(np.zeros(16000, np.float32), 16000, "hola", MouthStyle(fps=20), "auto")
    assert method == "rhubarb" and trk[6] == V.OPEN["AI"]
    monkeypatch.delenv("HYPERCARTOON_RHUBARB")
    monkeypatch.setenv("PATH", "/nonexistent")
    _, method2 = EP.mouth_for_clip(np.zeros(16000, np.float32), 16000, "hola", MouthStyle(fps=20), "auto")
    assert method2 in ("text", "words")  # falls back without the binary


def test_word_timed_visemes_leave_gaps_closed():
    tr = V.viseme_track_words([(0.0, 0.4, "aaa"), (0.8, 1.2, "ooo")], 1.2, 25)
    assert tr[:8].max() > 0.5 and tr[10:18].max() == 0.0 and tr[22:29].max() > 0.5  # open | gap closed | open


# ---- PySceneDetect adapter -----------------------------------------------------------------------------------------
def test_scenedetect_scene_list_to_frame_bounds():
    b = IG.bounds_from_scenes([(0.0, 2.0), (2.0, 5.0), (5.0, 5.0)], 10.0, 80)
    assert b == [(0, 20), (20, 80)] and IG.bounds_from_scenes([], 10.0, 80) is None


# ---- dataset ------------------------------------------------------------------------------------------------------------
def _video(path, secs=7, fps=16, cut=48):
    w = imageio.get_writer(path, fps=fps)
    for t in range(secs * fps):
        f = np.zeros((48, 80, 3), np.uint8)
        f[:, :, (t // cut) % 3] = 90
        f[10:20, t % 60 : t % 60 + 10] = 255
        w.append_data(f)
    w.close()


def test_training_set_matches_precomp_text_and_dataset_formats(tmp_path):
    show = tmp_path / "Show" / "S01"
    show.mkdir(parents=True)
    for e in (1, 2):
        _video(str(show / f"E0{e}.mp4"))
    ws = tmp_path / "MiSerie"
    tui.run_learning(str(tmp_path / "Show"), str(ws), io.StringIO())
    d = ws / "dataset"
    assert (d / "COMANDOS.md").exists() and (d / "text_input.json").exists()
    ti = json.load(open(d / "text_input.json"))
    k, v = next(iter(ti.items()))
    assert "video_sample_" in v["mp4"] and set(v) == {"text", "scene_start", "scene_end", "mp4"}  # what precomp_text.py reads
    assert v["text"].startswith("MiSerie animation style.")
    plan = json.load(open(ws / "plan.json"))
    stage = plan["stages"][0]["seconds"]
    rows = [json.loads(l) for l in open(d / f"train_{stage}s.jsonl")]
    assert rows and set(rows[0]) == {"vid_emb", "text_chunk_emb", "control", "loss_mask"} and len(rows[0]["text_chunk_emb"]) == stage // 3
    from hypercartoon.models.cogvideo import control_data as CD

    z = CD.load_control(str(d / rows[0]["control"]))
    assert z["frame_feats"].shape == (CD.latent_frames(stage), 4)  # one feature vector per latent frame
    assert rows[0]["vid_emb"].startswith("vid/") and rows[0]["text_chunk_emb"][0].startswith("txt/text-3s-493")
    clips = json.load(open(d / f"clips_{stage}s.json"))
    assert clips[0]["chunks"][0]["scene_start"] is True and "ffmpeg" in open(d / f"make_clips_{stage}s.sh").read()
    kit = json.load(open(ws / "episode_kit.json"))
    assert kit["ready"]["training_dataset"] and any(p["key"] == "dataset" for p in kit["phases"])


def test_heuristic_caption_mentions_what_was_measured():
    c = DS.HeuristicCaptioner().caption({"motion": 0.12, "brightness": 0.7, "palette": [[220, 40, 40], [50, 80, 220]], "speech": 0.6})
    assert "bright" in c and "fast action" in c and "red" in c and "blue" in c and "dialogue" in c
    with pytest.raises(ValueError):
        DS.get_captioner("nope")


# ---- external tools -----------------------------------------------------------------------------------------------------
def test_postprocess_runs_chain_skips_missing_and_validates_placeholders(tmp_path):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"video")
    steps = [{"name": "copy", "cmd": "cp {video} {out}"},
             {"name": "ghost", "cmd": "definitely-not-installed-tool {video} {out}"},
             {"name": "sync", "when": "has_audio", "cmd": "cp {video} {out}"},
             {"name": "typo", "cmd": "cp {video} {output}"}]
    log = PP.run_steps(steps, str(src), None, str(tmp_path / "w"), "ep")
    st = {r.get("name"): r["status"] for r in log if "name" in r}
    assert st == {"copy": "ok", "ghost": "skipped", "sync": "skipped", "typo": "error"}
    assert log[-1]["final"].endswith("ep.copy.mp4") and os.path.exists(log[-1]["final"])
