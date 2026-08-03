/*
 * Codex Pet for GUITION JC4880P443C-I-W (ESP32-P4 + ESP32-C6).
 *
 * The ESP32-P4 drives the 480x800 display and GT911 touch controller. Private
 * selected-pet art is generated locally as pet_generated.c and stays gitignored.
 */

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "bsp/esp-bsp.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lvgl.h"
#include "pet_generated.h"
#include "pet_interaction.h"
#include "pet_protocol.h"

#define DISPLAY_WIDTH 480
#define DISPLAY_HEIGHT 800
#define TODAY_PANEL_HEIGHT 510
#define PANEL_DRAG_THRESHOLD 10
#define PET_NORMAL_TOP 64
#define PET_PANEL_TOP 520
#define TAP_COOLDOWN_US (2500LL * 1000LL)
#define ACTION_CONTEXT (-1)

static const char *TAG = "codex_pet";

typedef enum {
    ACTION_IDLE,
    ACTION_BLINK,
    ACTION_LOOK_UP,
    ACTION_LOOK_LEFT,
    ACTION_LOOK_RIGHT,
    ACTION_WAVE,
    ACTION_PRESENT,
    ACTION_THINK,
    ACTION_HAPPY,
    ACTION_EXCITED,
    ACTION_SLEEPY,
    ACTION_SIT,
    ACTION_RUN_LEFT,
    ACTION_RUN_RIGHT,
    ACTION_TURN_AROUND,
    ACTION_WAITING_LONG,
    ACTION_REVIEW_POSITIVE,
    ACTION_REVIEW_CONCERNED,
    ACTION_NOTIFICATION,
    ACTION_WEATHER_REACTION,
    ACTION_WEATHER_CONCERNED,
    ACTION_RUNNING,
    ACTION_WAITING,
    ACTION_REVIEW,
    ACTION_FAILED,
    ACTION_COUNT,
} pet_action_id_t;

enum {
    PRIORITY_IDLE = 20,
    PRIORITY_WEATHER = 40,
    PRIORITY_LIFECYCLE = 60,
    PRIORITY_TOUCH = 80,
    PRIORITY_CRITICAL = 100,
};

typedef struct {
    const char *name;
    uint8_t first_frame;
    uint8_t frame_count;
    const uint16_t *durations;
    uint8_t priority;
    int8_t next_action;
    bool loop;
    bool interruptible;
} pet_action_manifest_t;

#define PET_IDLE_FRAME_MS 650U
#define PET_RUNNING_FRAME_MS 280U
#define PET_WAITING_FRAME_MS 520U
#define PET_REVIEW_FRAME_MS 420U

/*
 * V2 has three times as many lifecycle frames as v1. Preserve the familiar
 * per-frame cadence instead of compressing every row into the old loop time,
 * which made the character appear to run at two to three times normal speed.
 */
static const uint16_t idle_durations[] = {
    PET_IDLE_FRAME_MS, PET_IDLE_FRAME_MS, PET_IDLE_FRAME_MS,
    PET_IDLE_FRAME_MS, PET_IDLE_FRAME_MS, PET_IDLE_FRAME_MS,
};
static const uint16_t blink_durations[] = {280, 110, 110, 140, 140, 320};
static const uint16_t run_durations[] = {
    PET_RUNNING_FRAME_MS, PET_RUNNING_FRAME_MS, PET_RUNNING_FRAME_MS,
    PET_RUNNING_FRAME_MS, PET_RUNNING_FRAME_MS, PET_RUNNING_FRAME_MS,
    PET_RUNNING_FRAME_MS, PET_RUNNING_FRAME_MS,
};
static const uint16_t wave_durations[] = {140, 140, 140, 280};
static const uint16_t jump_durations[] = {140, 140, 140, 140, 280};
static const uint16_t failed_durations[] = {140, 140, 140, 140, 140, 140, 140, 240};
static const uint16_t waiting_durations[] = {
    PET_WAITING_FRAME_MS, PET_WAITING_FRAME_MS, PET_WAITING_FRAME_MS,
    PET_WAITING_FRAME_MS, PET_WAITING_FRAME_MS, PET_WAITING_FRAME_MS,
};
static const uint16_t running_durations[] = {
    PET_RUNNING_FRAME_MS, PET_RUNNING_FRAME_MS, PET_RUNNING_FRAME_MS,
    PET_RUNNING_FRAME_MS, PET_RUNNING_FRAME_MS, PET_RUNNING_FRAME_MS,
};
static const uint16_t review_durations[] = {
    PET_REVIEW_FRAME_MS, PET_REVIEW_FRAME_MS, PET_REVIEW_FRAME_MS,
    PET_REVIEW_FRAME_MS, PET_REVIEW_FRAME_MS, PET_REVIEW_FRAME_MS,
};
static const uint16_t look_hold_durations[] = {850};
static const uint16_t look_turn_durations[] = {100, 100, 100, 100, 100, 100, 100, 100, 220};
static const uint16_t excited_durations[] = {95, 95, 95, 95, 180};
static const uint16_t sleepy_durations[] = {240, 260, 300, 420, 700};

#define ARRAY_COUNT(values) (sizeof(values) / sizeof((values)[0]))
_Static_assert(ARRAY_COUNT(idle_durations) == PET_FRAME_IDLE_COUNT, "idle duration contract");
_Static_assert(ARRAY_COUNT(blink_durations) == PET_FRAME_IDLE_COUNT, "blink duration contract");
_Static_assert(ARRAY_COUNT(run_durations) == PET_FRAME_RUNNING_RIGHT_COUNT, "directional run contract");
_Static_assert(ARRAY_COUNT(wave_durations) == PET_FRAME_WAVING_COUNT, "wave duration contract");
_Static_assert(ARRAY_COUNT(jump_durations) == PET_FRAME_JUMPING_COUNT, "jump duration contract");
_Static_assert(ARRAY_COUNT(failed_durations) == PET_FRAME_FAILED_COUNT, "failed duration contract");
_Static_assert(ARRAY_COUNT(waiting_durations) == PET_FRAME_WAITING_COUNT, "waiting duration contract");
_Static_assert(ARRAY_COUNT(running_durations) == PET_FRAME_RUNNING_COUNT, "running duration contract");
_Static_assert(ARRAY_COUNT(review_durations) == PET_FRAME_REVIEW_COUNT, "review duration contract");
_Static_assert(ARRAY_COUNT(look_hold_durations) == 1, "look hold contract");
_Static_assert(ARRAY_COUNT(look_turn_durations) == 9, "look turn contract");
_Static_assert(ARRAY_COUNT(excited_durations) == PET_FRAME_JUMPING_COUNT,
               "excited duration contract");
