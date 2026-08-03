#include "pet_wireless.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_event.h"
#include "esp_hosted.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"

#define PET_WIRELESS_TASK_STACK 6144U
#define PET_WIRELESS_TASK_PRIORITY 5U
#define PET_WIRELESS_SCAN_FETCH_LIMIT 32U
#define PET_WIRELESS_RSSI_REFRESH_MS 3000U

typedef enum {
    COMMAND_WIFI_ENABLE,
    COMMAND_WIFI_DISABLE,
    COMMAND_WIFI_SCAN,
    COMMAND_WIFI_SCAN_DONE,
    COMMAND_WIFI_CONNECT,
    COMMAND_WIFI_FORGET,
    COMMAND_BLE_ADVERTISE,
    COMMAND_BLE_STOP_ADVERTISING,
} command_type_t;

typedef struct {
    char ssid[PET_WIRELESS_MAX_SSID_LEN + 1U];
    char password[64U];
} connect_request_t;

typedef struct {
    command_type_t type;
    connect_request_t *connect_request;
} command_t;

static portMUX_TYPE s_start_lock = portMUX_INITIALIZER_UNLOCKED;
static SemaphoreHandle_t s_snapshot_lock;
static SemaphoreHandle_t s_ble_operation_lock;
static QueueHandle_t s_command_queue;
static pet_wireless_snapshot_t s_snapshot;
static bool s_started;
static bool s_wifi_enabled;
static bool s_wifi_toggle_pending;
static bool s_wifi_forget_pending;
static pet_wireless_wifi_state_t s_scan_previous_state;
static bool s_ble_synced;
static bool s_ble_advertising_requested;
static bool s_ble_command_pending;
static uint8_t s_ble_address_type;

static void secure_zero(void *value, size_t size)
{
    volatile uint8_t *bytes = value;
    while (size-- > 0U) {
        *bytes++ = 0U;
    }
}

static void snapshot_set_error(int32_t error)
{
    xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
    s_snapshot.last_error = error;
    xSemaphoreGive(s_snapshot_lock);
}

static pet_wireless_result_t enqueue(command_type_t type, connect_request_t *request)
{
    if (s_command_queue == NULL) {
        return PET_WIRELESS_INVALID_STATE;
    }
    const command_t command = {.type = type, .connect_request = request};
    return xQueueSend(s_command_queue, &command, 0U) == pdTRUE ? PET_WIRELESS_OK
                                                               : PET_WIRELESS_BUSY;
}

static bool backend_ready(void)
{
    bool ready;
    if (s_snapshot_lock == NULL) {
        return false;
    }
    if (xSemaphoreTake(s_snapshot_lock, 0U) != pdTRUE) {
        return false;
    }
    ready = s_snapshot.backend == PET_WIRELESS_BACKEND_READY;
    xSemaphoreGive(s_snapshot_lock);
    return ready;
}

static int ble_gap_event(struct ble_gap_event *event, void *argument);

static bool ble_advertising_requested(void)
{
    xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
    bool requested = s_ble_advertising_requested;
    xSemaphoreGive(s_snapshot_lock);
    return requested;
}

static int ble_start_advertising(void)
{
    xSemaphoreTake(s_ble_operation_lock, portMAX_DELAY);
    xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
    bool should_advertise = s_ble_synced && s_ble_advertising_requested;
    xSemaphoreGive(s_snapshot_lock);
    if (!should_advertise || ble_gap_adv_active()) {
        xSemaphoreGive(s_ble_operation_lock);
        return 0;
    }

    struct ble_hs_adv_fields fields = {0};
    const char *name = ble_svc_gap_device_name();
    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    fields.name = (uint8_t *)name;
    fields.name_len = strlen(name);
    fields.name_is_complete = 1U;
    int result = ble_gap_adv_set_fields(&fields);
    if (result != 0) {
        xSemaphoreGive(s_ble_operation_lock);
        return result;
    }

    struct ble_gap_adv_params parameters = {0};
    parameters.conn_mode = BLE_GAP_CONN_MODE_UND;
    parameters.disc_mode = BLE_GAP_DISC_MODE_GEN;
    result = ble_gap_adv_start(s_ble_address_type, NULL, BLE_HS_FOREVER, &parameters,
                               ble_gap_event, NULL);
    xSemaphoreGive(s_ble_operation_lock);
    return result;
}

