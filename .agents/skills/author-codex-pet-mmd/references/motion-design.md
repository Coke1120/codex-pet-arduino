# Motion Design Contract

## Design for status readability

Author motion for the physical `152x204` source frame and its target display scale. Judge rendered pixels, not rig values.

Use these semantic anchors:

| State | Readable intent | Primary visual cues |
| --- | --- | --- |
| `idle` | Available, relaxed, attentive | Asymmetric contrapposto, small weight drift, gentle head or eye drift |
| `running` | Actively working | Forward intent, grounded alternating step, focused face, clearer body rhythm |
| `waiting` | Blocked on input without panic | Lazy toe play, delayed searching gaze, cool or coyly impatient face |
| `review` | Inspecting or evaluating | Deliberate lean, raised hand or thinking gesture, scanning gaze, serious face |
| internal `failed` | Recoverable error presentation | Readable misstep, brief surprise, deliberate cool recovery |

Keep `failed` internal. Avoid mapping it into the host lifecycle vocabulary.

## Preserve an appealing neutral stance

Build a visually readable, model-like asymmetry:

- Shift the pelvis over one support leg.
- Relax the other knee.
- Stagger the feet in depth and rotate the toes unequally.
- Counter-rotate hips, shoulders, and head slightly.
- Keep balance plausible and the full silhouette inside transparent padding.

Reject parallel feet, locked knees, mirrored limbs, punishment-like kneeling, forced squats, or a collapsed posture. A failed clip may show a mistake, but it must recover into composure rather than slump, distress, or sentimentality.

Depth offsets are not enough when the camera flattens them. Use a mild perspective view or visible screen-space foot separation, then judge the rendered silhouette at target size.

## Use body direction to reveal the performance

Do not stage every action front-on. Assign an intentional view to each status:

- keep neutral LOOK frame zero near-front so the four slide-driven gaze clips share a stable body;
- use opposing three-quarter views for screen-left and screen-right movement;
- use a stronger three-quarter or side view for running and jumping so knee flexion, toe-off, foot depth, and airborne phases remain visible;
- give waiting, review, and failure different body yaws when that improves their silhouette, while keeping the face and status cue readable.

Directional walking and running should carry a visible but restrained forward
torso lean. Counter-tilt the head enough to keep the gaze attentive. Reject an
upright march, backward lean, bow, collapse, or punishment-like downward pose.
Verify the imported rig's local pitch sign with a small positive/negative render
before authoring: this Chloe-compatible rig bends forward on positive local X.
Distribute the lean across `下半身`, `上半身`, and `上半身2`, and move `センター`
slightly along model-forward. Rotating only `上半身2` creates a high chest hinge
while the pelvis appears to fall backward.
When three-quarter projection still flattens a correct rig-space run, prefer a
near-side body yaw around `55–65°` and add a distinct airborne apex key per
half-cycle. Do not compensate by raising the swing foot during grounded phases;
that reads as marching.

Evaluate the final screen projection, not only the rig coordinates. A body yaw can project two correctly separated IK targets back across the body centerline. Reject any rotated running frame whose boots overlap or swap anatomical sides.

Before committing choreography, render a private low-resolution facing audit from four fixed positions around the model: front (`-Y`), screen-right side (`+X`), back (`+Y`), and screen-left side (`-X`). Use one target at the evaluated model bounds center and the same lens/distance for all four images. Select status yaws from those rendered silhouettes rather than assuming the PMX front or best side from bone coordinates.

