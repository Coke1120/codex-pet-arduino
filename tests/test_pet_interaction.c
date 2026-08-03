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
    assert(pet_panel_release_target(429, 0) == 0);
    assert(pet_panel_release_target(430, 0) == 1000);
    assert(pet_panel_release_target(100, 55) == 1000);
    assert(pet_panel_release_target(900, -55) == 0);

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
