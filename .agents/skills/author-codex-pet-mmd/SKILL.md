---
name: author-codex-pet-mmd
description: Author, render, convert, and verify an authorized private MMD, PMX, or generated-video character as Codex Pet status animation for the ESP32-P4 dynamic manifest-v2 playback and exact 152x204 asset contract. Use for rights and provenance checks, Blender pose or expression design, fixed-camera video curation, mask-material handling, private offline frame rendering, compressed RGB565A8 integration, or independent visual and hardware QA.
---

# Author Codex Pet MMD

Produce a private, rights-safe MMD derivative whose status is readable on the target display. Treat rendering, conversion, firmware build, and hardware display as separate proof layers.

## Enforce the rights gate

1. Obtain an explicit statement that the requester owns the model or has permission to create the intended private derivative.
2. Confirm that the permission covers the requested use, including any redistribution, publication, screenshots, or generated C assets.
3. Stop before importing or rendering when authorization or scope is unclear. Do not infer rights from possession of a PMX file, a download link, prior private use, or available credits.
4. Keep the PMX, textures, imported `.blend`, rendered PNGs, and generated C outside the repository unless redistribution rights explicitly allow inclusion.
5. Record a descriptive provenance label, public model or license page when appropriate, credits, and a rights note in `CREDITS.txt`. Never record the absolute PMX path.

Treat the Sakamata Chloe brief and command examples as model-specific design context only. Never reuse them as authorization for another run, user, model copy, derivative, or distribution channel.

## Establish the animation contract

- Treat 152 frames as the default smooth and legacy compatibility profile, not a firmware-wide ceiling: `IDLE` 12, `RUNNING_RIGHT` 8, `RUNNING_LEFT` 8, `WAVING` 8, `JUMPING` 30, `FAILED` 18, `WAITING` 14, `RUNNING` 24, `REVIEW` 14, and `LOOK` 16.
- Prefer `motion_manifest.json` version 2 for richer animation. It may define 1-65535 playback frames with per-action ranges and per-frame durations; those frames play directly without being resampled onto 152 entries. Keep `LOOK` divisible by four and the two directional-running counts equal.
- Preserve exact `152x204` transparent RGBA PNG input. The manifest carries the stored frame list, action ranges, idle loop count, and firmware durations.
- Author at 24 or 30 fps when motion needs it. Express cadence through durations such as 42 ms or 33 ms, then use deliberate holds or repeated terminal frames where semantic readability needs more time. Frame count alone does not define smoothness.
- Keep the legacy 73-cell Codex Pet v2 atlas compatible. Only the compatibility path pointer-resamples its action ranges onto the default 152 playback entries rather than duplicating bitmap storage.
- Check the complete application image budget with the final 512 KiB of the application partition reserved. Do not approve extra stored frames from frame count alone.
- Treat `idle`, `running`, `waiting`, and `review` as the externally meaningful lifecycle states.
- Treat `failed` as an internal animation/error presentation, not a fifth host lifecycle state. Do not publish or emit it as external lifecycle telemetry unless the product contract changes.
- Preserve legacy action slots required by the transport contract even when the authored intent is status-first.
- Split the `LOOK` action into four equal cardinal slide clips: up, screen-right, down, and screen-left. The default profile uses four frames per direction; dynamic profiles may use more.

Read [references/motion-design.md](references/motion-design.md) before changing poses, expressions, timing, blinks, or gaze.

## Author the model

1. Import the PMX through the repository Blender renderer and a compatible `mmd_tools` installation.
2. Keep source files in a private working directory outside the checkout.
3. Hide both model-authored mask materials `マスク` and `マスク瞳` by default. Use `--keep-mask` only when the authorized brief explicitly requires the masks visible.
4. Build every neutral or low-energy pose from a readable asymmetric, model-like stance: shift weight, stagger feet, relax one knee, vary toe direction, and offset the torso or head.
5. Avoid symmetrical locked knees, punishment-like kneeling, forced-exercise silhouettes, collapse, or distress unless the internal failed animation specifically requires a restrained error cue.
6. Make motion feel slow and lazy through small arcs, eased weight transfer, deliberate holds, and sparse blinks. Do not create frantic motion by changing every control on every frame.
7. Differentiate statuses by silhouette, center of mass, head direction, gaze, expression, and gesture. Do not rely on filenames or tiny numeric deltas.
8. Treat body orientation as an animation channel. Use opposing three-quarter or side-facing views where they reveal foot depth and joint mechanics; reserve the near-front neutral for gaze clips or actions that need direct eye contact. Do not leave every status facing the camera.