_Static_assert(ARRAY_COUNT(sleepy_durations) == 5, "sleepy duration contract");
_Static_assert(PET_FRAME_LOOK_FIRST + PET_FRAME_LOOK_COUNT == PET_FRAME_COUNT,
               "v2 frame ranges must fill the generated atlas contract");

static const pet_action_manifest_t action_manifest[ACTION_COUNT] = {
    [ACTION_IDLE] = {"idle", PET_FRAME_IDLE_FIRST, PET_FRAME_IDLE_COUNT, idle_durations,
                     PRIORITY_IDLE, ACTION_CONTEXT, true, true},
    [ACTION_BLINK] = {"blink", PET_FRAME_IDLE_FIRST, PET_FRAME_IDLE_COUNT, blink_durations,
                      PRIORITY_IDLE, ACTION_CONTEXT, false, true},
    [ACTION_LOOK_UP] = {"look_up", PET_FRAME_LOOK_FIRST, 1, look_hold_durations,
                        PRIORITY_WEATHER, ACTION_CONTEXT, false, true},
    [ACTION_LOOK_LEFT] = {"look_left", PET_FRAME_LOOK_FIRST + 12, 1, look_hold_durations,
                          PRIORITY_TOUCH, ACTION_CONTEXT, false, false},
    [ACTION_LOOK_RIGHT] = {"look_right", PET_FRAME_LOOK_FIRST + 4, 1, look_hold_durations,
                           PRIORITY_TOUCH, ACTION_CONTEXT, false, false},
    [ACTION_WAVE] = {"wave", PET_FRAME_WAVING_FIRST, PET_FRAME_WAVING_COUNT, wave_durations,
                     PRIORITY_TOUCH, ACTION_CONTEXT, false, false},
    [ACTION_PRESENT] = {"present", PET_FRAME_WAVING_FIRST, PET_FRAME_WAVING_COUNT, wave_durations,
                        PRIORITY_WEATHER, ACTION_CONTEXT, false, true},
    [ACTION_THINK] = {"think", PET_FRAME_REVIEW_FIRST, PET_FRAME_REVIEW_COUNT, review_durations,
                      PRIORITY_LIFECYCLE, ACTION_CONTEXT, false, true},
    [ACTION_HAPPY] = {"happy", PET_FRAME_JUMPING_FIRST, PET_FRAME_JUMPING_COUNT, jump_durations,
                      PRIORITY_TOUCH, ACTION_CONTEXT, false, false},
    [ACTION_EXCITED] = {"excited", PET_FRAME_JUMPING_FIRST, PET_FRAME_JUMPING_COUNT, excited_durations,
                        PRIORITY_TOUCH, ACTION_CONTEXT, false, false},
    [ACTION_SLEEPY] = {"sleepy", PET_FRAME_FAILED_FIRST + 3, 5, sleepy_durations,
                       PRIORITY_WEATHER, ACTION_CONTEXT, false, true},
    [ACTION_SIT] = {"sit", PET_FRAME_FAILED_FIRST + 7, 1, look_hold_durations,
                    PRIORITY_WEATHER, ACTION_CONTEXT, false, true},
    [ACTION_RUN_LEFT] = {"run_left", PET_FRAME_RUNNING_LEFT_FIRST, PET_FRAME_RUNNING_LEFT_COUNT,
                         run_durations, PRIORITY_LIFECYCLE, ACTION_CONTEXT, true, true},
    [ACTION_RUN_RIGHT] = {"run_right", PET_FRAME_RUNNING_RIGHT_FIRST, PET_FRAME_RUNNING_RIGHT_COUNT,
                          run_durations, PRIORITY_LIFECYCLE, ACTION_CONTEXT, true, true},
    [ACTION_TURN_AROUND] = {"turn_around", PET_FRAME_LOOK_FIRST + 4, 9, look_turn_durations,
                            PRIORITY_TOUCH, ACTION_CONTEXT, false, false},
    [ACTION_WAITING_LONG] = {"waiting_long", PET_FRAME_WAITING_FIRST, PET_FRAME_WAITING_COUNT,
                             waiting_durations, PRIORITY_LIFECYCLE, ACTION_CONTEXT, true, true},
    [ACTION_REVIEW_POSITIVE] = {"review_positive", PET_FRAME_REVIEW_FIRST, PET_FRAME_REVIEW_COUNT,
                                review_durations, PRIORITY_LIFECYCLE, ACTION_HAPPY, false, true},
    [ACTION_REVIEW_CONCERNED] = {"review_concerned", PET_FRAME_FAILED_FIRST, PET_FRAME_FAILED_COUNT,
                                 failed_durations, PRIORITY_LIFECYCLE, ACTION_CONTEXT, false, true},
    [ACTION_NOTIFICATION] = {"notification", PET_FRAME_WAVING_FIRST, PET_FRAME_WAVING_COUNT,
                             wave_durations, PRIORITY_TOUCH, ACTION_CONTEXT, false, false},
    [ACTION_WEATHER_REACTION] = {"weather_reaction", PET_FRAME_WAVING_FIRST, PET_FRAME_WAVING_COUNT,
                                 wave_durations, PRIORITY_WEATHER, ACTION_CONTEXT, false, true},
    [ACTION_WEATHER_CONCERNED] = {"weather_concerned", PET_FRAME_FAILED_FIRST, PET_FRAME_FAILED_COUNT,
                                  failed_durations, PRIORITY_WEATHER, ACTION_CONTEXT, false, true},
    [ACTION_RUNNING] = {"running", PET_FRAME_RUNNING_FIRST, PET_FRAME_RUNNING_COUNT, running_durations,
                        PRIORITY_LIFECYCLE, ACTION_CONTEXT, true, true},
    [ACTION_WAITING] = {"waiting", PET_FRAME_WAITING_FIRST, PET_FRAME_WAITING_COUNT, waiting_durations,
                        PRIORITY_LIFECYCLE, ACTION_CONTEXT, true, true},
    [ACTION_REVIEW] = {"review", PET_FRAME_REVIEW_FIRST, PET_FRAME_REVIEW_COUNT, review_durations,
                       PRIORITY_LIFECYCLE, ACTION_CONTEXT, true, true},
    [ACTION_FAILED] = {"failed", PET_FRAME_FAILED_FIRST, PET_FRAME_FAILED_COUNT, failed_durations,
                       PRIORITY_CRITICAL, ACTION_CONTEXT, false, false},
};
_Static_assert(ARRAY_COUNT(action_manifest) == ACTION_COUNT, "every action needs a manifest entry");
_Static_assert(PET_FRAME_W * PET_FRAME_SCALE / LV_SCALE_NONE == 456,
               "v2 pet must render 456 pixels wide");
