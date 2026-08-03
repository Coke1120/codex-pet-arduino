#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "pet_protocol.h"

static pet_command_t parse_ok(const char *line)
{
    pet_command_t command;
    assert(pet_protocol_parse(line, &command) == PET_PROTOCOL_OK);
    return command;
}

int main(void)
{
    pet_command_t command = parse_ok(" REVIEW \r\n");
    assert(command.type == PET_COMMAND_STATE);
    assert(command.data.state == PET_LIFECYCLE_REVIEW);
    assert(strcmp(pet_lifecycle_name(command.data.state), "REVIEW") == 0);

    command = parse_ok("capabilities");
    assert(command.type == PET_COMMAND_CAPABILITIES);

    command = parse_ok("clock 1785782520 28800");
    assert(command.type == PET_COMMAND_CLOCK);
    assert(command.data.clock.unix_epoch == 1785782520LL);
    assert(command.data.clock.utc_offset_seconds == 28800);

    command = parse_ok("weather 29.5 27 32.0 82 rain 1785782400");
    assert(command.type == PET_COMMAND_WEATHER);
    assert(command.data.weather.current_temperature_tenths == 295);
    assert(command.data.weather.low_temperature_tenths == 270);
    assert(command.data.weather.high_temperature_tenths == 320);
    assert(command.data.weather.rain_probability == 82);
    assert(command.data.weather.condition == PET_WEATHER_RAIN);
    assert(command.data.weather.updated_epoch == 1785782400LL);

    assert(pet_protocol_parse("", &command) == PET_PROTOCOL_EMPTY);
    assert(pet_protocol_parse("sleeping", &command) == PET_PROTOCOL_UNKNOWN);
    assert(pet_protocol_parse("clock 1", &command) == PET_PROTOCOL_INVALID_FORMAT);
    assert(pet_protocol_parse("clock 1 999999", &command) == PET_PROTOCOL_OUT_OF_RANGE);
    assert(pet_protocol_parse("clock 253402250400 0", &command) == PET_PROTOCOL_OUT_OF_RANGE);
    assert(pet_protocol_parse("weather 29 33 27 82 rain 1", &command) == PET_PROTOCOL_OUT_OF_RANGE);
    assert(pet_protocol_parse("weather 29 27 32 101 rain 1", &command) == PET_PROTOCOL_OUT_OF_RANGE);
    assert(pet_protocol_parse("weather 29.55 27 32 82 rain 1", &command) == PET_PROTOCOL_OUT_OF_RANGE);
    assert(pet_protocol_parse("weather 29 27 32 82 hail 1", &command) == PET_PROTOCOL_OUT_OF_RANGE);
    assert(pet_protocol_parse("weather 29 27 32 82 rain 9223372036854775807", &command) == PET_PROTOCOL_OUT_OF_RANGE);
    assert(pet_protocol_parse("status extra", &command) == PET_PROTOCOL_INVALID_FORMAT);

    assert(strcmp(pet_weather_condition_label(PET_WEATHER_PARTLY_CLOUDY), "Partly cloudy") == 0);
    assert(pet_weather_condition_is_critical(PET_WEATHER_THUNDER));
    assert(!pet_weather_condition_is_critical(PET_WEATHER_RAIN));

    puts("pet_protocol tests passed");
    return 0;
}
