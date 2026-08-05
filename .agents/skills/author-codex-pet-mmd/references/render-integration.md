# Private Render and Integration

## Keep the workspace private

Create a temporary working directory outside the repository. Store the PMX, textures, temporary `mmd_tools`, rendered frames, imported Blender data, credits, and generated C there. Keep private derivatives out of commits and shared logs.

Pass an absolute PMX path because Blender requires it, but expose it only to the local process. Use a non-path `--provenance-name`; reject an absolute value. Do not echo, persist, screenshot, or report the PMX path.

Treat the Sakamata Chloe brief in the project documentation as an example for that exact authorized model only. Replace provenance and rights fields for every other model. Never treat the example as permission.

## Render a smoke set

Run the repository script through a compatible Blender and `mmd_tools` installation. Substitute local private paths without recording them in project files:

```bash
blender --background --factory-startup \
  --python tools/render_mmd_pet_blender.py -- \
  --pmx <private-absolute-model-path> \
  --output-dir <private-output-dir> \
  --mmd-tools-dir <private-mmd-tools-dir> \
  --mmd-python-modules <private-python-modules-dir> \
  --provenance-name "Authorized private MMD model" \
  --rights-note "Private derivative authorized by the requester; do not redistribute." \
  --only IDLE_0,RUNNING_0,WAITING_0,REVIEW_0,FAILED_0,LOOK_067_5,LOOK_157_5,LOOK_247_5,LOOK_337_5
```

Omit `--keep-mask` so the renderer hides both `マスク` and `マスク瞳`. Add it only when the authorized design brief requires visible masks.

Inspect the smoke set for loaded textures, alpha, safe padding, model-like asymmetry, status differences, cardinal gaze, and path-free credits. Then remove `--only` and render the full selected profile. The default smooth profile produces 152 frames and `motion_manifest.json`.

## Validate render output

Require every filename listed by `motion_manifest.json`. For the default smooth profile, require the compatibility layout `IDLE` 12, `RUNNING_RIGHT` 8, `RUNNING_LEFT` 8, `WAVING` 8, `JUMPING` 30, `FAILED` 18, `WAITING` 14, `RUNNING` 24, `REVIEW` 14, and `LOOK` 16: 152 frames total. For a version-2 dynamic profile, require its declared 1-65535 frames, contiguous action ranges, equal directional-running counts, and a `LOOK` count divisible by four. Require every image to decode as exact `152x204` RGBA with transparent edge padding. Confirm `CREDITS.txt` contains only descriptive provenance, optional public pages, credits, and rights notes.

A version-2 manifest may define more frames when the complete linked firmware still preserves the required final 512 KiB application-partition reserve. The converter keeps those dynamic playback entries directly. Legacy 73-frame atlas input remains supported by pointer-resampling onto the default 152-entry compatibility profile, so compatibility does not require duplicating its bitmaps.

Create contact sheets or short loops in the private workspace. Do not publish them unless the rights grant covers publication.

## Convert frames

```bash
python3 tools/convert_codex_pet_p4.py \
  --frames-dir <private-output-dir> \
  --output <private-generated-c-path>
```

Require converter completion and retain the generated C privately. Do not treat generation as visual approval.

## Build with the external asset

Configure the ESP32-P4 build with the generated C file as `CODEX_PET_ASSET_SOURCE`. Supply an absolute path locally, but keep logs and reports generic:

```bash
idf.py -B <private-build-dir> \
  -D CODEX_PET_ASSET_SOURCE=<private-absolute-generated-c-path> \
  build
```

Confirm the build reports an external override without printing the source path. Run the repository tests covering the frame contract, MMD renderer, provenance privacy, and CMake override before reporting build evidence.

## Prove each layer

Record evidence separately:

1. **Render:** all manifest-listed exact-size RGBA files, `motion_manifest.json`, padding, masks removed, readable status and gaze, safe credits.
2. **Conversion:** successful raw RGB565A8 or JPEG-plus-alpha generation, a complete manifest-defined playback map, frame-contract tests, and confirmation that the complete linked application image retains the final 512 KiB reserve.
3. **Build:** successful external-source firmware build with path-safe output.
4. **Hardware:** successful flash plus on-panel observation of idle, running, waiting, review, internal failure where testable, and all four gaze slides.

For hardware QA, inspect scale, transparency, clipping, color, flicker, cadence, state transitions, and prolonged stability. Capture only rights-permitted evidence, and scrub private paths or model data from reports.

State a missing layer explicitly. Never infer hardware success from a build or visual quality from numeric pose differences.