_Static_assert(PET_FRAME_H * PET_FRAME_SCALE / LV_SCALE_NONE == 612,
               "v2 pet must render 612 pixels tall");
_Static_assert((DISPLAY_WIDTH - 456) / 2 == 12, "home pet should keep 12 pixel side margins");
_Static_assert(DISPLAY_HEIGHT - PET_PANEL_TOP == 280,
               "open panel intentionally exposes 280 pixels of the upper body");

typedef struct {
    bool valid;
    int64_t unix_epoch;
    int64_t received_at_us;
    int32_t utc_offset_seconds;
} clock_data_t;

typedef struct {
    bool valid;
    pet_weather_command_t values;
    bool stale_reaction_sent;
} weather_data_t;

typedef struct {
    lv_obj_t *screen;
    lv_obj_t *image;
    lv_obj_t *top_bar;
    lv_obj_t *top_time;
    lv_obj_t *top_weather_dot;
    lv_obj_t *top_weather;
    lv_obj_t *status_card;
    lv_obj_t *status_dot;
    lv_obj_t *status_label;
    lv_obj_t *today_panel;
    lv_obj_t *today_time;
    lv_obj_t *today_weekday;
    lv_obj_t *today_date;
    lv_obj_t *today_temperature;
    lv_obj_t *today_condition;
    lv_obj_t *today_high_low;
    lv_obj_t *today_updated;
    lv_obj_t *pet_tap_zone;
    lv_obj_t *top_gesture_zone;
    lv_timer_t *animation_timer;
    lv_timer_t *info_timer;
    pet_lifecycle_t lifecycle;
    pet_action_id_t base_action;
    pet_action_id_t active_action;
    pet_action_id_t pending_action;
    uint8_t action_frame;
    int32_t panel_progress;
    int32_t gesture_start_progress;
    int16_t gesture_start_y;
    bool gesture_active;
    bool gesture_moved;
    int64_t last_tap_us;
    clock_data_t clock;
    weather_data_t weather;
} pet_ui_t;

static pet_ui_t ui;
static portMUX_TYPE state_lock = portMUX_INITIALIZER_UNLOCKED;
static volatile pet_lifecycle_t protocol_state = PET_LIFECYCLE_IDLE;

static pet_lifecycle_t get_protocol_state(void)
{
    portENTER_CRITICAL(&state_lock);
    pet_lifecycle_t state = protocol_state;
    portEXIT_CRITICAL(&state_lock);
    return state;
}

static void set_protocol_state(pet_lifecycle_t state)
{
    portENTER_CRITICAL(&state_lock);
    protocol_state = state;
    portEXIT_CRITICAL(&state_lock);
}

static lv_color_t lifecycle_colour(pet_lifecycle_t state)
{
    switch (state) {
    case PET_LIFECYCLE_RUNNING: return lv_color_hex(0x49D17D);
    case PET_LIFECYCLE_WAITING: return lv_color_hex(0xF4C95D);
    case PET_LIFECYCLE_REVIEW: return lv_color_hex(0xE95773);
    default: return lv_color_hex(0xDDE6EF);
    }
}

static lv_color_t weather_colour(pet_weather_condition_t condition)
{
    switch (condition) {
    case PET_WEATHER_CLEAR: return lv_color_hex(0xFFD75A);
    case PET_WEATHER_PARTLY_CLOUDY: return lv_color_hex(0xB7C8DA);
    case PET_WEATHER_CLOUDY: return lv_color_hex(0x82909E);
    case PET_WEATHER_FOG: return lv_color_hex(0xA7B4C0);
    case PET_WEATHER_RAIN: return lv_color_hex(0x54A7FF);
    case PET_WEATHER_SNOW: return lv_color_hex(0xD7F3FF);
    case PET_WEATHER_THUNDER: return lv_color_hex(0xC88CFF);
    default: return lv_color_hex(0x55616D);
    }
}

static pet_action_id_t lifecycle_action(pet_lifecycle_t state)
{
    switch (state) {
    case PET_LIFECYCLE_RUNNING: return ACTION_RUNNING;
    case PET_LIFECYCLE_WAITING: return ACTION_WAITING;
    case PET_LIFECYCLE_REVIEW: return ACTION_REVIEW;
    default: return ACTION_IDLE;
    }
}

static uint32_t action_duration(pet_action_id_t action, uint8_t frame)
{
    const pet_action_manifest_t *manifest = &action_manifest[action];
    if (frame >= manifest->frame_count) frame = manifest->frame_count - 1;
    return manifest->durations[frame];
}

static void show_frame_locked(void)
{
    const pet_action_manifest_t *manifest = &action_manifest[ui.active_action];
    uint8_t index = manifest->first_frame + ui.action_frame;
    if (index >= PET_FRAME_COUNT) index = PET_FRAME_IDLE_FIRST;
    lv_image_set_src(ui.image, PET_FRAMES[index]);
}