For the final sprite contract, keep one camera and lighting rig fixed; rotate the character/body per status instead of orbiting the camera per frame. This preserves stable scale, alpha padding, ground reference, and gaze comparisons. The four-angle audit adapts the useful front-detection step from the external [turntable Blender skill](https://github.com/kevinbadi/blender-skills/blob/main/turntable/SKILL.md); its desktop output paths, Blender MCP prerequisite, 360-degree production orbit, Cycles/GPU settings, and product lighting are not part of this private ESP32 workflow.

## Drive the center and foot IK separately

Whole-armature translation moves the torso and foot IK parents together, so it creates a screen-space bob but not actual knee compression. On a standard compatible MMD hierarchy, verify that the body center is below `センター`/`グルーブ` while foot IK parents remain below `全ての親`, then:

- move the center bone relative to planted foot IK targets for load, crouch, and landing absorption;
- move each foot IK through explicit contact, toe-off, swing, and landing arcs;
- keep the support foot stable while loaded and put both feet visibly off the floor during a running flight phase;
- return non-looping actions to a compatible neutral center and foot placement before their final hold.

If the imported hierarchy differs, inspect it before authoring. Never assume numeric knee rotations are visible when an active IK constraint overrides them.

## Keep cadence slow and lazy

- Favor eased arcs and weight transfer over sharp pose swaps.
- Hold readable extremes long enough to survive the display cadence.
- Move only the controls needed to express the state.
- Keep root travel small so the character feels grounded rather than jittery.
- Use a sparse, soft blink as punctuation. Do not bake a full blink into every short idle loop or blink across all states at the same phase.
- In the default 152-frame profile, loop `IDLE_0` through `IDLE_9`; reserve `IDLE_10` and `IDLE_11` to complete the explicit blink reaction so normal idle does not blink every cycle.
- In that default profile, treat the 24-frame high-motion `RUNNING` clip as a compact light-run cycle at 30 ms per frame. The 8-frame directional run clips use 90 ms per frame; they must still show bent elbows, toe-off, swing, and a readable flight drawing rather than a sped-up walk.
- In that default profile, treat `JUMPING` as 29 motion frames at 33 ms followed by a readable landing hold. Allocate multiple frames to anticipation, exact full extension, ascent, tuck/apex, descent, contact, held absorption, and staged recovery instead of compressing them into a half-second pose sampler.
- In a dynamic manifest-v2 profile, keep every authored frame and choose 24 or 30 fps timing when useful. Increase frame count to improve arcs and joint mechanics, but retain readable holds and verify the complete linked firmware budget.
- Check the firmware durations as well as the frames; image count alone does not define perceived speed.

The default smooth and legacy compatibility layout contains 152 entries: `IDLE` 12,
`RUNNING_RIGHT` 8, `RUNNING_LEFT` 8, `WAVING` 8, `JUMPING` 30, `FAILED` 18,
`WAITING` 14, `RUNNING` 24, `REVIEW` 14, and `LOOK` 16. A version-2 manifest
may instead define a dynamic 1-65535-frame playback map. Dynamic frames play
directly; only the legacy compatibility path is pointer-resampled to 152.

## Differentiate semantics

Change at least two high-salience channels between lifecycle states: silhouette or center of mass, gesture, head direction, eye direction, or expression. Ensure adjacent status key poses remain distinguishable when reduced to a contact sheet or viewed briefly.

Do not count tiny bone-angle changes as semantic differentiation. Reject a change when the rendered result is visually identical at target scale.

## Author cardinal gaze slides

Split `LOOK` into four equal ordered clips. The default profile uses 16 legacy
filenames as four four-frame clips; dynamic profiles may use more frames per
direction:

1. Slide up.
2. Slide toward screen-right.
3. Slide down.
4. Slide toward screen-left.

Ease each clip from neutral to the cardinal target. Make its first frame pixel-equivalent to `IDLE_0`, keep the feet and lower body stable, let pupils lead, and let the head follow subtly. Keep screen direction unambiguous; do not confuse model-left with screen-left. Avoid snaps, circular orbiting, or sixteen unrelated angular poses.

## Review the pixels independently

Export contact sheets and short loops at target scale. Ask a reviewer who has not seen the pose values to label the state and motion direction. Reject:

- indistinguishable adjacent frames despite different numeric controls;
- status loops that share the same silhouette and expression;
- flicker, foot sliding, camera drift, clipping, alpha halos, or mask remnants;
- gaze changes visible only at high zoom;
- motion that reads as frantic, punitive, or distressed outside internal failure.
- a numerically different rig pose that produces no meaningful pixel-level change.
- an all-front presentation that hides depth, joint flexion, or directional intent.

Revise the authored poses until the reviewer can identify the intended semantics from the images alone.