## Render privately

Follow [references/render-integration.md](references/render-integration.md) for isolated setup and exact commands.

1. Run Blender offline with `--background --factory-startup` and the repository renderer.
2. Pass the private absolute PMX path only at local invocation time. Do not paste it into source, documentation, chat, screenshots, build logs, provenance, or reports.
3. Run a small `--only` smoke render first. Inspect import, textures, masks, framing, alpha, pose readability, and credits.
4. Render the complete selected motion profile only after the smoke set passes. The default smooth profile emits 152 frames; a dynamic manifest-v2 profile may emit more at 24 or 30 fps.
5. Reject clipped frames and any frame without transparent edge padding.

## Curate generated video privately

1. Treat MP4 as authoring input, not the embedded runtime format. Extract selected frames, remove the background, and package the result through the same manifest-v2 converter path.
2. Require one fixed camera, stable framing and scale, no cuts, no zoom, and no camera orbit within an action. Rotate or pose the character to reveal different directions instead of moving the camera.
3. Preserve the highest useful source resolution during matting and downsampling, but judge the final transparent `152x204` pixels. High source resolution cannot change the display asset dimensions.
4. Remove green or white spill as well as border-connected background. Verify transparent edge padding and inspect enclosed gaps, hair, fingers, footwear, and floor shadows for halos.
5. Curate loops explicitly. Use ping-pong only for reversible low-energy motion; preserve forward order for locomotion, and measure the seam rather than assuming it is smooth.
6. Map semantic intent, not filenames: a legacy `JUMPING` slot may hold a happy or excited dance when that better matches the product status, provided the documentation and review state that mapping clearly.

## Convert and integrate

1. Convert the frame directory with `tools/convert_codex_pet_p4.py --frames-dir` into a private `pet_generated.c`.
2. Point the ESP32-P4 build at that file with the absolute `CODEX_PET_ASSET_SOURCE` build option. Keep the source path local and ensure logs describe only an external override.
3. Do not copy private model assets or generated derivatives into tracked paths as a shortcut.
4. Run the targeted renderer, converter, metadata, and firmware-contract tests before claiming integration.

## Require layered evidence

Collect and label each layer independently:

- **Render evidence:** confirm the manifest-listed, uniquely named `152x204` RGBA PNGs, transparent padding, visible masks-off behavior, readable poses, and path-free `CREDITS.txt`.
- **Conversion evidence:** confirm converter success, complete manifest-defined playback mapping, correct raw or JPEG-plus-alpha output generation, the 512 KiB reserved-tail budget check on the complete linked app, and targeted test results.
- **Build evidence:** confirm the firmware build consumes the external generated C source and finishes without exposing the private asset path.
- **Hardware evidence:** confirm the flashed target displays the asset and demonstrate real lifecycle transitions, gaze slides, alpha edges, scale, cadence, and stability on the panel.

Never substitute one evidence layer for another. A render does not prove conversion, a build does not prove display behavior, and a photograph does not prove every status mapping.

## Run independent visual QA

1. Give a reviewer the rendered frames or contact sheets without pose parameters or an explanation of intended numeric differences.
2. Compare representative adjacent frames and all status key poses at the target display scale.
3. Require the reviewer to identify each status from the visuals, recognize every cardinal gaze direction, and flag clipping, flicker, mask remnants, alpha halos, jitter, or punitive silhouettes.
4. Reject any sequence whose controls or pose dictionaries differ numerically but whose rendered frames look identical in silhouette, expression, gaze, or motion at target scale.
5. Revise the authored motion, render again, and repeat independent review. Do not waive visual failure because unit tests pass.

Finish only after the rights gate and all applicable evidence layers pass, with any unavailable hardware evidence stated explicitly.