static void set_active_action_locked(pet_action_id_t action)
{
    ui.active_action = action;
    ui.action_frame = 0;
    show_frame_locked();
    if (ui.animation_timer != NULL) {
        lv_timer_set_period(ui.animation_timer, action_duration(action, 0));
        lv_timer_reset(ui.animation_timer);
    }
}

static bool can_interrupt_with(pet_action_id_t action)
{
    const pet_action_manifest_t *current = &action_manifest[ui.active_action];
    const pet_action_manifest_t *incoming = &action_manifest[action];
    return pet_action_can_interrupt(current->priority, current->interruptible,
                                    incoming->priority);
}

static void queue_or_start_action_locked(pet_action_id_t action)
{
    if (can_interrupt_with(action)) {
        set_active_action_locked(action);
        return;
    }
    if (pet_action_should_replace_pending(
            ui.pending_action != ACTION_COUNT,
            ui.pending_action == ACTION_COUNT ? 0 : action_manifest[ui.pending_action].priority,
            action_manifest[action].priority)) {
        ui.pending_action = action;
    }
}

static pet_action_id_t contextual_action_locked(void)
{
    if (ui.pending_action != ACTION_COUNT &&
        action_manifest[ui.pending_action].priority >= action_manifest[ui.base_action].priority) {
        pet_action_id_t pending = ui.pending_action;
        ui.pending_action = ACTION_COUNT;
        return pending;
    }
    if (ui.panel_progress == PET_PANEL_PROGRESS_MAX && ui.base_action == ACTION_IDLE) {
        return ACTION_LOOK_UP;
    }
    return ui.base_action;
}

static void update_animation(lv_timer_t *timer)
{
    (void)timer;
    const pet_action_manifest_t *manifest = &action_manifest[ui.active_action];
    if (ui.action_frame + 1 < manifest->frame_count) {
        ++ui.action_frame;
    } else if (manifest->loop) {
        if (ui.pending_action != ACTION_COUNT) {
            pet_action_id_t pending = ui.pending_action;
            ui.pending_action = ACTION_COUNT;
            set_active_action_locked(pending);
            return;
        }
        ui.action_frame = 0;
    } else if (manifest->next_action != ACTION_CONTEXT) {
        set_active_action_locked((pet_action_id_t)manifest->next_action);
        return;
    } else {
        set_active_action_locked(contextual_action_locked());
        return;
    }
    show_frame_locked();
    lv_timer_set_period(ui.animation_timer, action_duration(ui.active_action, ui.action_frame));
}

static void apply_lifecycle_locked(pet_lifecycle_t state)
{
    pet_action_id_t previous_base = ui.base_action;
    ui.lifecycle = state;
    ui.base_action = lifecycle_action(state);
    set_protocol_state(state);
    lv_label_set_text(ui.status_label, pet_lifecycle_name(state));
    lv_obj_set_style_bg_color(ui.status_dot, lifecycle_colour(state), 0);
    lv_obj_set_style_border_color(ui.status_card, lifecycle_colour(state), 0);

    if (ui.active_action == previous_base || can_interrupt_with(ui.base_action)) {
        set_active_action_locked(contextual_action_locked());
    }
}

static void apply_lifecycle(pet_lifecycle_t state, bool acknowledge)
{
    if (!bsp_display_lock(1000)) {
        if (acknowledge) printf("ERR display busy\n");
        return;
    }
    apply_lifecycle_locked(state);
    bsp_display_unlock();

    if (acknowledge) printf("OK %s\n", pet_lifecycle_name(state));
}

static int64_t current_epoch_locked(void)
{
    if (!ui.clock.valid) return -1;
    return pet_clock_epoch_at(ui.clock.unix_epoch, ui.clock.received_at_us,
                              esp_timer_get_time());
}

static void format_temperature(char *buffer, size_t capacity, int tenths)
{
    int absolute = tenths < 0 ? -tenths : tenths;
    if (absolute % 10 == 0) {
        snprintf(buffer, capacity, "%s%d", tenths < 0 ? "-" : "", absolute / 10);
    } else {
        snprintf(buffer, capacity, "%s%d.%d", tenths < 0 ? "-" : "", absolute / 10, absolute % 10);
    }
}

static const char *weather_short_label(pet_weather_condition_t condition)
{
    switch (condition) {
    case PET_WEATHER_CLEAR: return "SUN";
    case PET_WEATHER_PARTLY_CLOUDY: return "PARTLY";
    case PET_WEATHER_CLOUDY: return "CLOUD";
    case PET_WEATHER_FOG: return "FOG";
    case PET_WEATHER_RAIN: return "RAIN";
    case PET_WEATHER_SNOW: return "SNOW";
    case PET_WEATHER_THUNDER: return "STORM";
    default: return "--";
    }
}