static void ble_update_advertising_state(void)
{
    const int result = ble_start_advertising();
    xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
    if (result == 0) {
        s_snapshot.ble = s_ble_advertising_requested && ble_gap_adv_active()
            ? PET_WIRELESS_BLE_ADVERTISING : PET_WIRELESS_BLE_IDLE;
    } else {
        s_snapshot.ble = PET_WIRELESS_BLE_ERROR;
        s_snapshot.last_error = result;
    }
    xSemaphoreGive(s_snapshot_lock);
}

static int ble_gap_event(struct ble_gap_event *event, void *argument)
{
    (void)argument;
    switch (event->type) {
        case BLE_GAP_EVENT_CONNECT:
            xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
            s_snapshot.ble = event->connect.status == 0 ? PET_WIRELESS_BLE_IDLE
                                                        : PET_WIRELESS_BLE_ERROR;
            xSemaphoreGive(s_snapshot_lock);
            if (event->connect.status != 0 && ble_advertising_requested()) {
                ble_update_advertising_state();
            }
            break;
        case BLE_GAP_EVENT_DISCONNECT:
        case BLE_GAP_EVENT_ADV_COMPLETE:
            if (ble_advertising_requested()) {
                ble_update_advertising_state();
            }
            break;
        default:
            break;
    }
    return 0;
}

static void ble_on_reset(int reason)
{
    xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
    s_ble_synced = false;
    s_snapshot.ble = PET_WIRELESS_BLE_ERROR;
    s_snapshot.last_error = reason;
    xSemaphoreGive(s_snapshot_lock);
}

static void ble_on_sync(void)
{
    int result = ble_hs_util_ensure_addr(0);
    if (result == 0) {
        result = ble_hs_id_infer_auto(0, &s_ble_address_type);
    }

    xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
    s_ble_synced = result == 0;
    s_snapshot.ble = result == 0 ? PET_WIRELESS_BLE_IDLE : PET_WIRELESS_BLE_ERROR;
    if (result != 0) {
        s_snapshot.last_error = result;
    }
    const bool advertise = s_ble_advertising_requested;
    xSemaphoreGive(s_snapshot_lock);

    if (result == 0 && advertise) {
        ble_update_advertising_state();
    }
}

static void ble_host_task(void *argument)
{
    (void)argument;
    nimble_port_run();
    nimble_port_freertos_deinit();
}

static void initialize_ble(void)
{
    xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
    s_snapshot.ble = PET_WIRELESS_BLE_STARTING;
    xSemaphoreGive(s_snapshot_lock);

    esp_err_t result = esp_hosted_bt_controller_init();
    if (result == ESP_OK) {
        result = esp_hosted_bt_controller_enable();
    }
    if (result == ESP_OK) {
        result = nimble_port_init();
    }
    if (result != ESP_OK) {
        xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
        s_snapshot.ble = PET_WIRELESS_BLE_ERROR;
        s_snapshot.last_error = result;
        xSemaphoreGive(s_snapshot_lock);
        return;
    }

    ble_hs_cfg.reset_cb = ble_on_reset;
    ble_hs_cfg.sync_cb = ble_on_sync;
    ble_svc_gap_init();
    ble_svc_gatt_init();
    const int name_result = ble_svc_gap_device_name_set(PET_WIRELESS_DEVICE_NAME);
    if (name_result != 0) {
        xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
        s_snapshot.ble = PET_WIRELESS_BLE_ERROR;
        s_snapshot.last_error = name_result;
        xSemaphoreGive(s_snapshot_lock);
        return;
    }
    nimble_port_freertos_init(ble_host_task);
}

