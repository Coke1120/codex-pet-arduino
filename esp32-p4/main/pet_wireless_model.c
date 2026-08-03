#include "pet_wireless.h"

#include <string.h>

static size_t bounded_length(const char *value, size_t maximum)
{
    return value == NULL ? 0U : strnlen(value, maximum + 1U);
}

bool pet_wireless_credentials_valid(const char *ssid, const char *password)
{
    const size_t ssid_length = bounded_length(ssid, PET_WIRELESS_MAX_SSID_LEN);
    const size_t password_length = bounded_length(password, 63U);

    if (ssid_length == 0U || ssid_length > PET_WIRELESS_MAX_SSID_LEN || password == NULL) {
        return false;
    }
    return password_length == 0U || (password_length >= 8U && password_length <= 63U);
}

void pet_wireless_scan_reset(pet_wireless_snapshot_t *snapshot)
{
    if (snapshot == NULL) {
        return;
    }
    memset(snapshot->scan_results, 0, sizeof(snapshot->scan_results));
    snapshot->scan_result_count = 0U;
}

void pet_wireless_scan_add(pet_wireless_snapshot_t *snapshot,
                           const pet_wireless_access_point_t *access_point)
{
    if (snapshot == NULL || access_point == NULL || access_point->ssid[0] == '\0') {
        return;
    }

    size_t count = snapshot->scan_result_count;
    if (count > PET_WIRELESS_MAX_SCAN_RESULTS) {
        count = PET_WIRELESS_MAX_SCAN_RESULTS;
    }

    for (size_t index = 0; index < count; ++index) {
        if (strcmp(snapshot->scan_results[index].ssid, access_point->ssid) == 0) {
            if (access_point->rssi <= snapshot->scan_results[index].rssi) {
                return;
            }
            for (size_t move = index; move + 1U < count; ++move) {
                snapshot->scan_results[move] = snapshot->scan_results[move + 1U];
            }
            --count;
            break;
        }
    }

    size_t insertion = 0U;
    while (insertion < count && snapshot->scan_results[insertion].rssi >= access_point->rssi) {
        ++insertion;
    }
    if (insertion >= PET_WIRELESS_MAX_SCAN_RESULTS) {
        snapshot->scan_result_count = count;
        return;
    }

    const size_t new_count = count < PET_WIRELESS_MAX_SCAN_RESULTS ? count + 1U : count;
    for (size_t move = new_count; move > insertion + 1U; --move) {
        snapshot->scan_results[move - 1U] = snapshot->scan_results[move - 2U];
    }
    snapshot->scan_results[insertion] = *access_point;
    snapshot->scan_results[insertion].ssid[PET_WIRELESS_MAX_SSID_LEN] = '\0';
    snapshot->scan_result_count = new_count;
}
