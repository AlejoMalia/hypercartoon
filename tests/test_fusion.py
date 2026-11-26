import io
import json
import math
import os

import imageio
import numpy as np
import pytest

from hypercartoon.models.cogvideo import prompts as PR
from studio import fusion as F
from studio import pipeline as PL
from studio import tui
from studio.characters import Registry


def _prof(cuts, motion, bright, shot, palette, name="x"):
    return {"n_videos": 2, "total_seconds": 600.0, "fps": 16.0, "aspect": 1.5, "motion": motion, "brightness": bright,
            "shot_len": {"median": shot, "p10": shot / 2, "p90": shot * 2}, "cuts_per_min": cuts, "palette": palette,
            "episode_seconds": [300.0, 300.0], "chapter_seconds": 300.0, "style_prompt": f"{name} style", "seasons": {"S01": {}}}


def test_profile_blend_is_geometric_for_pacing_and_linear_light_for_colour():
    a = _prof(40.0, 0.10, 0.8, 1.5, [[0, 0, 0]], "A")
    b = _prof(10.0, 0.02, 0.4, 6.0, [[255, 255, 255]], "B")
    m = F.blend_profiles([a, b], [1, 1], ["A", "B"])
    assert abs(m["cuts_per_min"] - 20.0) < 1e-6 and abs(m["shot_len"]["median"] - 3.0) < 1e-6  # geometric means
    assert abs(m["motion"] - 0.06) < 1e-9 and abs(m["brightness"] - 0.6) < 1e-9
    assert m["palette"][0] == [188, 188, 188]  # black+white in linear light, not 128
    assert "A (50%)" in m["style_prompt"] and "B (50%)" in m["style_prompt"] and m["n_videos"] == 4
    heavy = F.blend_profiles([a, b], [3, 1], ["A", "B"])
    assert heavy["cuts_per_min"] > m["cuts_per_min"] and heavy["sources"][0]["weight"] == 0.75


def test_mouth_blend():
    A = {"fps": 24, "hold_frames": 2, "levels": [0, 0.5, 1.0], "lead_s": 0.04, "gain": 1.0, "n_samples": 10}
    B = {"fps": 12, "hold_frames": 4, "levels": [0, 0.3, 0.6, 1.0], "lead_s": 0.0, "gain": 0.6, "n_samples": 5}
    m = F.blend_mouth_styles([A, B], [1, 1])
    assert m["fps"] == 18 and m["hold_frames"] == 3 and len(m["levels"]) == 4 and abs(m["lead_s"] - 0.02) < 1e-9
    assert F.blend_mouth_styles([None, B], [1, 1])["fps"] == 12 and F.blend_mouth_styles([None, None], [1, 1]) is None


def _reg(names, voices=1):
    r = Registry()
    for i, n in enumerate(names):
        v = np.zeros(8)
        v[i] = 1.0
        vid = r.visual.add(v)
        r.names[vid] = n
        r.presence[vid] = 20.0
    for j in range(voices):
        v = np.zeros(8)
        v[j + 3] = 1.0
        a = r.voice.add(v)
        r.speech[a] = 10.0
        r.overlap[f"1|{a}"] = 8.0
    r.total_time = 60.0
    return r


def test_registry_merge_shifts_ids_and_disambiguates_names(tmp_path):
    ra, rb = _reg(["FOX", "OWL"]), _reg(["FOX", "BEAR"], voices=2)
    for n, r in (("a", ra), ("b", rb)):
        r.save(str(tmp_path / f"{n}.json"))
    merged, maps = F.merge_registries([json.load(open(tmp_path / "a.json")), json.load(open(tmp_path / "b.json"))], ["A", "B"])
    json.dump(merged, open(tmp_path / "m.json", "w"))
    m = Registry.load(str(tmp_path / "m.json"))
    assert len(m.visual.sums) == 4 and len(m.voice.sums) == 3 and m.total_time == 120.0
    assert sorted(m.names.values()) == ["BEAR", "FOX_A", "FOX_B", "OWL"]
    assert set(maps[1][0].values()).isdisjoint(maps[0][0].values())
    assert len(m.characters()) == 4


