#include "pet_protocol.h"

#include <ctype.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>

#define MAX_TOKENS 8
#define MIN_TEMPERATURE_TENTHS (-1000)
#define MAX_TEMPERATURE_TENTHS 1000
#define MAX_UTC_OFFSET_SECONDS (14 * 60 * 60)

static size_t normalise_and_tokenise(const char *line, char *buffer, char **tokens)
{
    size_t length = strlen(line);
    if (length >= PET_PROTOCOL_LINE_CAPACITY) return SIZE_MAX;

    memcpy(buffer, line, length + 1);
    for (size_t index = 0; index < length; ++index) {
        buffer[index] = (char)tolower((unsigned char)buffer[index]);
    }

    size_t count = 0;
    char *cursor = buffer;
    while (*cursor != '\0') {
        while (isspace((unsigned char)*cursor)) ++cursor;
        if (*cursor == '\0') break;
        if (count == MAX_TOKENS) return SIZE_MAX;
        tokens[count++] = cursor;
        while (*cursor != '\0' && !isspace((unsigned char)*cursor)) ++cursor;
        if (*cursor != '\0') *cursor++ = '\0';
    }
    return count;
}

static bool parse_i64(const char *token, int64_t minimum, int64_t maximum, int64_t *value)
{
    errno = 0;
    char *end = NULL;
    long long parsed = strtoll(token, &end, 10);
    if (errno == ERANGE || end == token || *end != '\0') return false;
    if (parsed < minimum || parsed > maximum) return false;
    *value = (int64_t)parsed;
    return true;
}

static bool parse_int(const char *token, int minimum, int maximum, int *value)
{
    int64_t parsed;
    if (!parse_i64(token, minimum, maximum, &parsed)) return false;
    *value = (int)parsed;
    return true;
}

static bool parse_temperature_tenths(const char *token, int *value)
{
    bool negative = false;
    if (*token == '-' || *token == '+') {
        negative = *token == '-';
        ++token;
    }
    if (!isdigit((unsigned char)*token)) return false;

    int whole = 0;
    while (isdigit((unsigned char)*token)) {
        if (whole > 100) return false;
        whole = whole * 10 + (*token++ - '0');
    }

    int fraction = 0;
    if (*token == '.') {
        ++token;
        if (!isdigit((unsigned char)*token)) return false;
        fraction = *token++ - '0';
        while (*token == '0') ++token;
    }
    if (*token != '\0') return false;

    int parsed = whole * 10 + fraction;
    if (negative) parsed = -parsed;
    if (parsed < MIN_TEMPERATURE_TENTHS || parsed > MAX_TEMPERATURE_TENTHS) return false;
    *value = parsed;
    return true;
}

static bool parse_condition(const char *token, pet_weather_condition_t *condition)
{
    static const struct {
        const char *name;
        pet_weather_condition_t value;
    } conditions[] = {
        {"clear", PET_WEATHER_CLEAR},
        {"partly_cloudy", PET_WEATHER_PARTLY_CLOUDY},
        {"cloudy", PET_WEATHER_CLOUDY},
        {"fog", PET_WEATHER_FOG},
        {"rain", PET_WEATHER_RAIN},
        {"snow", PET_WEATHER_SNOW},
        {"thunder", PET_WEATHER_THUNDER},
        {"unknown", PET_WEATHER_UNKNOWN},
    };

    for (size_t index = 0; index < sizeof(conditions) / sizeof(conditions[0]); ++index) {
        if (strcmp(token, conditions[index].name) == 0) {
            *condition = conditions[index].value;
            return true;
        }
    }
    return false;
}

