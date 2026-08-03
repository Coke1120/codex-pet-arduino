/*
 * Codex Pet for GUITION JC4880P443C-I-W (ESP32-P4 + ESP32-C6).
 *
 * The ESP32-P4 drives the 480x800 display and GT911 touch controller. Private
 * selected-pet art is generated locally as pet_generated.c and stays gitignored.
 */

#include <ctype.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "bsp/esp-bsp.h"
#include "esp_err.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lvgl.h"
#include "pet_generated.h"

#define SERIAL_LINE_CAPACITY 32

static const char *TAG = "codex_pet";

typedef enum {
    PET_IDLE,
    PET_RUNNING,
    PET_WAITING,
    PET_REVIEW,
} pet_state_t;

typedef struct {
    lv_obj_t *screen;
    lv_obj_t *image;
    lv_obj_t *status_card;
    lv_obj_t *status_dot;
    lv_obj_t *status_label;
    lv_timer_t *animation_timer;
    pet_state_t state;
    uint8_t frame;
} pet_ui_t;

static pet_ui_t ui;
static portMUX_TYPE state_lock = portMUX_INITIALIZER_UNLOCKED;
static volatile pet_state_t protocol_state = PET_IDLE;

static pet_state_t get_protocol_state(void)
{
    portENTER_CRITICAL(&state_lock);
    pet_state_t state = protocol_state;
    portEXIT_CRITICAL(&state_lock);
    return state;
}

static void set_protocol_state(pet_state_t state)
{
    portENTER_CRITICAL(&state_lock);
    protocol_state = state;
    portEXIT_CRITICAL(&state_lock);
}

static const char *state_name(pet_state_t state)
{
    switch (state) {
    case PET_RUNNING: return "RUNNING";
    case PET_WAITING: return "WAITING";
    case PET_REVIEW: return "REVIEW";
    default: return "IDLE";
    }
}

static lv_color_t state_colour(pet_state_t state)
{
    switch (state) {
    case PET_RUNNING: return lv_color_hex(0x49D17D);
    case PET_WAITING: return lv_color_hex(0xF4C95D);
    case PET_REVIEW: return lv_color_hex(0xE95773);
    default: return lv_color_hex(0xDDE6EF);
    }
}

static uint32_t state_interval(pet_state_t state)
{
    switch (state) {
    case PET_RUNNING: return 280;
    case PET_WAITING: return 520;
    case PET_REVIEW: return 420;
    default: return 650;
    }
}

static uint8_t state_frame_base(pet_state_t state)
{
    switch (state) {
    case PET_RUNNING: return 2;
    case PET_WAITING: return 4;
    case PET_REVIEW: return 6;
    default: return 0;
    }
}

static void show_frame_locked(void)
{
    uint8_t index = state_frame_base(ui.state) + (ui.frame & 1U);
    lv_image_set_src(ui.image, PET_FRAMES[index]);
}

static void update_frame(lv_timer_t *timer)
{
    (void)timer;
    ui.frame ^= 1U;
    show_frame_locked();
}

static void apply_state_locked(pet_state_t state)
{
    ui.state = state;
    set_protocol_state(state);
    ui.frame = 0;
    lv_label_set_text(ui.status_label, state_name(state));
    lv_obj_set_style_bg_color(ui.status_dot, state_colour(state), 0);
    lv_obj_set_style_border_color(ui.status_card, state_colour(state), 0);
    lv_timer_set_period(ui.animation_timer, state_interval(state));
    show_frame_locked();
    lv_timer_ready(ui.animation_timer);
}

static void apply_state(pet_state_t state, bool acknowledge)
{
    if (!bsp_display_lock(1000)) {
        if (acknowledge) {
            printf("ERR display busy\n");
            fflush(stdout);
        }
        return;
    }
    apply_state_locked(state);
    bsp_display_unlock();

    if (acknowledge) {
        printf("OK %s\n", state_name(state));
        fflush(stdout);
    }
}

static void cycle_state(lv_event_t *event)
{
    (void)event;
    pet_state_t current = get_protocol_state();
    apply_state_locked((pet_state_t)((current + 1) % 4));
}