def test_state_dict_soup_and_task_arithmetic():
    base = {"w": np.ones((2, 2)), "b": np.zeros(2)}
    a = {"w": np.full((2, 2), 3.0), "b": np.ones(2)}
    b = {"w": np.full((2, 2), 5.0), "b": np.full(2, 3.0)}
    soup = F.merge_state_dicts([a, b], [1, 1])
    assert np.allclose(soup["w"], 4.0) and np.allclose(soup["b"], 2.0)
    ta = F.merge_state_dicts([a, b], [0.5, 0.5], base=base)  # base + 0.5*(a-base) + 0.5*(b-base)
    assert np.allclose(ta["w"], 1 + 0.5 * 2 + 0.5 * 4) and np.allclose(ta["b"], 0 + 0.5 * 1 + 0.5 * 3)
    with pytest.raises(ValueError):
        F.merge_state_dicts([a, {"w": a["w"]}], [1, 1])
    with pytest.raises(ValueError):
        F.merge_state_dicts([a, {"w": np.ones((3, 3)), "b": np.ones(2)}], [1, 1])


def test_prompt_file_with_style_mix(tmp_path):
    vid = [{"text": "fox runs, style A", "requires_scene_transition": False, "alt_text": "fox runs, style B", "mix": 0.4},
           {"text": "owl sits, style A", "requires_scene_transition": True, "alt_text": "owl sits, style B", "mix": 0.4}]
    p = tmp_path / "p.jsonl"
    p.write_text(json.dumps(vid) + "\n" + json.dumps([{"text": "plain"}]) + "\n")
    v = PR.load_prompts(str(p))
    texts, negs, alts, mix = PR.split_video(v[0])
    assert texts[0].endswith(PR.SCENE_END_TOKEN) and texts[1].startswith(PR.SCENE_START_TOKEN)
    assert alts[0].endswith(PR.SCENE_END_TOKEN) and alts[1].startswith(PR.SCENE_START_TOKEN) and abs(mix - 0.4) < 1e-9
    assert PR.split_video(v[1])[2:] == (None, 0.0)  # old-format prompts keep working
    a, b = np.zeros((3, 4)), np.ones((3, 4))
    assert np.allclose(PR.blend_embeddings(a, b, 0.25), 0.25) and PR.blend_embeddings(a, b, 0.0) is a
    with pytest.raises(ValueError):
        PR.blend_embeddings(a, b, 1.5)


def _video(path, cut_every, secs=6, fps=16):
    w = imageio.get_writer(path, fps=fps)
    for t in range(secs * fps):
        k = t // cut_every
        f = np.zeros((48, 80, 3), np.uint8)
        f[:, :, k % 3] = 60 + 50 * (k % 3)
        f[10:20, (t * (1 + k % 2)) % 60 : (t * (1 + k % 2)) % 60 + 10] = 255
        w.append_data(f)
    w.close()


def test_fuse_two_projects_and_create_with_style_mix(tmp_path):
    projs = []
    for name, cut in (("rapido", 12), ("lento", 48)):
        src = tmp_path / name / "S01"
        src.mkdir(parents=True)
        for e in (1, 2):
            _video(str(src / f"E0{e}.mp4"), cut)
        ws = tmp_path / f"proj_{name}"
        outs, kit, _ = tui.run_learning(str(tmp_path / name), str(ws), io.StringIO())
        projs.append(str(ws))
    a, b = (json.load(open(os.path.join(p, "profile.json"))) for p in projs)
    assert a["cuts_per_min"] > b["cuts_per_min"]
    out = str(tmp_path / "fused")
    ctx = {"srcs": projs, "weights": [3, 1], "out": out, "mode": "embedding"}
    outs = PL.run(F.FUSION_PHASES, ctx)
    assert not [o for o in outs if o.status == "error"], [o.note for o in outs]
    f = json.load(open(os.path.join(out, "profile.json")))
    assert b["cuts_per_min"] < f["cuts_per_min"] < a["cuts_per_min"] and f["n_videos"] == 4
    rec = json.load(open(os.path.join(out, "fusion.json")))
    assert rec["embedding_pair"]["primary"] == "proj_rapido" and abs(rec["embedding_pair"]["mix"] - 0.25) < 1e-6
    assert os.path.exists(os.path.join(out, "episode_kit.json"))
    from studio import episode as EP

    ectx = EP.make_ctx(out, os.path.join(out, "episodes", "e1"), "INT. SALA - DIA\n\nZORRO\nHola a todos.\n", emotion="lexicon")
    eouts = PL.run([p for p in EP.EPISODE_PHASES if p.key in ("story", "emotion", "plan")], ectx)
    assert not [o for o in eouts if o.status == "error"], [o.note for o in eouts]
    line = json.loads(open(os.path.join(out, "episodes", "e1", "prompts.jsonl")).readline())
    assert line[0]["mix"] == pytest.approx(0.25) and line[0]["alt_text"] != line[0]["text"]
    assert "proj_rapido" in rec["style_prompts"] and rec["style_prompts"]["proj_lento"] in line[0]["alt_text"]
