#ifndef PET_WIRELESS_H
#define PET_WIRELESS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PET_WIRELESS_MAX_SSID_LEN 32U
#define PET_WIRELESS_MAX_SCAN_RESULTS 8U
#define PET_WIRELESS_DEVICE_NAME "Codex Pet"

typedef enum {
    PET_WIRELESS_BACKEND_STOPPED = 0,
    PET_WIRELESS_BACKEND_STARTING,
    PET_WIRELESS_BACKEND_READY,
    PET_WIRELESS_BACKEND_ERROR,
} pet_wireless_backend_state_t;

typedef enum {
    PET_WIRELESS_WIFI_DISABLED = 0,
    PET_WIRELESS_WIFI_IDLE,
    PET_WIRELESS_WIFI_SCANNING,
    PET_WIRELESS_WIFI_CONNECTING,
    PET_WIRELESS_WIFI_CONNECTED,
    PET_WIRELESS_WIFI_ERROR,
} pet_wireless_wifi_state_t;

typedef enum {
    PET_WIRELESS_BLE_DISABLED = 0,
    PET_WIRELESS_BLE_STARTING,
    PET_WIRELESS_BLE_IDLE,
    PET_WIRELESS_BLE_ADVERTISING,
    PET_WIRELESS_BLE_ERROR,
} pet_wireless_ble_state_t;

typedef enum {
    PET_WIRELESS_OK = 0,
    PET_WIRELESS_INVALID_ARGUMENT,
    PET_WIRELESS_INVALID_STATE,
    PET_WIRELESS_BUSY,
    PET_WIRELESS_NO_MEMORY,
    PET_WIRELESS_BACKEND_FAILURE,
} pet_wireless_result_t;

typedef struct {
    char ssid[PET_WIRELESS_MAX_SSID_LEN + 1U];
    int8_t rssi;
    bool open;
} pet_wireless_access_point_t;

typedef struct {
    pet_wireless_backend_state_t backend;
    pet_wireless_wifi_state_t wifi;
    pet_wireless_ble_state_t ble;
    char ssid[PET_WIRELESS_MAX_SSID_LEN + 1U];
    int8_t rssi;
    pet_wireless_access_point_t scan_results[PET_WIRELESS_MAX_SCAN_RESULTS];
    size_t scan_result_count;
    int32_t last_error;
} pet_wireless_snapshot_t;

/* Starts the radio manager task and returns without waiting for the C6. */
pet_wireless_result_t pet_wireless_start(void);

/* Copies a coherent, password-free snapshot suitable for LVGL polling. */
bool pet_wireless_get_snapshot(pet_wireless_snapshot_t *snapshot);

pet_wireless_result_t pet_wireless_wifi_set_enabled(bool enabled);
pet_wireless_result_t pet_wireless_wifi_scan(void);
pet_wireless_result_t pet_wireless_wifi_connect(const char *ssid, const char *password);
pet_wireless_result_t pet_wireless_wifi_forget(void);
pet_wireless_result_t pet_wireless_ble_set_advertising(bool enabled);

/* Pure helpers used by the firmware and host tests. */
bool pet_wireless_credentials_valid(const char *ssid, const char *password);
void pet_wireless_scan_reset(pet_wireless_snapshot_t *snapshot);
void pet_wireless_scan_add(pet_wireless_snapshot_t *snapshot,
                           const pet_wireless_access_point_t *access_point);

#ifdef __cplusplus
}
#endif

#endif