static void create_ui(void)
{
    ui.screen = lv_screen_active();
    lv_obj_set_style_bg_color(ui.screen, lv_color_hex(0x081018), 0);
    lv_obj_set_style_bg_grad_color(ui.screen, lv_color_hex(0x18222E), 0);
    lv_obj_set_style_bg_grad_dir(ui.screen, LV_GRAD_DIR_VER, 0);
    lv_obj_clear_flag(ui.screen, LV_OBJ_FLAG_SCROLLABLE);

    ui.image = lv_image_create(ui.screen);
    lv_image_set_src(ui.image, PET_FRAMES[0]);
    lv_obj_align(ui.image, LV_ALIGN_TOP_MID, 0, 42);
    lv_obj_remove_flag(ui.image, LV_OBJ_FLAG_CLICKABLE);

    ui.status_card = lv_obj_create(ui.screen);
    lv_obj_set_size(ui.status_card, 330, 64);
    lv_obj_align(ui.status_card, LV_ALIGN_BOTTOM_MID, 0, -24);
    lv_obj_set_style_radius(ui.status_card, 18, 0);
    lv_obj_set_style_bg_color(ui.status_card, lv_color_hex(0x101820), 0);
    lv_obj_set_style_bg_opa(ui.status_card, LV_OPA_90, 0);
    lv_obj_set_style_border_width(ui.status_card, 2, 0);
    lv_obj_set_style_border_color(ui.status_card, state_colour(PET_IDLE), 0);
    lv_obj_clear_flag(ui.status_card, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(ui.status_card, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(ui.status_card, cycle_state, LV_EVENT_CLICKED, NULL);

    ui.status_dot = lv_obj_create(ui.status_card);
    lv_obj_remove_style_all(ui.status_dot);
    lv_obj_set_size(ui.status_dot, 18, 18);
    lv_obj_align(ui.status_dot, LV_ALIGN_LEFT_MID, 24, 0);
    lv_obj_set_style_radius(ui.status_dot, 9, 0);
    lv_obj_set_style_bg_color(ui.status_dot, state_colour(PET_IDLE), 0);
    lv_obj_set_style_bg_opa(ui.status_dot, LV_OPA_COVER, 0);
    lv_obj_remove_flag(ui.status_dot, LV_OBJ_FLAG_CLICKABLE);

    ui.status_label = lv_label_create(ui.status_card);
    lv_label_set_text(ui.status_label, "IDLE");
    lv_obj_set_style_text_color(ui.status_label, lv_color_hex(0xFFFFFF), 0);
    lv_obj_set_style_text_font(ui.status_label, &lv_font_montserrat_14, 0);
    lv_obj_align(ui.status_label, LV_ALIGN_LEFT_MID, 58, 0);
    lv_obj_remove_flag(ui.status_label, LV_OBJ_FLAG_CLICKABLE);

    lv_obj_t *hint = lv_label_create(ui.status_card);
    lv_label_set_text(hint, "tap to test");
    lv_obj_set_style_text_color(hint, lv_color_hex(0x82909E), 0);
    lv_obj_align(hint, LV_ALIGN_RIGHT_MID, -22, 0);
    lv_obj_remove_flag(hint, LV_OBJ_FLAG_CLICKABLE);

    ui.state = PET_IDLE;
    ui.frame = 0;
    ui.animation_timer = lv_timer_create(update_frame, state_interval(PET_IDLE), NULL);
}

static char *trim_and_lower(char *line)
{
    while (isspace((unsigned char)*line)) line++;
    char *end = line + strlen(line);
    while (end > line && isspace((unsigned char)end[-1])) --end;
    *end = '\0';
    for (char *cursor = line; *cursor; ++cursor) {
        *cursor = (char)tolower((unsigned char)*cursor);
    }
    return line;
}

static void process_command(char *raw)
{
    char *command = trim_and_lower(raw);
    if (!strcmp(command, "idle")) apply_state(PET_IDLE, true);
    else if (!strcmp(command, "running")) apply_state(PET_RUNNING, true);
    else if (!strcmp(command, "waiting")) apply_state(PET_WAITING, true);
    else if (!strcmp(command, "review")) apply_state(PET_REVIEW, true);
    else if (!strcmp(command, "ping")) {
        printf("pong\n");
        fflush(stdout);
    } else if (!strcmp(command, "status")) {
        printf("STATE %s\n", state_name(get_protocol_state()));
        fflush(stdout);
    } else if (*command) {
        printf("ERR unknown command: %s\n", command);
        fflush(stdout);
    }
}

static void serial_task(void *argument)
{
    (void)argument;
    char line[SERIAL_LINE_CAPACITY];
    size_t length = 0;
    bool discarding = false;

    while (true) {
        int input = getchar();
        if (input == EOF) {
            clearerr(stdin);
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }
        char c = (char)input;
        if (c == '\n' || c == '\r') {
            if (discarding) {
                discarding = false;
                length = 0;
            } else if (length > 0) {
                line[length] = '\0';
                process_command(line);
                length = 0;
            }
        } else if (!discarding && isprint((unsigned char)c)) {
            if (length < sizeof(line) - 1) line[length++] = c;
            else {
                length = 0;
                discarding = true;
                printf("ERR command too long\n");
                fflush(stdout);
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
    printf("Commands: idle running waiting review ping status\n");

    BaseType_t created = xTaskCreate(serial_task, "codex_pet_serial", 4096, NULL, 5, NULL);
    if (created != pdPASS) ESP_LOGE(TAG, "Could not start Serial task");
}