static void wifi_event_handler(void *argument, esp_event_base_t event_base, int32_t event_id,
                               void *event_data)
{
    (void)argument;
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_SCAN_DONE) {
        if (enqueue(COMMAND_WIFI_SCAN_DONE, NULL) != PET_WIRELESS_OK) {
            xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
            s_snapshot.wifi = PET_WIRELESS_WIFI_ERROR;
            s_snapshot.last_error = ESP_ERR_TIMEOUT;
            xSemaphoreGive(s_snapshot_lock);
        }
        return;
    }

    xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_CONNECTED) {
        s_snapshot.wifi = PET_WIRELESS_WIFI_CONNECTED;
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        bool connection_failed = s_snapshot.wifi == PET_WIRELESS_WIFI_CONNECTING;
        s_snapshot.wifi = !s_wifi_enabled ? PET_WIRELESS_WIFI_DISABLED
                            : connection_failed ? PET_WIRELESS_WIFI_ERROR
                                                : PET_WIRELESS_WIFI_IDLE;
        if (connection_failed && event_data != NULL) {
            const wifi_event_sta_disconnected_t *disconnected = event_data;
            s_snapshot.last_error = disconnected->reason;
        }
        s_snapshot.rssi = 0;
    }
    xSemaphoreGive(s_snapshot_lock);
}

static esp_err_t initialize_wifi(void)
{
    esp_err_t result = esp_netif_init();
    if (result != ESP_OK && result != ESP_ERR_INVALID_STATE) {
        return result;
    }
    result = esp_event_loop_create_default();
    if (result != ESP_OK && result != ESP_ERR_INVALID_STATE) {
        return result;
    }
    result = esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event_handler, NULL);
    if (result != ESP_OK) {
        return result;
    }
    if (esp_netif_create_default_wifi_sta() == NULL) {
        return ESP_ERR_NO_MEM;
    }

    wifi_init_config_t configuration = WIFI_INIT_CONFIG_DEFAULT();
    result = esp_wifi_init(&configuration);
    if (result == ESP_OK) {
        result = esp_wifi_set_storage(WIFI_STORAGE_FLASH);
    }
    if (result == ESP_OK) {
        result = esp_wifi_set_mode(WIFI_MODE_STA);
    }
    return result;
}

static void fetch_scan_results(void)
{
    uint16_t count = 0U;
    esp_err_t result = esp_wifi_scan_get_ap_num(&count);
    if (result != ESP_OK) {
        xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
        s_snapshot.wifi = PET_WIRELESS_WIFI_ERROR;
        s_snapshot.last_error = result;
        xSemaphoreGive(s_snapshot_lock);
        return;
    }
    if (count > PET_WIRELESS_SCAN_FETCH_LIMIT) {
        count = PET_WIRELESS_SCAN_FETCH_LIMIT;
    }

    wifi_ap_record_t *records = count == 0U ? NULL : calloc(count, sizeof(*records));
    if (count != 0U && records == NULL) {
        xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
        s_snapshot.wifi = PET_WIRELESS_WIFI_ERROR;
        s_snapshot.last_error = ESP_ERR_NO_MEM;
        xSemaphoreGive(s_snapshot_lock);
        return;
    }
    result = count == 0U ? ESP_OK : esp_wifi_scan_get_ap_records(&count, records);

    pet_wireless_snapshot_t model = {0};
    if (result == ESP_OK) {
        for (uint16_t index = 0U; index < count; ++index) {
            pet_wireless_access_point_t access_point = {
                .rssi = records[index].rssi,
                .open = records[index].authmode == WIFI_AUTH_OPEN,
            };
            const size_t ssid_length = strnlen((const char *)records[index].ssid,
                                               PET_WIRELESS_MAX_SSID_LEN);
            memcpy(access_point.ssid, records[index].ssid, ssid_length);
            access_point.ssid[ssid_length] = '\0';
            pet_wireless_scan_add(&model, &access_point);
        }
    }
    free(records);

    xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
    if (result == ESP_OK) {
        memcpy(s_snapshot.scan_results, model.scan_results, sizeof(model.scan_results));
        s_snapshot.scan_result_count = model.scan_result_count;
        s_snapshot.wifi = s_scan_previous_state == PET_WIRELESS_WIFI_CONNECTED
                              ? PET_WIRELESS_WIFI_CONNECTED
                              : PET_WIRELESS_WIFI_IDLE;
    } else {
        s_snapshot.wifi = PET_WIRELESS_WIFI_ERROR;
        s_snapshot.last_error = result;
    }
    xSemaphoreGive(s_snapshot_lock);
}

