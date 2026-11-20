// SPDX-License-Identifier: MIT
// Entry point. Task 4.1 only proves the IDF project builds with the core linked in; task 4.7
// writes the task layout, the watchdog and the power cap here.
#include "link.h"

#include "esp_log.h"

static const char *TAG = "macropad-obs";

void app_main(void)
{
	ESP_LOGI(TAG, "link protocol %d; ports not started (tasks 4.2-4.7)", LINK_VERSION);
}
