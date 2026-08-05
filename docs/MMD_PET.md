# MMD / PMX Pet Pipeline

Codex Pet does not render PMX or VRM on the ESP32-P4. Blender imports and poses
the model offline, renders transparent `152x204` PNG frames, and the existing
converter packs those frames as LVGL RGB565A8 data. The model, textures, blend
file, rendered frames, and generated C asset should remain private unless their
redistribution scope is explicit.

## Current toolchain

- Blender 5.1.x
- [MMD Tools v4.5.13](https://github.com/MMD-Blender/blender_mmd_tools/releases/tag/v4.5.13)
- `ffmpeg`
- ESP-IDF 5.5.x for the JC4880P443C-I-W target

MMD Tools v4.5.13 declares Blender 4.2-5.1 compatibility. A temporary Blender
extension repository keeps the test installation separate from the user's
normal Blender profile:

```sh
runroot=/tmp/codex-pet-mmd
blender=/Applications/Blender.app/Contents/MacOS/Blender

mkdir -p "$runroot/config" "$runroot/scripts" "$runroot/extensions" "$runroot/repo"
curl -L -o "$runroot/mmd_tools.zip" \
  https://github.com/MMD-Blender/blender_mmd_tools/releases/download/v4.5.13/mmd_tools-v4.5.13-bl4.2.zip

env BLENDER_USER_CONFIG="$runroot/config" \
    BLENDER_USER_SCRIPTS="$runroot/scripts" \
    BLENDER_USER_EXTENSIONS="$runroot/extensions" \
    "$blender" --command extension repo-add mmd_tmp \
      --name "MMD temp" --directory "$runroot/repo" --clear-all

env BLENDER_USER_CONFIG="$runroot/config" \
    BLENDER_USER_SCRIPTS="$runroot/scripts" \
    BLENDER_USER_EXTENSIONS="$runroot/extensions" \
    "$blender" --command extension install-file -r mmd_tmp -e \
      "$runroot/mmd_tools.zip"
```

## Render private frames

The renderer hides the model-authored `マスク` and `マスク瞳` materials by
default, uses a mild perspective camera and a catwalk-like asymmetric stance,
and authors motion around Codex status semantics rather than the original pet
choreography. Pass `--keep-mask` only when the mask should remain visible.

```sh
frames=/tmp/codex-pet-mmd/frames

env BLENDER_USER_CONFIG="$runroot/config" \
    BLENDER_USER_SCRIPTS="$runroot/scripts" \
    BLENDER_USER_EXTENSIONS="$runroot/extensions" \
    "$blender" --background --factory-startup \
      --python tools/render_mmd_pet_blender.py -- \
      --pmx /absolute/path/to/model.pmx \
      --output-dir "$frames" \
      --mmd-module bl_ext.mmd_tmp.mmd_tools \
      --provenance-name "Sakamata Chloe MMD model" \
      --model-page https://3d.nicovideo.jp/works/td84836 \
      --credit "© COVER" \
      --rights-note "Authorized by the rights holder for this local prototype."
```

Use `--only IDLE_0,LOOK_067_5` for a fast import/render smoke test. A successful
default smooth run writes 152 RGBA PNGs, `motion_manifest.json`, and a local
`CREDITS.txt`. Every PNG must be exactly `152x204` RGBA. The provenance fields
come only from the explicit command-line metadata above; the renderer never
stores the absolute PMX path. For another model, replace or omit these Chloe
specific values rather than carrying its authorization or credit forward.

## Chloe motion direction

The initial choreography keeps the mask hidden but preserves Chloe's guarded
distance through a slightly side-on body line, a hand near the collar or face,
brief eye contact, and a look away. Her outward read is mysterious, coyly sexy,
and cool, not sentimental. The staging mix is roughly 40% cool, 20% lazy, 30%
mischievous/cute, and 10% embarrassed recovery. It should not read as either an
unbroken assassin pose or an unbroken soft-cute loop.

- `idle`: runway-like front/back feet, weight on the rear leg, relaxed shoulder,
  slow head turn, brief eye contact, then a small look away.
- `running`: a grounded, side-oriented light jog with a restrained forward
  center-of-mass shift and distributed pelvis/lumbar/chest lean, plus head
  counter-tilt, planted contact, toe-off, flight, and swing phases rather than
  a backward waist hinge, upright march, frontal cross-step, or cartoon sprint.
  A near-side body yaw and a dedicated apex key keep the lean and flight visible
  at native pet resolution without raising the recovery foot prematurely.
- `waiting`: guarded side stance with lazy toe play, delayed head scan, and a
  cool or coyly impatient expression rather than a worried one.
- `review`: one foot drawn back, hand near the chin/collar, narrow gaze scanning
  the work, then brief direct eye contact before disengaging; it remains cool
  and analytical rather than emotional.
- `failed`: a clear crossed-step mistake and balance correction, a short
  surprised beat, then a deliberate return to the cool baseline. It must not
  end as a slump, punishment pose, or sentimental/downcast expression.
- slide gaze: uses a stable neutral catwalk stance while easing the head and
  eyes toward up, right, down, or left; closing the slide restores the current
  lifecycle loop, so the feet do not skate during the transition.

The unused compatibility actions retain the short cute-burst vocabulary (small
wave or hop), but lifecycle statuses do not depend on the original Codex Pet
action rules.

## Animation meaning

The renderer's default smooth raw profile has this 152-entry playback layout:

| Action | Frames |
| --- | ---: |
| `IDLE` | 12 |
| `RUNNING_RIGHT` | 8 |
| `RUNNING_LEFT` | 8 |
| `WAVING` | 8 |
| `JUMPING` | 30 |
| `FAILED` | 18 |
| `WAITING` | 14 |
| `RUNNING` | 24 |
| `REVIEW` | 14 |
| `LOOK` | 16 |

The renderer records its stored-frame contract and timings in
`motion_manifest.json`. For the default profile, the converter uses the
152-entry layout above; legacy 73-frame atlas input remains compatible through
pointer resampling without storing 152 duplicate bitmaps. A custom version 2
manifest instead supplies dynamic action and playback counts, so a compressed
candidate can contain a larger set without being resampled to 152 entries. The
current private candidate uses 720 playback frames. Such a set is acceptable
only when the complete linked application still preserves the final 512 KiB of
the application partition; neither frame count nor converter payload size alone
proves that reserve. See [Private Video Pet Pipeline](VIDEO_PET.md) for the
dynamic manifest, compressed conversion, and build-size verification workflow.

Unless stated otherwise, the frame counts and timings below describe the
default 152-entry profile, not a version 2 custom manifest:

- The host-controlled lifecycle statuses are `idle`, `running`, `waiting`, and
  `review`; each has newly authored MMD body, head, leg, and expression motion.
- `failed` is a separate internal critical/reaction clip, not a fifth host
  lifecycle status.
- In the default 152-entry profile, the final 16 slots are four eased four-frame
  gaze clips: up, right, down, and left. A custom version 2 manifest may use
  larger equal quarters for the same cardinal order.
- Today, Settings, and Usage slide progress select the up, right, and down gaze
  frames respectively. The renderer also provides left gaze for touch reactions
  and future left-side navigation.
- Normal smooth idle loops `IDLE_0` through `IDLE_9` at 120 ms per frame;
  `IDLE_10` and `IDLE_11` complete an explicit blink reaction.
- High-motion `RUNNING` uses all 24 frames at 30 ms each; the 8-frame
  directional runs use 90 ms each for a roughly 0.72-second cycle. `JUMPING` uses its
  first 29 frames at 33 ms each, followed by a 180 ms landing hold.
- Waiting and review use 65 ms motion frames followed by a readable 180 ms hold.
- Each gaze transition uses three eased steps (65, 65, and 85 ms) followed by a
  650 ms cardinal hold. Its first frame matches `IDLE_0`, and its feet remain
  stable.
- Slide-driven gaze can temporarily replace any lifecycle sprite, not only
  idle. Closing the slide restores the current lifecycle action and resumes its
  timer.
- A rightward gaze-only drag on Home supplies the fourth slide direction: the
  character looks screen-left while the finger moves, then eases back to the
  current lifecycle pose on release. It intentionally does not open a fourth
  page.

## Convert and build

```sh
python3 tools/convert_codex_pet_p4.py \
  --frames-dir "$frames" \
  --output /tmp/codex-pet-mmd/pet_generated.c

source "$HOME/.espressif/frameworks/esp-idf-v5.5.1/export.sh"
idf.py -C esp32-p4 -B /tmp/codex-pet-mmd/build \
  -D CODEX_PET_ASSET_SOURCE=/tmp/codex-pet-mmd/pet_generated.c \
  build
```

The explicit asset source must be absolute. Do not copy the PMX, textures, or
derived `pet_generated.c` into Git merely to build the firmware.

## Hardware verification still required

The current host prototype passed independent full-set, jump, and directional
walking visual reviews, and its private asset passed conversion and an ESP-IDF
build. Those
results do not prove the physical display result. Before release,
flash a known board, read back the expected image, confirm boot/protocol
readiness, and visually check animation cadence, slide gaze direction,
transparency, clipping, and panel occlusion.
