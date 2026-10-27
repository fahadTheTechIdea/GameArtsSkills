# Real-scene spike (evidence, not shipped)

An early, informal P16.0 run of the terrain reader on a real painted reference the owner supplied "for testing": three pixel-art scenes (beach, village, forest) in one JPEG. The image is
not in the repository (it is the owner's reference art). To rerun, put it beside the scripts as `reference.jpg` and run `run_real.py` (the framework's palette and an automatic reading),
then `seeded.py` (village) and `seeded2.py` (beach and forest): terrains defined by sample points, objects filled from the nearest ground. The sample coordinates were chosen by looking at
this picture. `results.json` has the numbers; the plan's research document (section 3.6) reads them.

Not shown: any ground truth (there is none), a segmenter's result, the art in an engine.