static void refresh_connection(void)
{
    xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
    const bool connected = s_snapshot.wifi == PET_WIRELESS_WIFI_CONNECTED;
    xSemaphoreGive(s_snapshot_lock);
    if (!connected) {
        return;
    }

    wifi_ap_record_t record = {0};
    if (esp_wifi_sta_get_ap_info(&record) != ESP_OK) {
        return;
    }
    xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
    const size_t ssid_length = strnlen((const char *)record.ssid, PET_WIRELESS_MAX_SSID_LEN);
    memcpy(s_snapshot.ssid, record.ssid, ssid_length);
    s_snapshot.ssid[ssid_length] = '\0';
    s_snapshot.rssi = record.rssi;
    xSemaphoreGive(s_snapshot_lock);
}

static void handle_connect(connect_request_t *request)
{
    wifi_config_t configuration = {0};
    const size_t ssid_length = strnlen(request->ssid, PET_WIRELESS_MAX_SSID_LEN);
    const size_t password_length = strnlen(request->password, sizeof(request->password) - 1U);
    memcpy(configuration.sta.ssid, request->ssid, ssid_length);
    memcpy(configuration.sta.password, request->password, password_length);
    configuration.sta.threshold.authmode = password_length == 0U ? WIFI_AUTH_OPEN
                                                                  : WIFI_AUTH_WPA_PSK;

    esp_err_t result = esp_wifi_set_config(WIFI_IF_STA, &configuration);
    secure_zero(&configuration, sizeof(configuration));
    secure_zero(request, sizeof(*request));
    free(request);
    if (result == ESP_OK) {
        result = esp_wifi_connect();
    }

    xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
    if (result != ESP_OK) {
        s_snapshot.wifi = PET_WIRELESS_WIFI_ERROR;
        s_snapshot.last_error = result;
    }
    xSemaphoreGive(s_snapshot_lock);
}

static void handle_command(const command_t *command)
{
    esp_err_t result = ESP_OK;
    switch (command->type) {
        case COMMAND_WIFI_ENABLE:
            result = esp_wifi_start();
            xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
            s_wifi_toggle_pending = false;
            if (result == ESP_OK) {
                s_wifi_enabled = true;
                s_snapshot.wifi = PET_WIRELESS_WIFI_IDLE;
            }
            xSemaphoreGive(s_snapshot_lock);
            break;
        case COMMAND_WIFI_DISABLE:
            (void)esp_wifi_disconnect();
            result = esp_wifi_stop();
            xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
            s_wifi_toggle_pending = false;
            if (result == ESP_OK || result == ESP_ERR_WIFI_NOT_STARTED) {
                s_wifi_enabled = false;
                s_snapshot.wifi = PET_WIRELESS_WIFI_DISABLED;
                s_snapshot.rssi = 0;
            }
            xSemaphoreGive(s_snapshot_lock);
            break;
        case COMMAND_WIFI_SCAN: {
            const wifi_scan_config_t scan = {.show_hidden = true};
            result = esp_wifi_scan_start(&scan, false);
            if (result != ESP_OK) {
                xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
                s_snapshot.wifi = PET_WIRELESS_WIFI_ERROR;
                xSemaphoreGive(s_snapshot_lock);
            }
            break;
        }
        case COMMAND_WIFI_SCAN_DONE:
            fetch_scan_results();
            return;
        case COMMAND_WIFI_CONNECT:
            handle_connect(command->connect_request);
            return;
        case COMMAND_WIFI_FORGET: {
            wifi_config_t empty_configuration = {0};
            (void)esp_wifi_disconnect();
            result = esp_wifi_set_config(WIFI_IF_STA, &empty_configuration);
            secure_zero(&empty_configuration, sizeof(empty_configuration));
            xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
            s_wifi_forget_pending = false;
            if (result == ESP_OK) {
                s_snapshot.wifi = PET_WIRELESS_WIFI_IDLE;
                s_snapshot.ssid[0] = '\0';
                s_snapshot.rssi = 0;
            }
            xSemaphoreGive(s_snapshot_lock);
            break;
        }
        case COMMAND_BLE_ADVERTISE:
            xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
            s_ble_advertising_requested = true;
            const bool synced = s_ble_synced;
            xSemaphoreGive(s_snapshot_lock);
            if (synced) {
                ble_update_advertising_state();
            }
            xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
            s_ble_command_pending = false;
            xSemaphoreGive(s_snapshot_lock);
            return;
        case COMMAND_BLE_STOP_ADVERTISING:
            xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
            s_ble_advertising_requested = false;
            xSemaphoreGive(s_snapshot_lock);
            xSemaphoreTake(s_ble_operation_lock, portMAX_DELAY);
            if (ble_gap_adv_active()) {
                result = ble_gap_adv_stop();
            }
            xSemaphoreGive(s_ble_operation_lock);
            xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
            s_ble_command_pending = false;
            if (result == ESP_OK) {
                s_snapshot.ble = PET_WIRELESS_BLE_IDLE;
            }
            xSemaphoreGive(s_snapshot_lock);
            break;
    }

    if (result != ESP_OK && result != ESP_ERR_WIFI_NOT_STARTED) {
        snapshot_set_error(result);
    }
}