static void update_info_labels_locked(void)
{
    int64_t now = current_epoch_locked();
    if (now < 0) {
        lv_label_set_text(ui.top_time, "--:--");
        lv_label_set_text(ui.today_time, "--:--");
        lv_label_set_text(ui.today_weekday, "Waiting for Mac");
        lv_label_set_text(ui.today_date, "Time unavailable");
    } else {
        time_t local_epoch = (time_t)pet_epoch_add_seconds(
            now, ui.clock.utc_offset_seconds);
        struct tm local_time;
        if (gmtime_r(&local_epoch, &local_time) != NULL) {
            static const char *months[] = {
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December",
            };
            char clock_text[16];
            char weekday[20];
            char date[32];
            strftime(clock_text, sizeof(clock_text), "%H:%M", &local_time);
            strftime(weekday, sizeof(weekday), "%A", &local_time);
            snprintf(date, sizeof(date), "%d %s %d", local_time.tm_mday,
                     months[local_time.tm_mon], local_time.tm_year + 1900);
            lv_label_set_text(ui.top_time, clock_text);
            lv_label_set_text(ui.today_time, clock_text);
            lv_label_set_text(ui.today_weekday, weekday);
            lv_label_set_text(ui.today_date, date);
        }
    }

    if (!ui.weather.valid) {
        lv_label_set_text(ui.top_weather, "--  -- \xC2\xB0" "C");
        lv_label_set_text(ui.today_temperature, "-- \xC2\xB0" "C");
        lv_label_set_text(ui.today_condition, "Weather unavailable");
        lv_label_set_text(ui.today_high_low, "H: --   L: --   Rain: --");
        lv_label_set_text(ui.today_updated, "Waiting for weather sync");
        lv_obj_set_style_bg_color(ui.top_weather_dot, weather_colour(PET_WEATHER_UNKNOWN), 0);
        return;
    }

    const pet_weather_command_t *weather = &ui.weather.values;
    char current[16];
    char low[16];
    char high[16];
    char text[96];
    format_temperature(current, sizeof(current), weather->current_temperature_tenths);
    format_temperature(low, sizeof(low), weather->low_temperature_tenths);
    format_temperature(high, sizeof(high), weather->high_temperature_tenths);
    snprintf(text, sizeof(text), "%s  %s \xC2\xB0" "C",
             weather_short_label(weather->condition), current);
    lv_label_set_text(ui.top_weather, text);
    snprintf(text, sizeof(text), "%s \xC2\xB0" "C", current);
    lv_label_set_text(ui.today_temperature, text);
    lv_label_set_text(ui.today_condition, pet_weather_condition_label(weather->condition));
    snprintf(text, sizeof(text), "H: %s\xC2\xB0   L: %s\xC2\xB0   Rain: %d%%", high, low,
             weather->rain_probability);
    lv_label_set_text(ui.today_high_low, text);
    lv_obj_set_style_bg_color(ui.top_weather_dot, weather_colour(weather->condition), 0);

    int64_t age = now >= 0 ? now - weather->updated_epoch : -1;
    pet_weather_freshness_t freshness = pet_weather_freshness(now, weather->updated_epoch);
    if (freshness == PET_WEATHER_TIME_UNKNOWN) {
        lv_label_set_text(ui.today_updated, "Updated recently - Open-Meteo");
    } else if (freshness == PET_WEATHER_STALE) {
        snprintf(text, sizeof(text), "Weather unavailable - last update %lldh ago",
                 (long long)(age / 3600));
        lv_label_set_text(ui.today_updated, text);
        lv_obj_set_style_text_opa(ui.top_weather, LV_OPA_50, 0);
        if (!ui.weather.stale_reaction_sent) {
            ui.weather.stale_reaction_sent = true;
            queue_or_start_action_locked(ACTION_WEATHER_CONCERNED);
        }
    } else if (freshness == PET_WEATHER_AGING) {
        snprintf(text, sizeof(text), "Updated %lldm ago - Open-Meteo",
                 (long long)(age / 60));
        lv_label_set_text(ui.today_updated, text);
        lv_obj_set_style_text_opa(ui.top_weather, LV_OPA_70, 0);
    } else {
        snprintf(text, sizeof(text), "Updated %lldm ago - Open-Meteo",
                 (long long)(age / 60));
        lv_label_set_text(ui.today_updated, text);
        lv_obj_set_style_text_opa(ui.top_weather, LV_OPA_COVER, 0);
    }
}

static void update_info_timer(lv_timer_t *timer)
{
    (void)timer;
    update_info_labels_locked();
}

static void apply_clock_locked(const pet_clock_command_t *clock)
{
    ui.clock.valid = true;
    ui.clock.unix_epoch = clock->unix_epoch;
    ui.clock.utc_offset_seconds = clock->utc_offset_seconds;
    ui.clock.received_at_us = esp_timer_get_time();
    update_info_labels_locked();
}

static void apply_weather_locked(const pet_weather_command_t *weather)
{
    ui.weather.valid = true;
    ui.weather.values = *weather;
    ui.weather.stale_reaction_sent = false;
    update_info_labels_locked();

    pet_action_id_t reaction = ACTION_WEATHER_REACTION;
    if (pet_weather_condition_is_critical(weather->condition)) {
        reaction = ACTION_FAILED;
    } else if (weather->condition == PET_WEATHER_RAIN ||
               weather->condition == PET_WEATHER_SNOW ||
               weather->condition == PET_WEATHER_FOG) {
        reaction = ACTION_WEATHER_CONCERNED;
    } else if (weather->current_temperature_tenths >= 320 ||
               weather->current_temperature_tenths <= 120) {
        reaction = ACTION_SLEEPY;
    }
    queue_or_start_action_locked(reaction);
}

static void set_pet_render_top_locked(int32_t top)
{
    int32_t rendered_height = PET_FRAME_H * PET_FRAME_SCALE / LV_SCALE_NONE;
    int32_t transform_expansion = (rendered_height - PET_FRAME_H) / 2;
    lv_obj_align(ui.image, LV_ALIGN_TOP_MID, 0, top + transform_expansion);
}

