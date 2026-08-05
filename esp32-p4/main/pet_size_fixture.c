#include "pet_generated.h"

#define PET_SIZE_FIXTURE_FRAME_COUNT 152
#define PET_SIZE_FIXTURE_FRAME_BYTES (PET_FRAME_W * PET_FRAME_H * 3)
#define PET_SIZE_FIXTURE_TOTAL_BYTES \
    (PET_SIZE_FIXTURE_FRAME_BYTES * PET_SIZE_FIXTURE_FRAME_COUNT)

/* Rights-safe CI payload: one retained object with the exact byte footprint of
 * the default/compatibility 152-frame raw RGB565A8 profile. Dynamic manifest
 * assets may use other frame counts; repeated visual data keeps this fixture's
 * content irrelevant. */
static const LV_ATTRIBUTE_MEM_ALIGN uint8_t
    pet_size_fixture_payload[PET_SIZE_FIXTURE_TOTAL_BYTES]
    __attribute__((used)) = {
        [0 ... (PET_SIZE_FIXTURE_TOTAL_BYTES - 1)] = 0xA5,
    };

_Static_assert(PET_SIZE_FIXTURE_TOTAL_BYTES == 14139648,
               "size fixture must match the 152-frame RGB565A8 payload");

static const lv_image_dsc_t pet_size_fixture_images[PET_SIZE_FIXTURE_FRAME_COUNT]
    __attribute__((used)) = {
        [0 ... (PET_SIZE_FIXTURE_FRAME_COUNT - 1)] = {
            .header.magic = LV_IMAGE_HEADER_MAGIC,
            .header.cf = LV_COLOR_FORMAT_RGB565A8,
            .header.flags = 0,
            .header.w = PET_FRAME_W,
            .header.h = PET_FRAME_H,
            .header.stride = PET_FRAME_W * 2,
            .data_size = PET_SIZE_FIXTURE_FRAME_BYTES,
            .data = pet_size_fixture_payload,
        },
};

static const pet_frame_asset_t pet_size_fixture_frames[PET_SIZE_FIXTURE_FRAME_COUNT] = {
    [0 ... (PET_SIZE_FIXTURE_FRAME_COUNT - 1)] = {.raw = &pet_size_fixture_images[0]},
};

static const pet_motion_range_t pet_size_fixture_motions[PET_MOTION_COUNT] = {
    [PET_MOTION_IDLE] = {0, 12},
    [PET_MOTION_RUNNING_RIGHT] = {12, 8},
    [PET_MOTION_RUNNING_LEFT] = {20, 8},
    [PET_MOTION_WAVING] = {28, 8},
    [PET_MOTION_JUMPING] = {36, 30},
    [PET_MOTION_FAILED] = {66, 18},
    [PET_MOTION_WAITING] = {84, 14},
    [PET_MOTION_RUNNING] = {98, 24},
    [PET_MOTION_REVIEW] = {122, 14},
    [PET_MOTION_LOOK] = {136, 16},
};

static const uint16_t idle_durations[] = {[0 ... 9] = 120};
static const uint16_t blink_durations[] = {[0 ... 9] = 45, [10] = 70, [11] = 90};
static const uint16_t run_durations[] = {[0 ... 7] = 90};
static const uint16_t wave_durations[] = {180, 180, 180, 180, 180, 260, 220, 300};
static const uint16_t jump_durations[] = {[0 ... 28] = 33, [29] = 180};
static const uint16_t failed_durations[] = {[0 ... 16] = 50, [17] = 300};
static const uint16_t waiting_durations[] = {[0 ... 12] = 65, [13] = 180};
static const uint16_t running_durations[] = {[0 ... 23] = 30};
static const uint16_t review_durations[] = {[0 ... 12] = 65, [13] = 180};
static const uint16_t look_durations[] = {65, 65, 85, 650};
static const uint16_t excited_durations[] = {[0 ... 28] = 33, [29] = 150};
static const uint16_t sleepy_durations[] = {240, 260, 300, 420, 700};
static const uint16_t hold_durations[] = {850};

#define TIMING(values) {.durations_ms = (values), .count = sizeof(values) / sizeof((values)[0])}
static const pet_timing_track_t pet_size_fixture_timings[PET_TIMING_COUNT] = {
    [PET_TIMING_IDLE] = TIMING(idle_durations),
    [PET_TIMING_BLINK] = TIMING(blink_durations),
    [PET_TIMING_RUN] = TIMING(run_durations),
    [PET_TIMING_WAVE] = TIMING(wave_durations),
    [PET_TIMING_JUMP] = TIMING(jump_durations),
    [PET_TIMING_FAILED] = TIMING(failed_durations),
    [PET_TIMING_WAITING] = TIMING(waiting_durations),
    [PET_TIMING_RUNNING] = TIMING(running_durations),
    [PET_TIMING_REVIEW] = TIMING(review_durations),
    [PET_TIMING_LOOK] = TIMING(look_durations),
    [PET_TIMING_EXCITED] = TIMING(excited_durations),
    [PET_TIMING_SLEEPY] = TIMING(sleepy_durations),
    [PET_TIMING_HOLD] = TIMING(hold_durations),
};

const pet_asset_bundle_t PET_ASSET_BUNDLE = {
    .frame_count = PET_SIZE_FIXTURE_FRAME_COUNT,
    .idle_loop_count = 10,
    .storage = PET_FRAME_STORAGE_RAW_RGB565A8,
    .frames = pet_size_fixture_frames,
    .motions = pet_size_fixture_motions,
    .timings = pet_size_fixture_timings,
};
