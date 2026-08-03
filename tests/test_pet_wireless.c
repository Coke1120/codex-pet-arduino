#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "pet_wireless.h"

static pet_wireless_access_point_t ap(const char *ssid, int8_t rssi, bool open)
{
    pet_wireless_access_point_t result = {.rssi = rssi, .open = open};
    snprintf(result.ssid, sizeof(result.ssid), "%s", ssid);
    return result;
}

int main(void)
{
    assert(!pet_wireless_credentials_valid(NULL, "12345678"));
    assert(!pet_wireless_credentials_valid("", "12345678"));
    assert(pet_wireless_credentials_valid("a", ""));
    assert(pet_wireless_credentials_valid("12345678901234567890123456789012", "12345678"));
    assert(!pet_wireless_credentials_valid("123456789012345678901234567890123", "12345678"));
    assert(!pet_wireless_credentials_valid("Codex", "1234567"));
    assert(pet_wireless_credentials_valid("Codex", "12345678"));
    assert(pet_wireless_credentials_valid("Codex", "123456789012345678901234567890123456789012345678901234567890123"));
    assert(!pet_wireless_credentials_valid("Codex", "1234567890123456789012345678901234567890123456789012345678901234"));

    pet_wireless_snapshot_t snapshot = {0};
    const pet_wireless_access_point_t weak = ap("weak", -80, true);
    const pet_wireless_access_point_t strong = ap("strong", -20, false);
    const pet_wireless_access_point_t duplicate_weak = ap("strong", -70, true);
    const pet_wireless_access_point_t duplicate_strong = ap("weak", -10, false);
    pet_wireless_scan_add(&snapshot, &weak);
    pet_wireless_scan_add(&snapshot, &strong);
    pet_wireless_scan_add(&snapshot, &duplicate_weak);
    pet_wireless_scan_add(&snapshot, &duplicate_strong);
    assert(snapshot.scan_result_count == 2U);
    assert(strcmp(snapshot.scan_results[0].ssid, "weak") == 0);
    assert(snapshot.scan_results[0].rssi == -10);
    assert(!snapshot.scan_results[0].open);
    assert(strcmp(snapshot.scan_results[1].ssid, "strong") == 0);
    assert(snapshot.scan_results[1].rssi == -20);

    for (int index = 0; index < 12; ++index) {
        char ssid[8];
        snprintf(ssid, sizeof(ssid), "ap-%02d", index);
        const pet_wireless_access_point_t candidate = ap(ssid, (int8_t)(-30 - index), true);
        pet_wireless_scan_add(&snapshot, &candidate);
    }
    assert(snapshot.scan_result_count == PET_WIRELESS_MAX_SCAN_RESULTS);
    assert(snapshot.scan_results[0].rssi == -10);
    assert(snapshot.scan_results[PET_WIRELESS_MAX_SCAN_RESULTS - 1U].rssi == -35);

    pet_wireless_scan_reset(&snapshot);
    assert(snapshot.scan_result_count == 0U);
    puts("pet_wireless tests passed");
    return 0;
}
