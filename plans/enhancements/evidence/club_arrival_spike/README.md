# Club-arrival spike (evidence, not shipped)

The layered-map pipeline on the owner's Cozy Soccer club-arrival mockup (a candidate in their own repository, `plans/city-design-review/d270/mockups/39-club-arrival.png`, read-only; the
image is not copied here). To rerun, copy it beside the scripts as `club_arrival.png`, then `python cozy_run.py 32` (terrains and colour occluders defined by sample points, read with
`gamearts_layered_map.py`), `python ambiguity.py` (the near-tie margin that was tried and rejected) and `python masked.py` (an occlusion mask drawn by hand, against colour-only reading).
The sample points and mask rectangles were chosen by looking at this picture. `results.json` has the numbers; section 3.7 of the research document reads them.

Not shown: any ground truth, a segmenter's masks, the art in an engine, tilesets made for these terrains.