pet_protocol_result_t pet_protocol_parse(const char *line, pet_command_t *command)
{
    if (line == NULL || command == NULL) return PET_PROTOCOL_INVALID_FORMAT;
    memset(command, 0, sizeof(*command));

    char buffer[PET_PROTOCOL_LINE_CAPACITY];
    char *tokens[MAX_TOKENS];
    size_t count = normalise_and_tokenise(line, buffer, tokens);
    if (count == SIZE_MAX) return PET_PROTOCOL_INVALID_FORMAT;
    if (count == 0) return PET_PROTOCOL_EMPTY;

    if (count == 1) {
        if (strcmp(tokens[0], "idle") == 0) {
            command->type = PET_COMMAND_STATE;
            command->data.state = PET_LIFECYCLE_IDLE;
            return PET_PROTOCOL_OK;
        }
        if (strcmp(tokens[0], "running") == 0) {
            command->type = PET_COMMAND_STATE;
            command->data.state = PET_LIFECYCLE_RUNNING;
            return PET_PROTOCOL_OK;
        }
        if (strcmp(tokens[0], "waiting") == 0) {
            command->type = PET_COMMAND_STATE;
            command->data.state = PET_LIFECYCLE_WAITING;
            return PET_PROTOCOL_OK;
        }
        if (strcmp(tokens[0], "review") == 0) {
            command->type = PET_COMMAND_STATE;
            command->data.state = PET_LIFECYCLE_REVIEW;
            return PET_PROTOCOL_OK;
        }
        if (strcmp(tokens[0], "ping") == 0) {
            command->type = PET_COMMAND_PING;
            return PET_PROTOCOL_OK;
        }
        if (strcmp(tokens[0], "status") == 0) {
            command->type = PET_COMMAND_STATUS;
            return PET_PROTOCOL_OK;
        }
        if (strcmp(tokens[0], "capabilities") == 0) {
            command->type = PET_COMMAND_CAPABILITIES;
            return PET_PROTOCOL_OK;
        }
    }

    if (strcmp(tokens[0], "clock") == 0) {
        if (count != 3) return PET_PROTOCOL_INVALID_FORMAT;
        int64_t offset;
        if (!parse_i64(tokens[1], 0, PET_MAX_UNIX_EPOCH,
                       &command->data.clock.unix_epoch) ||
            !parse_i64(tokens[2], -MAX_UTC_OFFSET_SECONDS, MAX_UTC_OFFSET_SECONDS, &offset)) {
            return PET_PROTOCOL_OUT_OF_RANGE;
        }
        command->data.clock.utc_offset_seconds = (int32_t)offset;
        command->type = PET_COMMAND_CLOCK;
        return PET_PROTOCOL_OK;
    }

    if (strcmp(tokens[0], "weather") == 0) {
        if (count != 7) return PET_PROTOCOL_INVALID_FORMAT;
        pet_weather_command_t *weather = &command->data.weather;
        if (!parse_temperature_tenths(tokens[1], &weather->current_temperature_tenths) ||
            !parse_temperature_tenths(tokens[2], &weather->low_temperature_tenths) ||
            !parse_temperature_tenths(tokens[3], &weather->high_temperature_tenths) ||
            !parse_int(tokens[4], 0, 100, &weather->rain_probability) ||
            !parse_condition(tokens[5], &weather->condition) ||
            !parse_i64(tokens[6], 0, PET_MAX_UNIX_EPOCH,
                       &weather->updated_epoch)) {
            return PET_PROTOCOL_OUT_OF_RANGE;
        }
        if (weather->low_temperature_tenths > weather->high_temperature_tenths) {
            return PET_PROTOCOL_OUT_OF_RANGE;
        }
        command->type = PET_COMMAND_WEATHER;
        return PET_PROTOCOL_OK;
    }

    if (strcmp(tokens[0], "usage") == 0) {
        if (count != 6) return PET_PROTOCOL_INVALID_FORMAT;
        pet_usage_command_t *usage = &command->data.usage;
        if (!parse_i64(tokens[1], 0, INT64_MAX, &usage->latest_session_tokens) ||
            !parse_i64(tokens[2], 0, INT64_MAX, &usage->today_tokens) ||
            !parse_i64(tokens[3], 0, INT64_MAX, &usage->today_cached_input_tokens) ||
            !parse_i64(tokens[4], 0, INT64_MAX, &usage->today_input_tokens) ||
            !parse_i64(tokens[5], 0, PET_MAX_UNIX_EPOCH, &usage->updated_epoch)) {
            return PET_PROTOCOL_OUT_OF_RANGE;
        }
        if (usage->today_cached_input_tokens > usage->today_input_tokens) {
            return PET_PROTOCOL_OUT_OF_RANGE;
        }
        command->type = PET_COMMAND_USAGE;
        return PET_PROTOCOL_OK;
    }

    if (strcmp(tokens[0], "quota") == 0) {
        if (count != 7) return PET_PROTOCOL_INVALID_FORMAT;
        pet_quota_command_t *quota = &command->data.quota;
        if (!parse_int(tokens[1], -1, 100, &quota->session_remaining_percent) ||
            !parse_i64(tokens[2], 0, PET_MAX_UNIX_EPOCH,
                       &quota->session_reset_epoch) ||
            !parse_int(tokens[3], -1, 100, &quota->weekly_remaining_percent) ||
            !parse_i64(tokens[4], 0, PET_MAX_UNIX_EPOCH,
                       &quota->weekly_reset_epoch) ||
            !parse_i64(tokens[5], -1, INT64_MAX,
                       &quota->credits_remaining_tenths) ||
            !parse_i64(tokens[6], 0, PET_MAX_UNIX_EPOCH,
                       &quota->updated_epoch)) {
            return PET_PROTOCOL_OUT_OF_RANGE;
        }
        if ((quota->session_remaining_percent < 0 && quota->session_reset_epoch != 0) ||
            (quota->weekly_remaining_percent < 0 && quota->weekly_reset_epoch != 0)) {
            return PET_PROTOCOL_OUT_OF_RANGE;
        }
        command->type = PET_COMMAND_QUOTA;
        return PET_PROTOCOL_OK;
    }

    if (count == 1) return PET_PROTOCOL_UNKNOWN;
    return PET_PROTOCOL_INVALID_FORMAT;
}

