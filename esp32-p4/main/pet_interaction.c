#include "pet_interaction.h"

#include <limits.h>

static int32_t clamp_progress(int32_t progress)
{
    if (progress < 0) return 0;
    if (progress > PET_PANEL_PROGRESS_MAX) return PET_PANEL_PROGRESS_MAX;
    return progress;
}

bool pet_panel_gesture_can_begin(int32_t progress, int16_t touch_y)
{
    return progress > 0 || touch_y <= PET_TOP_GESTURE_HEIGHT;
}

int32_t pet_panel_progress_from_drag(int32_t start_progress, int32_t delta_y,
                                     int32_t panel_height)
{
    if (panel_height <= 0) return clamp_progress(start_progress);
    int64_t progress = (int64_t)start_progress +
        (int64_t)delta_y * PET_PANEL_PROGRESS_MAX / panel_height;
    if (progress < 0) return 0;
    if (progress > PET_PANEL_PROGRESS_MAX) return PET_PANEL_PROGRESS_MAX;
    return (int32_t)progress;
}

int32_t pet_panel_release_target(int32_t progress, int32_t delta_y)
{
    if (delta_y >= PET_PANEL_RELEASE_DISTANCE) return PET_PANEL_PROGRESS_MAX;
    if (delta_y <= -PET_PANEL_RELEASE_DISTANCE) return 0;
    return progress >= PET_PANEL_SNAP_THRESHOLD ? PET_PANEL_PROGRESS_MAX : 0;
}

pet_gesture_axis_t pet_navigation_axis_lock(int32_t delta_x, int32_t delta_y)
{
    int64_t magnitude_x = delta_x < 0 ? -(int64_t)delta_x : delta_x;
    int64_t magnitude_y = delta_y < 0 ? -(int64_t)delta_y : delta_y;

    if (magnitude_x >= PET_NAVIGATION_AXIS_LOCK_DISTANCE &&
        magnitude_x * 3 >= magnitude_y * 4) {
        return PET_GESTURE_AXIS_HORIZONTAL;
    }
    if (magnitude_y >= PET_NAVIGATION_AXIS_LOCK_DISTANCE &&
        magnitude_y * 3 >= magnitude_x * 4) {
        return PET_GESTURE_AXIS_VERTICAL;
    }
    return PET_GESTURE_AXIS_NONE;
}

pet_surface_t pet_navigation_target(pet_surface_t current, pet_gesture_axis_t axis,
                                    int32_t delta_x, int32_t delta_y,
                                    int16_t touch_y)
{
    switch (current) {
    case PET_SURFACE_HOME:
        if (axis == PET_GESTURE_AXIS_HORIZONTAL && delta_x < 0) {
            return PET_SURFACE_SETTINGS;
        }
        if (axis == PET_GESTURE_AXIS_VERTICAL && delta_y < 0) {
            return PET_SURFACE_USAGE;
        }
        if (axis == PET_GESTURE_AXIS_VERTICAL && delta_y > 0 &&
            touch_y <= PET_TOP_GESTURE_HEIGHT) {
            return PET_SURFACE_TODAY;
        }
        return PET_SURFACE_HOME;
    case PET_SURFACE_TODAY:
        return axis == PET_GESTURE_AXIS_VERTICAL && delta_y < 0
            ? PET_SURFACE_HOME : PET_SURFACE_TODAY;
    case PET_SURFACE_SETTINGS:
        return axis == PET_GESTURE_AXIS_HORIZONTAL && delta_x > 0
            ? PET_SURFACE_HOME : PET_SURFACE_SETTINGS;
    case PET_SURFACE_USAGE:
        return axis == PET_GESTURE_AXIS_VERTICAL && delta_y > 0
            ? PET_SURFACE_HOME : PET_SURFACE_USAGE;
    default:
        return PET_SURFACE_HOME;
    }
}

int32_t pet_navigation_opening_delta(pet_surface_t surface, int32_t delta_x,
                                     int32_t delta_y)
{
    switch (surface) {
    case PET_SURFACE_TODAY: return delta_y;
    case PET_SURFACE_SETTINGS:
        return delta_x == INT32_MIN ? INT32_MAX : -delta_x;
    case PET_SURFACE_USAGE:
        return delta_y == INT32_MIN ? INT32_MAX : -delta_y;
    default: return 0;
    }
}

