#include "pet_wireless.h"

#include <string.h>

static size_t bounded_length(const char *value, size_t maximum)
{
    if (value == NULL) {
        return 0U;
    }

    size_t length = 0U;
    while (length <= maximum && value[length] != '\0') {
        ++length;
    }
    return length;
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

bool pet_wireless_deadline_expired(int64_t now_us, int64_t deadline_us)
{
    return deadline_us > 0 && now_us >= deadline_us;
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
    if (snapshot == NULL || access_point == NULL) {
        return;
    }

    const size_t access_point_ssid_length =
        bounded_length(access_point->ssid, PET_WIRELESS_MAX_SSID_LEN);
    if (access_point_ssid_length == 0U ||
        access_point_ssid_length > PET_WIRELESS_MAX_SSID_LEN) {
        return;
    }

    size_t count = snapshot->scan_result_count;
    if (count > PET_WIRELESS_MAX_SCAN_RESULTS) {
        count = PET_WIRELESS_MAX_SCAN_RESULTS;
    }

    for (size_t index = 0; index < count; ++index) {
        const size_t existing_ssid_length =
            bounded_length(snapshot->scan_results[index].ssid, PET_WIRELESS_MAX_SSID_LEN);
        const bool same_ssid = existing_ssid_length == access_point_ssid_length &&
                               memcmp(snapshot->scan_results[index].ssid,
                                      access_point->ssid,
                                      access_point_ssid_length) == 0;
        if (same_ssid) {
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