const char *pet_protocol_result_name(pet_protocol_result_t result)
{
    switch (result) {
    case PET_PROTOCOL_EMPTY: return "empty command";
    case PET_PROTOCOL_UNKNOWN: return "unknown command";
    case PET_PROTOCOL_INVALID_FORMAT: return "invalid format";
    case PET_PROTOCOL_OUT_OF_RANGE: return "value out of range";
    default: return "ok";
    }
}

const char *pet_lifecycle_name(pet_lifecycle_t state)
{
    switch (state) {
    case PET_LIFECYCLE_RUNNING: return "RUNNING";
    case PET_LIFECYCLE_WAITING: return "WAITING";
    case PET_LIFECYCLE_REVIEW: return "REVIEW";
    default: return "IDLE";
    }
}

const char *pet_weather_condition_name(pet_weather_condition_t condition)
{
    switch (condition) {
    case PET_WEATHER_CLEAR: return "clear";
    case PET_WEATHER_PARTLY_CLOUDY: return "partly_cloudy";
    case PET_WEATHER_CLOUDY: return "cloudy";
    case PET_WEATHER_FOG: return "fog";
    case PET_WEATHER_RAIN: return "rain";
    case PET_WEATHER_SNOW: return "snow";
    case PET_WEATHER_THUNDER: return "thunder";
    default: return "unknown";
    }
}

const char *pet_weather_condition_label(pet_weather_condition_t condition)
{
    switch (condition) {
    case PET_WEATHER_CLEAR: return "Clear";
    case PET_WEATHER_PARTLY_CLOUDY: return "Partly cloudy";
    case PET_WEATHER_CLOUDY: return "Cloudy";
    case PET_WEATHER_FOG: return "Foggy";
    case PET_WEATHER_RAIN: return "Rain later";
    case PET_WEATHER_SNOW: return "Wintry weather";
    case PET_WEATHER_THUNDER: return "Thunderstorms";
    default: return "Weather unavailable";
    }
}

bool pet_weather_condition_is_critical(pet_weather_condition_t condition)
{
    return condition == PET_WEATHER_THUNDER;
}