static void set_panel_progress_locked(int32_t progress)
{
    if (progress < 0) progress = 0;
    if (progress > PET_PANEL_PROGRESS_MAX) progress = PET_PANEL_PROGRESS_MAX;
    ui.panel_progress = progress;

    int32_t panel_y = -TODAY_PANEL_HEIGHT +
        TODAY_PANEL_HEIGHT * progress / PET_PANEL_PROGRESS_MAX;
    lv_obj_set_y(ui.today_panel, panel_y);
    int32_t pet_top = PET_NORMAL_TOP +
        (PET_PANEL_TOP - PET_NORMAL_TOP) * progress / PET_PANEL_PROGRESS_MAX;
    set_pet_render_top_locked(pet_top);

    lv_opa_t home_opa = (lv_opa_t)(LV_OPA_COVER * (PET_PANEL_PROGRESS_MAX - progress) /
                                   PET_PANEL_PROGRESS_MAX);
    lv_obj_set_style_opa(ui.top_bar, home_opa, 0);
    lv_obj_set_style_opa(ui.status_card, home_opa, 0);
    if (progress > PET_PANEL_PROGRESS_MAX / 3) {
        lv_obj_add_flag(ui.pet_tap_zone, LV_OBJ_FLAG_HIDDEN);
        lv_obj_remove_flag(ui.status_card, LV_OBJ_FLAG_CLICKABLE);
    } else {
        lv_obj_remove_flag(ui.pet_tap_zone, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(ui.status_card, LV_OBJ_FLAG_CLICKABLE);
    }

    if (progress == PET_PANEL_PROGRESS_MAX && ui.base_action == ACTION_IDLE &&
        action_manifest[ui.active_action].priority <= PRIORITY_WEATHER) {
        set_active_action_locked(ACTION_LOOK_UP);
    } else if (progress == 0 && ui.active_action == ACTION_LOOK_UP) {
        set_active_action_locked(ui.base_action);
    }
}

static void panel_progress_animation(void *variable, int32_t value)
{
    (void)variable;
    set_panel_progress_locked(value);
}

static void animate_panel_to_locked(int32_t target)
{
    lv_anim_delete(&ui, panel_progress_animation);
    lv_anim_t animation;
    lv_anim_init(&animation);
    lv_anim_set_var(&animation, &ui);
    lv_anim_set_exec_cb(&animation, panel_progress_animation);
    lv_anim_set_values(&animation, ui.panel_progress, target);
    lv_anim_set_duration(&animation, 220);
    lv_anim_set_path_cb(&animation, lv_anim_path_ease_out);
    lv_anim_start(&animation);

    if (target == 0 && ui.pending_action == ACTION_LOOK_UP) {
        ui.pending_action = ACTION_COUNT;
    } else if (target == PET_PANEL_PROGRESS_MAX && ui.base_action == ACTION_IDLE) {
        queue_or_start_action_locked(ACTION_LOOK_UP);
    }
}

static void panel_drag_event(lv_event_t *event)
{
    lv_event_code_t code = lv_event_get_code(event);
    lv_indev_t *input = lv_indev_active();
    if (input == NULL) return;

    lv_point_t point;
    lv_indev_get_point(input, &point);
    if (code == LV_EVENT_PRESSED) {
        ui.gesture_active = pet_panel_gesture_can_begin(ui.panel_progress, point.y);
        ui.gesture_start_y = point.y;
        ui.gesture_start_progress = ui.panel_progress;
        ui.gesture_moved = false;
        lv_anim_delete(&ui, panel_progress_animation);
    } else if (code == LV_EVENT_PRESSING && ui.gesture_active) {
        int32_t delta = point.y - ui.gesture_start_y;
        if (delta > PANEL_DRAG_THRESHOLD || delta < -PANEL_DRAG_THRESHOLD) {
            ui.gesture_moved = true;
        }
        set_panel_progress_locked(pet_panel_progress_from_drag(
            ui.gesture_start_progress, delta, TODAY_PANEL_HEIGHT));
    } else if (code == LV_EVENT_RELEASED && ui.gesture_active) {
        int32_t delta = point.y - ui.gesture_start_y;
        int32_t target = pet_panel_release_target(ui.panel_progress, delta);
        animate_panel_to_locked(target);
        ui.gesture_active = false;
    }
}

static void tap_pet(lv_event_t *event)
{
    if (lv_event_get_code(event) != LV_EVENT_CLICKED || ui.panel_progress > 0) return;
    int64_t now = esp_timer_get_time();
    if (now - ui.last_tap_us < TAP_COOLDOWN_US) return;
    ui.last_tap_us = now;

    static const pet_action_id_t reactions[] = {
        ACTION_BLINK,
        ACTION_WAVE,
        ACTION_HAPPY,
        ACTION_LOOK_LEFT,
        ACTION_LOOK_RIGHT,
        ACTION_TURN_AROUND,
        ACTION_EXCITED,
    };
    pet_action_id_t reaction = reactions[esp_random() %
        (sizeof(reactions) / sizeof(reactions[0]))];
    queue_or_start_action_locked(reaction);
}

static void cycle_state(lv_event_t *event)
{
    if (lv_event_get_code(event) != LV_EVENT_CLICKED) return;
    pet_lifecycle_t current = get_protocol_state();
    apply_lifecycle_locked((pet_lifecycle_t)((current + 1) % 4));
}

static lv_obj_t *create_label(lv_obj_t *parent, const char *text, const lv_font_t *font,
                              lv_color_t colour, int x, int y)
{
    lv_obj_t *label = lv_label_create(parent);
    lv_label_set_text(label, text);
    lv_obj_set_style_text_font(label, font, 0);
    lv_obj_set_style_text_color(label, colour, 0);
    lv_obj_set_pos(label, x, y);
    lv_obj_remove_flag(label, LV_OBJ_FLAG_CLICKABLE);
    return label;
}

static void create_top_bar(void)
{
    ui.top_bar = lv_obj_create(ui.screen);
    lv_obj_set_size(ui.top_bar, 440, 46);
    lv_obj_align(ui.top_bar, LV_ALIGN_TOP_MID, 0, 12);
    lv_obj_set_style_radius(ui.top_bar, 20, 0);
    lv_obj_set_style_bg_color(ui.top_bar, lv_color_hex(0x101820), 0);
    lv_obj_set_style_bg_opa(ui.top_bar, LV_OPA_70, 0);
    lv_obj_set_style_border_width(ui.top_bar, 0, 0);
    lv_obj_set_style_pad_all(ui.top_bar, 0, 0);
    lv_obj_clear_flag(ui.top_bar, LV_OBJ_FLAG_SCROLLABLE);

    ui.top_time = create_label(ui.top_bar, "--:--", &lv_font_montserrat_20,
                               lv_color_hex(0xFFFFFF), 18, 11);
    ui.top_weather_dot = lv_obj_create(ui.top_bar);
    lv_obj_remove_style_all(ui.top_weather_dot);
    lv_obj_set_size(ui.top_weather_dot, 12, 12);
    lv_obj_set_style_radius(ui.top_weather_dot, 6, 0);
    lv_obj_set_style_bg_opa(ui.top_weather_dot, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(ui.top_weather_dot, weather_colour(PET_WEATHER_UNKNOWN), 0);
    lv_obj_set_pos(ui.top_weather_dot, 252, 17);
    ui.top_weather = create_label(ui.top_bar, "--  -- \xC2\xB0" "C", &lv_font_montserrat_14,
                                  lv_color_hex(0xFFFFFF), 274, 15);
}

static void create_status_card(void)
{
    ui.status_card = lv_obj_create(ui.screen);
    lv_obj_set_size(ui.status_card, 286, 60);
    lv_obj_align(ui.status_card, LV_ALIGN_BOTTOM_MID, 0, -22);
    lv_obj_set_style_radius(ui.status_card, 18, 0);
    lv_obj_set_style_bg_color(ui.status_card, lv_color_hex(0x101820), 0);
    lv_obj_set_style_bg_opa(ui.status_card, LV_OPA_90, 0);
    lv_obj_set_style_border_width(ui.status_card, 2, 0);
    lv_obj_set_style_border_color(ui.status_card, lifecycle_colour(PET_LIFECYCLE_IDLE), 0);
    lv_obj_clear_flag(ui.status_card, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(ui.status_card, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(ui.status_card, cycle_state, LV_EVENT_CLICKED, NULL);

    ui.status_dot = lv_obj_create(ui.status_card);
    lv_obj_remove_style_all(ui.status_dot);
    lv_obj_set_size(ui.status_dot, 16, 16);
    lv_obj_align(ui.status_dot, LV_ALIGN_LEFT_MID, 22, 0);
    lv_obj_set_style_radius(ui.status_dot, 8, 0);
    lv_obj_set_style_bg_color(ui.status_dot, lifecycle_colour(PET_LIFECYCLE_IDLE), 0);
    lv_obj_set_style_bg_opa(ui.status_dot, LV_OPA_COVER, 0);
    lv_obj_remove_flag(ui.status_dot, LV_OBJ_FLAG_CLICKABLE);

    ui.status_label = lv_label_create(ui.status_card);
    lv_label_set_text(ui.status_label, "IDLE");
    lv_obj_set_style_text_color(ui.status_label, lv_color_hex(0xFFFFFF), 0);
    lv_obj_set_style_text_font(ui.status_label, &lv_font_montserrat_14, 0);
    lv_obj_align(ui.status_label, LV_ALIGN_LEFT_MID, 52, 0);
    lv_obj_remove_flag(ui.status_label, LV_OBJ_FLAG_CLICKABLE);

    lv_obj_t *hint = lv_label_create(ui.status_card);
    lv_label_set_text(hint, "tap state");
    lv_obj_set_style_text_color(hint, lv_color_hex(0x82909E), 0);
    lv_obj_align(hint, LV_ALIGN_RIGHT_MID, -18, 0);
    lv_obj_remove_flag(hint, LV_OBJ_FLAG_CLICKABLE);
}

static void create_today_panel(void)
{
    ui.today_panel = lv_obj_create(ui.screen);
    lv_obj_set_size(ui.today_panel, DISPLAY_WIDTH, TODAY_PANEL_HEIGHT);
    lv_obj_set_pos(ui.today_panel, 0, -TODAY_PANEL_HEIGHT);
    lv_obj_set_style_radius(ui.today_panel, 30, 0);
    lv_obj_set_style_bg_color(ui.today_panel, lv_color_hex(0x0C1620), 0);
    lv_obj_set_style_bg_opa(ui.today_panel, (lv_opa_t)242, 0);
    lv_obj_set_style_border_width(ui.today_panel, 1, 0);
    lv_obj_set_style_border_color(ui.today_panel, lv_color_hex(0x344454), 0);
    lv_obj_set_style_pad_all(ui.today_panel, 0, 0);
    lv_obj_clear_flag(ui.today_panel, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(ui.today_panel, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(ui.today_panel, panel_drag_event, LV_EVENT_ALL, NULL);

    create_label(ui.today_panel, "TODAY", &lv_font_montserrat_14,
                 lv_color_hex(0x82909E), 28, 22);
    ui.today_time = create_label(ui.today_panel, "--:--", &lv_font_montserrat_28,
                                 lv_color_hex(0xFFFFFF), 26, 52);
    ui.today_weekday = create_label(ui.today_panel, "Waiting for Mac", &lv_font_montserrat_20,
                                    lv_color_hex(0xE7EDF3), 28, 94);
    ui.today_date = create_label(ui.today_panel, "Time unavailable", &lv_font_montserrat_14,
                                 lv_color_hex(0x9EACB9), 28, 126);

    lv_obj_t *separator = lv_obj_create(ui.today_panel);
    lv_obj_remove_style_all(separator);
    lv_obj_set_size(separator, 424, 1);
    lv_obj_set_style_bg_color(separator, lv_color_hex(0x344454), 0);
    lv_obj_set_style_bg_opa(separator, LV_OPA_COVER, 0);
    lv_obj_set_pos(separator, 28, 170);
    lv_obj_remove_flag(separator, LV_OBJ_FLAG_CLICKABLE);

    create_label(ui.today_panel, "HONG KONG", &lv_font_montserrat_14,
                 lv_color_hex(0x82909E), 28, 195);
    ui.today_temperature = create_label(ui.today_panel, "-- \xC2\xB0" "C", &lv_font_montserrat_28,
                                        lv_color_hex(0xFFFFFF), 28, 224);
    ui.today_condition = create_label(ui.today_panel, "Weather unavailable", &lv_font_montserrat_20,
                                      lv_color_hex(0xE7EDF3), 28, 270);
    ui.today_high_low = create_label(ui.today_panel, "H: --   L: --   Rain: --",
                                     &lv_font_montserrat_14, lv_color_hex(0xB9C6D2), 28, 314);
    ui.today_updated = create_label(ui.today_panel, "Waiting for weather sync",
                                    &lv_font_montserrat_14, lv_color_hex(0x82909E), 28, 354);
    create_label(ui.today_panel, "Swipe up to return to your Pet", &lv_font_montserrat_14,
                 lv_color_hex(0x60707E), 28, 455);
}

static void create_touch_zones(void)
{
    ui.pet_tap_zone = lv_obj_create(ui.screen);
    lv_obj_remove_style_all(ui.pet_tap_zone);
    lv_obj_set_size(ui.pet_tap_zone, 430, 610);
    lv_obj_align(ui.pet_tap_zone, LV_ALIGN_TOP_MID, 0, 78);
    lv_obj_add_flag(ui.pet_tap_zone, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_clear_flag(ui.pet_tap_zone, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(ui.pet_tap_zone, tap_pet, LV_EVENT_CLICKED, NULL);

    ui.top_gesture_zone = lv_obj_create(ui.screen);
    lv_obj_remove_style_all(ui.top_gesture_zone);
    lv_obj_set_size(ui.top_gesture_zone, DISPLAY_WIDTH, PET_TOP_GESTURE_HEIGHT);
    lv_obj_set_pos(ui.top_gesture_zone, 0, 0);
    lv_obj_add_flag(ui.top_gesture_zone, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_clear_flag(ui.top_gesture_zone, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(ui.top_gesture_zone, panel_drag_event, LV_EVENT_ALL, NULL);
}

static void create_ui(void)
{
    ui.screen = lv_screen_active();
    lv_obj_set_style_bg_color(ui.screen, lv_color_hex(0x081018), 0);
    lv_obj_set_style_bg_grad_color(ui.screen, lv_color_hex(0x18222E), 0);
    lv_obj_set_style_bg_grad_dir(ui.screen, LV_GRAD_DIR_VER, 0);
    lv_obj_clear_flag(ui.screen, LV_OBJ_FLAG_SCROLLABLE);

    ui.image = lv_image_create(ui.screen);
    lv_image_set_src(ui.image, PET_FRAMES[PET_FRAME_IDLE_FIRST]);
    lv_image_set_scale(ui.image, PET_FRAME_SCALE);
    lv_image_set_antialias(ui.image, false);
    set_pet_render_top_locked(PET_NORMAL_TOP);
    lv_obj_remove_flag(ui.image, LV_OBJ_FLAG_CLICKABLE);

    create_status_card();
    create_top_bar();
    create_today_panel();
    create_touch_zones();

    ui.lifecycle = PET_LIFECYCLE_IDLE;
    ui.base_action = ACTION_IDLE;
    ui.active_action = ACTION_IDLE;
    ui.pending_action = ACTION_COUNT;
    ui.action_frame = 0;
    ui.panel_progress = 0;
    ui.last_tap_us = -TAP_COOLDOWN_US;
    ui.animation_timer = lv_timer_create(update_animation, action_duration(ACTION_IDLE, 0), NULL);
    ui.info_timer = lv_timer_create(update_info_timer, 1000, NULL);
    update_info_labels_locked();
}

static void process_command(char *line)
{
    pet_command_t command;
    pet_protocol_result_t result = pet_protocol_parse(line, &command);
    if (result == PET_PROTOCOL_EMPTY) return;
    if (result != PET_PROTOCOL_OK) {
        printf("ERR %s\n", pet_protocol_result_name(result));
        return;
    }

    switch (command.type) {
    case PET_COMMAND_STATE:
        apply_lifecycle(command.data.state, true);
        break;
    case PET_COMMAND_PING:
        printf("pong\n");
        break;
    case PET_COMMAND_STATUS:
        printf("STATE %s\n", pet_lifecycle_name(get_protocol_state()));
        break;
    case PET_COMMAND_CAPABILITIES:
        printf("CAPABILITIES 2 lifecycle clock weather today-v1\n");
        break;
    case PET_COMMAND_CLOCK:
        if (!bsp_display_lock(1000)) {
            printf("ERR display busy\n");
            break;
        }
        apply_clock_locked(&command.data.clock);
        bsp_display_unlock();
        printf("OK CLOCK\n");
        break;
    case PET_COMMAND_WEATHER:
        if (!bsp_display_lock(1000)) {
            printf("ERR display busy\n");
            break;
        }
        apply_weather_locked(&command.data.weather);
        bsp_display_unlock();
        printf("OK WEATHER\n");
        break;
    default:
        printf("ERR unknown command\n");
        break;
    }
}

static void serial_task(void *argument)
{
    (void)argument;
    char line[PET_PROTOCOL_LINE_CAPACITY];
    size_t length = 0;
    bool discarding = false;

    while (true) {
        int input = getchar();
        if (input == EOF) {
            clearerr(stdin);
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }
        char character = (char)input;
        if (character == '\n' || character == '\r') {
            if (discarding) {
                discarding = false;
                length = 0;
            } else if (length > 0) {
                line[length] = '\0';
                process_command(line);
                length = 0;
            }
        } else if ((unsigned char)character >= 0x20 && (unsigned char)character <= 0x7E) {
            if (!discarding && length < sizeof(line) - 1) {
                line[length++] = character;
            } else if (!discarding) {
                length = 0;
                discarding = true;
                printf("ERR command too long\n");
            }
        }
    }
}

void app_main(void)
{
    setvbuf(stdin, NULL, _IONBF, 0);
    setvbuf(stdout, NULL, _IONBF, 0);

    lv_display_t *display = bsp_display_start();
    if (display == NULL) {
        ESP_LOGE(TAG, "Display initialization failed");
        return;
    }
    ESP_ERROR_CHECK(bsp_display_brightness_set(80));

    if (!bsp_display_lock(0)) {
        ESP_LOGE(TAG, "Could not lock LVGL");
        return;
    }
    create_ui();
    bsp_display_unlock();

    printf("Codex Pet ESP32-P4 ready\n");
    printf("Board: JC4880P443C-I-W\n");
    printf("Protocol: v2 lifecycle clock weather today-v1\n");
    printf("Commands: idle running waiting review ping status capabilities clock weather\n");

    BaseType_t created = xTaskCreate(serial_task, "codex_pet_serial", 4096, NULL, 5, NULL);
    if (created != pdPASS) ESP_LOGE(TAG, "Could not start Serial task");
}