static void wireless_task(void *argument)
{
    (void)argument;
    esp_err_t result = esp_hosted_connect_to_slave();
    if (result == ESP_OK) {
        result = initialize_wifi();
    }
    if (result != ESP_OK) {
        xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
        s_snapshot.backend = PET_WIRELESS_BACKEND_ERROR;
        s_snapshot.wifi = PET_WIRELESS_WIFI_ERROR;
        s_snapshot.ble = PET_WIRELESS_BLE_ERROR;
        s_snapshot.last_error = result;
        xSemaphoreGive(s_snapshot_lock);
    } else {
        xSemaphoreTake(s_snapshot_lock, portMAX_DELAY);
        s_snapshot.backend = PET_WIRELESS_BACKEND_READY;
        s_snapshot.wifi = PET_WIRELESS_WIFI_DISABLED;
        xSemaphoreGive(s_snapshot_lock);
        initialize_ble();
    }

    command_t command;
    for (;;) {
        if (xQueueReceive(s_command_queue, &command,
                          pdMS_TO_TICKS(PET_WIRELESS_RSSI_REFRESH_MS)) == pdTRUE) {
            handle_command(&command);
        } else {
            refresh_connection();
        }
    }
}

pet_wireless_result_t pet_wireless_start(void)
{
    taskENTER_CRITICAL(&s_start_lock);
    if (s_started) {
        taskEXIT_CRITICAL(&s_start_lock);
        return PET_WIRELESS_OK;
    }
    s_started = true;
    taskEXIT_CRITICAL(&s_start_lock);

    s_snapshot_lock = xSemaphoreCreateMutex();
    s_ble_operation_lock = xSemaphoreCreateMutex();
    s_command_queue = xQueueCreate(8U, sizeof(command_t));
    if (s_snapshot_lock == NULL || s_ble_operation_lock == NULL ||
        s_command_queue == NULL) {
        if (s_command_queue != NULL) {
            vQueueDelete(s_command_queue);
            s_command_queue = NULL;
        }
        if (s_snapshot_lock != NULL) {
            vSemaphoreDelete(s_snapshot_lock);
            s_snapshot_lock = NULL;
        }
        if (s_ble_operation_lock != NULL) {
            vSemaphoreDelete(s_ble_operation_lock);
            s_ble_operation_lock = NULL;
        }
        taskENTER_CRITICAL(&s_start_lock);
        s_started = false;
        taskEXIT_CRITICAL(&s_start_lock);
        return PET_WIRELESS_NO_MEMORY;
    }
    memset(&s_snapshot, 0, sizeof(s_snapshot));
    s_snapshot.backend = PET_WIRELESS_BACKEND_STARTING;
    s_snapshot.wifi = PET_WIRELESS_WIFI_DISABLED;
    s_snapshot.ble = PET_WIRELESS_BLE_DISABLED;

    if (xTaskCreate(wireless_task, "pet_wireless", PET_WIRELESS_TASK_STACK, NULL,
                    PET_WIRELESS_TASK_PRIORITY, NULL) != pdPASS) {
        s_snapshot.backend = PET_WIRELESS_BACKEND_ERROR;
        vQueueDelete(s_command_queue);
        s_command_queue = NULL;
        vSemaphoreDelete(s_snapshot_lock);
        s_snapshot_lock = NULL;
        vSemaphoreDelete(s_ble_operation_lock);
        s_ble_operation_lock = NULL;
        taskENTER_CRITICAL(&s_start_lock);
        s_started = false;
        taskEXIT_CRITICAL(&s_start_lock);
        return PET_WIRELESS_NO_MEMORY;
    }
    return PET_WIRELESS_OK;
}

