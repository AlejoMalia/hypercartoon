"""Perception layer: object tracking + frame/motion coherence, decoupled from the generative model.

Core (labelmap, coherence, associate) is numpy/scipy only so it runs anywhere. Heavy backends
(SAM 2, Grounding DINO, Ultralytics, Roboflow trackers, BoxMOT) are imported lazily in `backends`.
"""
from hypercartoon.perception.coherence import coherence_report
from hypercartoon.perception.labelmap import load_labelmaps, save_labelmaps

__all__ = ["coherence_report", "load_labelmaps", "save_labelmaps"]
