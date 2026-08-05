#pragma once

#include <stdint.h>

#include "lvgl.h"

#define CODEX_PET_GENERATED_ABI 2

#define PET_FRAME_W 152
#define PET_FRAME_H 204
#define PET_FRAME_SCALE 768

#define PET_JPEG_PADDED_W 160
#define PET_JPEG_PADDED_H 208
#define PET_FRAME_COLOUR_BYTES (PET_FRAME_W * PET_FRAME_H * 2U)
#define PET_FRAME_ALPHA_BYTES (PET_FRAME_W * PET_FRAME_H)
#define PET_FRAME_RGB565A8_BYTES (PET_FRAME_COLOUR_BYTES + PET_FRAME_ALPHA_BYTES)
#define PET_JPEG_DECODE_BYTES (PET_JPEG_PADDED_W * PET_JPEG_PADDED_H * 2U)

typedef enum {
    PET_FRAME_STORAGE_RAW_RGB565A8,
    PET_FRAME_STORAGE_JPEG_ALPHA_RLE,
} pet_frame_storage_t;

typedef struct {
    const lv_image_dsc_t *raw;
    const uint8_t *jpeg_data;
    uint32_t jpeg_size;
    const uint8_t *alpha_rle_data;
    uint32_t alpha_rle_size;
} pet_frame_asset_t;

typedef enum {
    PET_MOTION_IDLE,
    PET_MOTION_RUNNING_RIGHT,
    PET_MOTION_RUNNING_LEFT,
    PET_MOTION_WAVING,
    PET_MOTION_JUMPING,
    PET_MOTION_FAILED,
    PET_MOTION_WAITING,
    PET_MOTION_RUNNING,
    PET_MOTION_REVIEW,
    PET_MOTION_LOOK,
    PET_MOTION_COUNT,
} pet_motion_id_t;

typedef enum {
    PET_TIMING_IDLE,
    PET_TIMING_BLINK,
    PET_TIMING_RUN,
    PET_TIMING_WAVE,
    PET_TIMING_JUMP,
    PET_TIMING_FAILED,
    PET_TIMING_WAITING,
    PET_TIMING_RUNNING,
    PET_TIMING_REVIEW,
    PET_TIMING_LOOK,
    PET_TIMING_EXCITED,
    PET_TIMING_SLEEPY,
    PET_TIMING_HOLD,
    PET_TIMING_COUNT,
} pet_timing_id_t;

typedef struct {
    uint16_t first_frame;
    uint16_t frame_count;
} pet_motion_range_t;

typedef struct {
    const uint16_t *durations_ms;
    uint16_t count;
} pet_timing_track_t;

typedef struct {
    uint16_t frame_count;
    uint16_t idle_loop_count;
    pet_frame_storage_t storage;
    const pet_frame_asset_t *frames;
    const pet_motion_range_t *motions;
    const pet_timing_track_t *timings;
} pet_asset_bundle_t;

extern const pet_asset_bundle_t PET_ASSET_BUNDLE;