bool pet_wireless_get_snapshot(pet_wireless_snapshot_t *snapshot)
{
    if (snapshot == NULL || s_snapshot_lock == NULL) {
        return false;
    }
    if (xSemaphoreTake(s_snapshot_lock, 0U) != pdTRUE) {
        return false;
    }
    *snapshot = s_snapshot;
    xSemaphoreGive(s_snapshot_lock);
    return true;
}

pet_wireless_result_t pet_wireless_wifi_set_enabled(bool enabled)
{
    if (!backend_ready()) {
        return PET_WIRELESS_INVALID_STATE;
    }
    if (xSemaphoreTake(s_snapshot_lock, 0U) != pdTRUE) {
        return PET_WIRELESS_BUSY;
    }
    if (s_wifi_toggle_pending || s_wifi_forget_pending ||
        s_snapshot.wifi == PET_WIRELESS_WIFI_SCANNING ||
        s_snapshot.wifi == PET_WIRELESS_WIFI_CONNECTING) {
        xSemaphoreGive(s_snapshot_lock);
        return PET_WIRELESS_BUSY;
    }
    if (enabled == s_wifi_enabled) {
        xSemaphoreGive(s_snapshot_lock);
        return PET_WIRELESS_OK;
    }
    s_wifi_toggle_pending = true;
    xSemaphoreGive(s_snapshot_lock);

    pet_wireless_result_t result =
        enqueue(enabled ? COMMAND_WIFI_ENABLE : COMMAND_WIFI_DISABLE, NULL);
    if (result != PET_WIRELESS_OK && xSemaphoreTake(s_snapshot_lock, 0U) == pdTRUE) {
        s_wifi_toggle_pending = false;
        xSemaphoreGive(s_snapshot_lock);
    }
    return result;
}

pet_wireless_result_t pet_wireless_wifi_scan(void)
{
    if (!backend_ready()) {
        return PET_WIRELESS_INVALID_STATE;
    }
    if (xSemaphoreTake(s_snapshot_lock, 0U) != pdTRUE) {
        return PET_WIRELESS_BUSY;
    }
    if (!s_wifi_enabled || s_wifi_toggle_pending || s_wifi_forget_pending ||
        s_snapshot.wifi == PET_WIRELESS_WIFI_SCANNING ||
        s_snapshot.wifi == PET_WIRELESS_WIFI_CONNECTING) {
        xSemaphoreGive(s_snapshot_lock);
        return s_wifi_enabled ? PET_WIRELESS_BUSY : PET_WIRELESS_INVALID_STATE;
    }
    s_scan_previous_state = s_snapshot.wifi;
    s_snapshot.wifi = PET_WIRELESS_WIFI_SCANNING;
    xSemaphoreGive(s_snapshot_lock);
    const pet_wireless_result_t result = enqueue(COMMAND_WIFI_SCAN, NULL);
    if (result != PET_WIRELESS_OK) {
        if (xSemaphoreTake(s_snapshot_lock, 0U) == pdTRUE) {
            s_snapshot.wifi = s_scan_previous_state;
            xSemaphoreGive(s_snapshot_lock);
        }
    }
    return result;
}

