# Private Video Pet Pipeline

Use this workflow only when you own the source video or have explicit permission
to create and use the derived pet frames. Keep the source, editing project,
mattes, previews, extracted PNGs, manifest, and generated C translation unit in
a private workspace. Never commit private media or `pet_generated.c`.

## Why the runtime uses frames

The authoring source may be a high-resolution H.264 MP4 with no alpha channel.
Direct MP4/H.264 playback is deliberately not the runtime path: the current P4
UI needs transparent, random-access status clips, and this project has not
selected a native H.264 decode path. Video is therefore edited and matted
offline, then converted into independently addressable frames.

## Prepare the private frame set

1. Cut short, readable loops or segments for each action. Remove duplicate
   holds and unused footage before extraction. Use ping-pong only for suitable
   low-energy loops; reversing locomotion, impacts, gestures, or asymmetric
   motion usually looks wrong.
2. Matte the subject against transparency in the private editing workspace.
   Export every frame as an exact `152x204` RGBA PNG with stable registration
   and enough transparent edge clearance to avoid clipping.
3. Represent 24 fps with `42` ms per frame in `firmware_durations_ms`.
4. Write `motion_manifest.json` beside the PNGs. Each PNG filename is the
   lowercase manifest frame name plus `.png`.

A custom manifest uses `"version": 2`, `"profile": "custom"`, width `152`,
height `204`, an `idle_loop_count`, an ordered unique `frames` array, contiguous
`actions`, and `firmware_durations_ms`. The action order is fixed:

| Action | Purpose |
| --- | --- |
| `IDLE` | `idle` lifecycle loop and blink source |
| `RUNNING_RIGHT`, `RUNNING_LEFT` | Directional reactions |
| `WAVING`, `JUMPING`, `FAILED` | Touch, success, and failure reactions |
| `WAITING`, `RUNNING`, `REVIEW` | `waiting`, `running`, and `review` lifecycle loops |
| `LOOK` | Four equal quarters in up, right, down, left order |

Unlike the default/legacy smooth raw profile, which uses 152 playback entries,
a version 2 manifest supplies dynamic playback counts. A larger compressed set
is therefore valid without resampling to 152 entries; the current private
candidate uses 720 playback frames. This is a capacity example, not a new fixed
layout or target count.

Every action must contain at least one frame, `LOOK` must be divisible by four,
and both the complete frame list and each action count are limited to
`1`-`65535` entries. Version 2 also requires explicit timing tracks for `IDLE`,
`BLINK`, `RUN`, `WAVE`, `JUMP`, `FAILED`, `WAITING`, `RUNNING`, `REVIEW`,
`LOOK`, `EXCITED`, `SLEEPY`, and `HOLD`. Timing counts must match the action
they drive. `IDLE` uses `idle_loop_count`; `BLINK` uses the full `IDLE` count;
`RUN` uses one directional-run count; `LOOK` uses one quarter of the `LOOK`
count; `SLEEPY` uses at most the final five `FAILED` frames; and `HOLD` has one
entry. Each duration is also a `uint16_t` millisecond value.

## Convert and build

Run the converter from the repository root:

```sh
python3 tools/convert_codex_pet_p4.py \
  --frames-dir /tmp/codex-pet-video/frames \
  --encoding jpeg-alpha-rle \
  --jpeg-qscale 2 \
  --alpha-bits 8 \
  --output /tmp/codex-pet-video/pet_generated.c
```

The converter stores each color frame as a black-padded `160x208` JPEG and the
exact 8-bit alpha plane as RLE. On the P4, the hardware JPEG decoder produces
padded RGB565; firmware crops it back to `152x204`, appends the decoded alpha
plane, and alternates between two PSRAM RGB565A8 buffers for LVGL.

From an ESP-IDF 5.5.x shell, use an isolated effective configuration and build
directory. Pass the generated file as an absolute external asset source:

```sh
idf.py -C esp32-p4 -B /tmp/codex-pet-video/build \
  -D SDKCONFIG=/tmp/codex-pet-video/sdkconfig \
  -D SDKCONFIG_DEFAULTS="$PWD/esp32-p4/sdkconfig.defaults" \
  -D CODEX_PET_ASSET_SOURCE=/tmp/codex-pet-video/pet_generated.c \
  set-target esp32p4
idf.py -C esp32-p4 -B /tmp/codex-pet-video/build \
  -D SDKCONFIG=/tmp/codex-pet-video/sdkconfig \
  -D SDKCONFIG_DEFAULTS="$PWD/esp32-p4/sdkconfig.defaults" \
  -D CODEX_PET_ASSET_SOURCE=/tmp/codex-pet-video/pet_generated.c \
  build
idf.py -C esp32-p4 -B /tmp/codex-pet-video/build size
wc -c /tmp/codex-pet-video/build/codex_pet_jc4880p443c.bin
```

Record the actual linked application binary size. The factory application
partition is `0xF70000` bytes; the candidate must be no larger than `0xEF0000`
(15,663,104 bytes) so its final 512 KiB remains reserved. Frame count or
converter payload size alone does not prove this margin.

## Evidence required

Keep four distinct evidence layers for every candidate:

1. **Matte and preview:** review the complete animation at target size and
   timing; check registration, transparent margins, action boundaries, and the
   four `LOOK` quarters.
2. **Codec roundtrip:** decode representative and edge-case JPEG/alpha payloads
   back to RGB565A8; confirm exact alpha recovery, padding crop, frame order,
   and acceptable color loss. Converter unit tests support this evidence but do
   not replace a candidate-specific preview.
3. **Build:** retain converter output, ESP-IDF build/size output, map file, and
   the measured linked binary size proving the 512 KiB reserve.
4. **Hardware:** on the intended board, verify RGB565 byte order and colors,
   the exact crop, animation cadence, touch-driven slide gaze in all four
   directions, and clean alpha edges over the real UI. Build success is not
   physical display evidence.
