"""Frame analysis of linked video files (Phase 3 WP-11): flash, faces, open captions."""

import os

import cv2
import numpy as np
import pytest

from ka11y.accessibility.rules.media.video_analysis import analyze_media_records, analyze_video_file, is_direct_video


def _clip(path, frames, fps=20, flash_every=None):
    w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (160, 120))
    assert w.isOpened()
    for i in range(frames):
        v = 255 if (flash_every and (i // flash_every) % 2 == 0) else 40
        w.write(np.full((120, 160, 3), v, dtype=np.uint8))
    w.release()


def test_is_direct_video():
    assert is_direct_video("https://x.com/a.mp4?x=1") and not is_direct_video("https://x.com/live.m3u8")


def test_static_clip_has_no_flash_and_no_face(tmp_path):
    p = str(tmp_path / "s.mp4"); _clip(p, 60)
    a = analyze_video_file(p)
    assert a["flash"]["max_flashes_per_second"] <= 3 and a["faces"]["talking_head"] is False


def test_flashing_clip_detected(tmp_path):
    p = str(tmp_path / "f.mp4"); _clip(p, 80, fps=20, flash_every=2)  # 5 flashes / s
    a = analyze_video_file(p)
    assert a["flash"]["max_flashes_per_second"] > 3 and a["flash"]["flashing_area"] > 0.5


def test_records_get_findings_and_annotations(tmp_path):
    p = str(tmp_path / "f.mp4"); _clip(p, 80, fps=20, flash_every=2)
    rec = {"tag": "video", "src": "https://ex.com/v.mp4", "page_url": "https://ex.com/", "wcag_1_2_2_status": "FAILED", "wcag_1_2_2_violation": "no captions"}
    def fake_fetch(src):
        import shutil; dst = str(tmp_path / "copy.mp4"); shutil.copy(p, dst); return dst
    fs = analyze_media_records([rec], "https://ex.com/", fetch=fake_fetch, use_ocr=False)
    ids = {f["rule_id"]: f for f in fs}
    assert ids["python_2_3_1_video_flash"]["status"] == "fail" and ids["python_2_3_2_video_flash"]["status"] == "fail"
    assert "video_analysis" in rec and rec["wcag_1_2_2_status"] == "FAILED"


def test_open_captions_annotation_via_ocr_stub(tmp_path):
    p = str(tmp_path / "s.mp4"); _clip(p, 60)
    rec = {"tag": "video", "src": "https://ex.com/v.mp4", "page_url": "https://ex.com/", "wcag_1_2_2_status": "FAILED", "wcag_1_2_2_violation": "no captions"}
    def fake_fetch(src):
        import shutil; dst = str(tmp_path / "c.mp4"); shutil.copy(p, dst); return dst
    def fake_analyze(path, ocr=None):
        return {"fps": 20, "flash": {"max_flashes_per_second": 0, "flashing_area": 0}, "faces": {"sampled": 2, "with_face": 2, "talking_head": True, "possible_corner_interpreter": False}, "captions": {"sampled": 2, "text_bands": 2, "open_captions_likely": True}}
    fs = analyze_media_records([rec], "https://ex.com/", fetch=fake_fetch, analyze=fake_analyze, use_ocr=False)
    assert rec["wcag_1_2_2_status"] == "NEEDS_REVIEW" and "G93" in rec["wcag_1_2_2_violation"]
    assert fs[0]["status"] == "pass"
