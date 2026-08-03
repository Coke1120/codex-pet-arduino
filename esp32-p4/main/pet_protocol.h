#pragma once

#include <stdbool.h>
#include <stdint.h>

#define PET_PROTOCOL_LINE_CAPACITY 128
/* Latest UTC instant that remains within year 9999 at the protocol's
 * maximum timezone offset. This also keeps all firmware epoch arithmetic
 * comfortably inside int64_t. */
#define PET_MAX_UNIX_EPOCH 253402250399LL

typedef enum {
    PET_LIFECYCLE_IDLE,
    PET_LIFECYCLE_RUNNING,
    PET_LIFECYCLE_WAITING,
    PET_LIFECYCLE_REVIEW,
} pet_lifecycle_t;

typedef enum {
    PET_WEATHER_CLEAR,
    PET_WEATHER_PARTLY_CLOUDY,
    PET_WEATHER_CLOUDY,
    PET_WEATHER_FOG,
    PET_WEATHER_RAIN,
    PET_WEATHER_SNOW,
    PET_WEATHER_THUNDER,
    PET_WEATHER_UNKNOWN,
} pet_weather_condition_t;

typedef enum {
    PET_COMMAND_NONE,
    PET_COMMAND_STATE,
    PET_COMMAND_PING,
    PET_COMMAND_STATUS,
    PET_COMMAND_CAPABILITIES,
    PET_COMMAND_CLOCK,
    PET_COMMAND_WEATHER,
    PET_COMMAND_USAGE,
} pet_command_type_t;

typedef enum {
    PET_PROTOCOL_OK,
    PET_PROTOCOL_EMPTY,
    PET_PROTOCOL_UNKNOWN,
    PET_PROTOCOL_INVALID_FORMAT,
    PET_PROTOCOL_OUT_OF_RANGE,
} pet_protocol_result_t;

typedef struct {
    int64_t unix_epoch;
    int32_t utc_offset_seconds;
} pet_clock_command_t;

typedef struct {
    int current_temperature_tenths;
    int low_temperature_tenths;
    int high_temperature_tenths;
    int rain_probability;
    pet_weather_condition_t condition;
    int64_t updated_epoch;
} pet_weather_command_t;

typedef struct {
    int64_t latest_session_tokens;
    int64_t today_tokens;
    int64_t today_cached_input_tokens;
    int64_t today_input_tokens;
    int64_t updated_epoch;
} pet_usage_command_t;

typedef struct {
    pet_command_type_t type;
    union {
        pet_lifecycle_t state;
        pet_clock_command_t clock;
        pet_weather_command_t weather;
        pet_usage_command_t usage;
    } data;
} pet_command_t;

pet_protocol_result_t pet_protocol_parse(const char *line, pet_command_t *command);
const char *pet_protocol_result_name(pet_protocol_result_t result);
const char *pet_lifecycle_name(pet_lifecycle_t state);
const char *pet_weather_condition_name(pet_weather_condition_t condition);
const char *pet_weather_condition_label(pet_weather_condition_t condition);
bool pet_weather_condition_is_critical(pet_weather_condition_t condition);
