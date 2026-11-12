# Master Ankur transparent renders

Prepared from the founder's seven 2048 × 2048 PNGs on 12 November 2026.
These replace the smaller brand-sheet crops in the frontend. Original downloads
remain unchanged. The PNGs here have real alpha; the checkerboard is removed.

`AnnaData-Frontend-main/tools/prepare_ankur.py` uses Pillow only. Run it with the
source directory and this output directory as arguments, from the repository root.
The source filename mapping is recorded in `FILES` in that script.

The extraction flood-fills bright neutral background pixels from the exterior,
preserving enclosed eye highlights. A one-source-pixel contraction and 0.6-pixel
feather reduce grey edge contamination. This is a deterministic cutout, not an
exact recovery of every original translucent fur strand.

The two source talking images differ in texture as well as mouth size. The final
half-open PNG uses the open-mouth image's body, eyes, alpha and lighting, with a
feathered mouth-only patch from the smaller-mouth render. The two mouths have a
subtle size difference; no new expression was invented.

All app exports use the same 500-pixel scaling and (6, 31) placement on a 512-pixel
canvas, preserving torso alignment rather than centering different arm silhouettes.
The seven WebP files total approximately 190 KB. High-resolution PNGs are kept here
for future editing and are not included in the frontend's public asset directory.

Visual checks: all seven poses on cream and dark green backgrounds, plus enlarged
sprout/edge and mouth-patch inspection. Frontend: 13 suites, 114 tests passed.
Existing React test warnings and outdated Browserslist warnings remain.

The production build passed. Headless Chrome checks of that build at 375 × 812
(home) and 360 × 780 (voice listening with a fake microphone) showed clean artwork;
home had no horizontal overflow. This does not verify a physical phone microphone
or the full live speech loop. Temporary browser profiles and screenshots were removed.