pet_wireless_result_t pet_wireless_wifi_connect(const char *ssid, const char *password)
{
    if (!pet_wireless_credentials_valid(ssid, password)) {
        return PET_WIRELESS_INVALID_ARGUMENT;
    }
    if (!backend_ready()) {
        return PET_WIRELESS_INVALID_STATE;
    }
    connect_request_t *request = calloc(1U, sizeof(*request));
    if (request == NULL) {
        return PET_WIRELESS_NO_MEMORY;
    }
    memcpy(request->ssid, ssid, strlen(ssid));
    memcpy(request->password, password, strlen(password));

    if (xSemaphoreTake(s_snapshot_lock, 0U) != pdTRUE) {
        secure_zero(request, sizeof(*request));
        free(request);
        return PET_WIRELESS_BUSY;
    }
    if (!s_wifi_enabled) {
        xSemaphoreGive(s_snapshot_lock);
        secure_zero(request, sizeof(*request));
        free(request);
        return PET_WIRELESS_INVALID_STATE;
    }
    if (s_wifi_forget_pending || s_snapshot.wifi == PET_WIRELESS_WIFI_SCANNING ||
        s_snapshot.wifi == PET_WIRELESS_WIFI_CONNECTING) {
        xSemaphoreGive(s_snapshot_lock);
        secure_zero(request, sizeof(*request));
        free(request);
        return PET_WIRELESS_BUSY;
    }
    if (s_snapshot.wifi == PET_WIRELESS_WIFI_CONNECTED) {
        xSemaphoreGive(s_snapshot_lock);
        secure_zero(request, sizeof(*request));
        free(request);
        return PET_WIRELESS_INVALID_STATE;
    }
    snprintf(s_snapshot.ssid, sizeof(s_snapshot.ssid), "%s", ssid);
    s_snapshot.rssi = 0;
    s_snapshot.wifi = PET_WIRELESS_WIFI_CONNECTING;
    xSemaphoreGive(s_snapshot_lock);

    const pet_wireless_result_t result = enqueue(COMMAND_WIFI_CONNECT, request);
    if (result != PET_WIRELESS_OK) {
        secure_zero(request, sizeof(*request));
        free(request);
        if (xSemaphoreTake(s_snapshot_lock, 0U) == pdTRUE) {
            s_snapshot.wifi = PET_WIRELESS_WIFI_IDLE;
            xSemaphoreGive(s_snapshot_lock);
        }
        return result;
    }
    return PET_WIRELESS_OK;
}

pet_wireless_result_t pet_wireless_wifi_forget(void)
{
    if (!backend_ready()) {
        return PET_WIRELESS_INVALID_STATE;
    }
    if (xSemaphoreTake(s_snapshot_lock, 0U) != pdTRUE) {
        return PET_WIRELESS_BUSY;
    }
    if (s_wifi_toggle_pending || s_wifi_forget_pending ||
        s_snapshot.wifi == PET_WIRELESS_WIFI_SCANNING ||
        s_snapshot.wifi == PET_WIRELESS_WIFI_CONNECTING) {
        xSemaphoreGive(s_snapshot_lock);
        return PET_WIRELESS_BUSY;
    }
    s_wifi_forget_pending = true;
    xSemaphoreGive(s_snapshot_lock);

    pet_wireless_result_t result = enqueue(COMMAND_WIFI_FORGET, NULL);
    if (result != PET_WIRELESS_OK && xSemaphoreTake(s_snapshot_lock, 0U) == pdTRUE) {
        s_wifi_forget_pending = false;
        xSemaphoreGive(s_snapshot_lock);
    }
    return result;
}

pet_wireless_result_t pet_wireless_ble_set_advertising(bool enabled)
{
    if (!backend_ready()) {
        return PET_WIRELESS_INVALID_STATE;
    }
    if (xSemaphoreTake(s_snapshot_lock, 0U) != pdTRUE) {
        return PET_WIRELESS_BUSY;
    }
    bool advertising = s_snapshot.ble == PET_WIRELESS_BLE_ADVERTISING;
    if (s_ble_command_pending) {
        xSemaphoreGive(s_snapshot_lock);
        return PET_WIRELESS_BUSY;
    }
    if (s_snapshot.ble != PET_WIRELESS_BLE_IDLE &&
        s_snapshot.ble != PET_WIRELESS_BLE_ADVERTISING) {
        xSemaphoreGive(s_snapshot_lock);
        return PET_WIRELESS_INVALID_STATE;
    }
    if (enabled == advertising) {
        xSemaphoreGive(s_snapshot_lock);
        return PET_WIRELESS_OK;
    }
    s_ble_command_pending = true;
    xSemaphoreGive(s_snapshot_lock);

    pet_wireless_result_t result = enqueue(
        enabled ? COMMAND_BLE_ADVERTISE : COMMAND_BLE_STOP_ADVERTISING, NULL);
    if (result != PET_WIRELESS_OK && xSemaphoreTake(s_snapshot_lock, 0U) == pdTRUE) {
        s_ble_command_pending = false;
        xSemaphoreGive(s_snapshot_lock);
    }
    return result;
}
