#include <assert.h>
#include <stdio.h>

#include "pet_interaction.h"

int main(void)
{
    assert(pet_panel_gesture_can_begin(0, 82));
    assert(!pet_panel_gesture_can_begin(0, 83));
    assert(pet_panel_gesture_can_begin(1, 799));
    assert(pet_panel_progress_from_drag(0, -100, 510) == 0);
    assert(pet_panel_progress_from_drag(1000, 100, 510) == 1000);
    assert(pet_panel_progress_from_drag(0, 255, 510) == 500);
    assert(pet_panel_progress_from_drag(INT32_MAX, INT32_MAX, 1) == 1000);
    assert(pet_panel_progress_from_drag(INT32_MIN, INT32_MIN, 1) == 0);
    assert(pet_panel_release_target(429, 0) == 0);
    assert(pet_panel_release_target(430, 0) == 1000);
    assert(pet_panel_release_target(100, 55) == 1000);
    assert(pet_panel_release_target(900, -55) == 0);

    assert(pet_navigation_axis_lock(13, 0) == PET_GESTURE_AXIS_NONE);
    assert(pet_navigation_axis_lock(14, 10) == PET_GESTURE_AXIS_HORIZONTAL);
    assert(pet_navigation_axis_lock(10, 14) == PET_GESTURE_AXIS_VERTICAL);
    assert(pet_navigation_axis_lock(14, 11) == PET_GESTURE_AXIS_NONE);
    assert(pet_navigation_axis_lock(INT32_MIN, 0) == PET_GESTURE_AXIS_HORIZONTAL);
    assert(pet_navigation_axis_lock(0, INT32_MIN) == PET_GESTURE_AXIS_VERTICAL);

    assert(pet_navigation_target(PET_SURFACE_HOME, PET_GESTURE_AXIS_VERTICAL,
                                 0, 20, 82) == PET_SURFACE_TODAY);
    assert(pet_navigation_target(PET_SURFACE_HOME, PET_GESTURE_AXIS_VERTICAL,
                                 0, 20, 83) == PET_SURFACE_HOME);
    assert(pet_navigation_target(PET_SURFACE_HOME, PET_GESTURE_AXIS_HORIZONTAL,
                                 -20, 0, 400) == PET_SURFACE_SETTINGS);
    assert(pet_navigation_target(PET_SURFACE_HOME, PET_GESTURE_AXIS_VERTICAL,
                                 0, -20, 400) == PET_SURFACE_USAGE);
    assert(pet_navigation_target(PET_SURFACE_TODAY, PET_GESTURE_AXIS_HORIZONTAL,
                                 -20, 0, 0) == PET_SURFACE_TODAY);
    assert(pet_navigation_target(PET_SURFACE_TODAY, PET_GESTURE_AXIS_VERTICAL,
                                 0, -20, 0) == PET_SURFACE_HOME);
    assert(pet_navigation_target(PET_SURFACE_SETTINGS, PET_GESTURE_AXIS_HORIZONTAL,
                                 20, 0, 0) == PET_SURFACE_HOME);
    assert(pet_navigation_target(PET_SURFACE_USAGE, PET_GESTURE_AXIS_VERTICAL,
                                 0, 20, 0) == PET_SURFACE_HOME);

    assert(pet_navigation_opening_delta(PET_SURFACE_TODAY, 0, 100) == 100);
    assert(pet_navigation_opening_delta(PET_SURFACE_SETTINGS, -100, 0) == 100);
    assert(pet_navigation_opening_delta(PET_SURFACE_USAGE, 0, -100) == 100);
    assert(pet_navigation_progress_from_drag(PET_SURFACE_SETTINGS, 0, -240, 0) == 500);
    assert(pet_navigation_progress_from_drag(PET_SURFACE_USAGE, 0, 0, -400) == 500);
    assert(pet_navigation_progress_from_drag(PET_SURFACE_TODAY, 0, 0, 800) == 1000);
    assert(pet_navigation_progress_from_drag(PET_SURFACE_USAGE, 1000, 0, 800) == 0);
    assert(pet_navigation_release_target(349, 0) == 0);
    assert(pet_navigation_release_target(350, 0) == 1000);
    assert(pet_navigation_release_target(1, 72) == 1000);
    assert(pet_navigation_release_target(999, -72) == 0);

    assert(pet_clock_epoch_at(100, 1000000, 999999) == 100);
    assert(pet_clock_epoch_at(100, 1000000, 3999999) == 102);
    assert(pet_clock_epoch_at(INT64_MAX, 0, 2000000) == INT64_MAX);
    assert(pet_epoch_add_seconds(INT64_MAX, 1) == INT64_MAX);
    assert(pet_epoch_add_seconds(INT64_MIN, -1) == INT64_MIN);
    assert(pet_epoch_add_seconds(100, -20) == 80);
    assert(pet_weather_freshness(-1, 0) == PET_WEATHER_TIME_UNKNOWN);
    assert(pet_weather_freshness(99, 100) == PET_WEATHER_TIME_UNKNOWN);
    assert(pet_weather_freshness(100, -1) == PET_WEATHER_TIME_UNKNOWN);
    assert(pet_weather_freshness(2699, 0) == PET_WEATHER_FRESH);
    assert(pet_weather_freshness(2700, 0) == PET_WEATHER_AGING);
    assert(pet_weather_freshness(10799, 0) == PET_WEATHER_AGING);
    assert(pet_weather_freshness(10800, 0) == PET_WEATHER_STALE);
    assert(pet_usage_freshness(-1, 0) == PET_USAGE_TIME_UNKNOWN);
    assert(pet_usage_freshness(99, 100) == PET_USAGE_TIME_UNKNOWN);
    assert(pet_usage_freshness(100, -1) == PET_USAGE_TIME_UNKNOWN);
    assert(pet_usage_freshness(299, 0) == PET_USAGE_FRESH);
    assert(pet_usage_freshness(300, 0) == PET_USAGE_AGING);
    assert(pet_usage_freshness(1799, 0) == PET_USAGE_AGING);
    assert(pet_usage_freshness(1800, 0) == PET_USAGE_STALE);

    assert(!pet_action_can_interrupt(60, true, 40));
    assert(pet_action_can_interrupt(60, true, 60));
    assert(pet_action_can_interrupt(60, false, 80));
    assert(!pet_action_can_interrupt(80, false, 80));
    assert(pet_action_should_replace_pending(false, 0, 40));
    assert(!pet_action_should_replace_pending(true, 80, 40));
    assert(pet_action_should_replace_pending(true, 40, 40));

    puts("pet_interaction tests passed");
    return 0;
}