int32_t pet_navigation_progress_from_drag(pet_surface_t surface, int32_t start_progress,
                                          int32_t delta_x, int32_t delta_y)
{
    int32_t dimension = surface == PET_SURFACE_SETTINGS
        ? PET_NAVIGATION_DISPLAY_WIDTH : PET_NAVIGATION_DISPLAY_HEIGHT;
    int64_t opening_delta = pet_navigation_opening_delta(surface, delta_x, delta_y);
    int64_t progress = start_progress +
        opening_delta * PET_PANEL_PROGRESS_MAX / dimension;
    if (progress < 0) return 0;
    if (progress > PET_PANEL_PROGRESS_MAX) return PET_PANEL_PROGRESS_MAX;
    return (int32_t)progress;
}

int32_t pet_cardinal_gaze_progress_from_drag(int32_t delta, int32_t dimension)
{
    if (delta <= 0 || dimension <= 0) return 0;
    int64_t progress = (int64_t)delta * PET_PANEL_PROGRESS_MAX * 2 / dimension;
    if (progress > PET_PANEL_PROGRESS_MAX) return PET_PANEL_PROGRESS_MAX;
    return (int32_t)progress;
}

int32_t pet_navigation_release_target(int32_t progress, int32_t opening_delta)
{
    if (opening_delta >= PET_PAGE_RELEASE_DISTANCE) return PET_PANEL_PROGRESS_MAX;
    if (opening_delta <= -PET_PAGE_RELEASE_DISTANCE) return 0;
    return progress >= PET_PAGE_SNAP_THRESHOLD ? PET_PANEL_PROGRESS_MAX : 0;
}

int64_t pet_clock_epoch_at(int64_t synced_epoch, int64_t synced_at_us, int64_t now_us)
{
    if (synced_epoch < 0 || synced_at_us < 0 || now_us <= synced_at_us) {
        return synced_epoch;
    }
    int64_t elapsed = (now_us - synced_at_us) / 1000000LL;
    if (synced_epoch > INT64_MAX - elapsed) return INT64_MAX;
    return synced_epoch + elapsed;
}

int64_t pet_epoch_add_seconds(int64_t epoch, int32_t seconds)
{
    if (seconds > 0 && epoch > INT64_MAX - seconds) return INT64_MAX;
    if (seconds < 0 && epoch < INT64_MIN - seconds) return INT64_MIN;
    return epoch + seconds;
}

pet_weather_freshness_t pet_weather_freshness(int64_t now_epoch, int64_t updated_epoch)
{
    if (now_epoch < 0 || updated_epoch < 0 || updated_epoch > now_epoch) {
        return PET_WEATHER_TIME_UNKNOWN;
    }
    int64_t age = now_epoch - updated_epoch;
    if (age >= PET_WEATHER_STALE_SECONDS) return PET_WEATHER_STALE;
    if (age >= PET_WEATHER_WARN_SECONDS) return PET_WEATHER_AGING;
    return PET_WEATHER_FRESH;
}

pet_usage_freshness_t pet_usage_freshness(int64_t now_epoch, int64_t updated_epoch)
{
    if (now_epoch < 0 || updated_epoch < 0 || updated_epoch > now_epoch) {
        return PET_USAGE_TIME_UNKNOWN;
    }
    int64_t age = now_epoch - updated_epoch;
    if (age >= PET_USAGE_STALE_SECONDS) return PET_USAGE_STALE;
    if (age >= PET_USAGE_WARN_SECONDS) return PET_USAGE_AGING;
    return PET_USAGE_FRESH;
}

bool pet_action_can_interrupt(uint8_t current_priority, bool current_interruptible,
                              uint8_t incoming_priority)
{
    if (incoming_priority > current_priority) return true;
    return current_interruptible && incoming_priority >= current_priority;
}

bool pet_action_should_replace_pending(bool has_pending, uint8_t pending_priority,
                                       uint8_t incoming_priority)
{
    return !has_pending || incoming_priority >= pending_priority;
}
