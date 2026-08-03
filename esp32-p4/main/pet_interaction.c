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
    return clamp_progress(start_progress + delta_y * PET_PANEL_PROGRESS_MAX / panel_height);
}

int32_t pet_panel_release_target(int32_t progress, int32_t delta_y)
{
    if (delta_y >= PET_PANEL_RELEASE_DISTANCE) return PET_PANEL_PROGRESS_MAX;
    if (delta_y <= -PET_PANEL_RELEASE_DISTANCE) return 0;
    return progress >= PET_PANEL_SNAP_THRESHOLD ? PET_PANEL_PROGRESS_MAX : 0;
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
