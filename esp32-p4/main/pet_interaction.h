#pragma once

#include <stdbool.h>
#include <stdint.h>

#define PET_PANEL_PROGRESS_MAX 1000
#define PET_PANEL_SNAP_THRESHOLD 430
#define PET_PANEL_RELEASE_DISTANCE 55
#define PET_TOP_GESTURE_HEIGHT 82
#define PET_WEATHER_WARN_SECONDS (45 * 60)
#define PET_WEATHER_STALE_SECONDS (3 * 60 * 60)
#define PET_NAVIGATION_DISPLAY_WIDTH 480
#define PET_NAVIGATION_DISPLAY_HEIGHT 800
#define PET_NAVIGATION_AXIS_LOCK_DISTANCE 14
#define PET_PAGE_SNAP_THRESHOLD 350
#define PET_PAGE_RELEASE_DISTANCE 72
#define PET_USAGE_WARN_SECONDS (5 * 60)
#define PET_USAGE_STALE_SECONDS (30 * 60)

typedef enum {
    PET_SURFACE_HOME,
    PET_SURFACE_TODAY,
    PET_SURFACE_SETTINGS,
    PET_SURFACE_USAGE,
} pet_surface_t;

typedef enum {
    PET_GESTURE_AXIS_NONE,
    PET_GESTURE_AXIS_HORIZONTAL,
    PET_GESTURE_AXIS_VERTICAL,
} pet_gesture_axis_t;

typedef enum {
    PET_WEATHER_FRESH,
    PET_WEATHER_AGING,
    PET_WEATHER_STALE,
    PET_WEATHER_TIME_UNKNOWN,
} pet_weather_freshness_t;

typedef enum {
    PET_USAGE_FRESH,
    PET_USAGE_AGING,
    PET_USAGE_STALE,
    PET_USAGE_TIME_UNKNOWN,
} pet_usage_freshness_t;

bool pet_panel_gesture_can_begin(int32_t progress, int16_t touch_y);
int32_t pet_panel_progress_from_drag(int32_t start_progress, int32_t delta_y,
                                     int32_t panel_height);
int32_t pet_panel_release_target(int32_t progress, int32_t delta_y);
pet_gesture_axis_t pet_navigation_axis_lock(int32_t delta_x, int32_t delta_y);
pet_surface_t pet_navigation_target(pet_surface_t current, pet_gesture_axis_t axis,
                                    int32_t delta_x, int32_t delta_y,
                                    int16_t touch_y);
int32_t pet_navigation_opening_delta(pet_surface_t surface, int32_t delta_x,
                                     int32_t delta_y);
int32_t pet_navigation_progress_from_drag(pet_surface_t surface, int32_t start_progress,
                                          int32_t delta_x, int32_t delta_y);
int32_t pet_cardinal_gaze_progress_from_drag(int32_t delta, int32_t dimension);
int32_t pet_navigation_release_target(int32_t progress, int32_t opening_delta);
int64_t pet_clock_epoch_at(int64_t synced_epoch, int64_t synced_at_us, int64_t now_us);
int64_t pet_epoch_add_seconds(int64_t epoch, int32_t seconds);
pet_weather_freshness_t pet_weather_freshness(int64_t now_epoch, int64_t updated_epoch);
pet_usage_freshness_t pet_usage_freshness(int64_t now_epoch, int64_t updated_epoch);
bool pet_action_can_interrupt(uint8_t current_priority, bool current_interruptible,
                              uint8_t incoming_priority);
bool pet_action_should_replace_pending(bool has_pending, uint8_t pending_priority,
                                       uint8_t incoming_priority);
