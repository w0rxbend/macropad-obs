// SPDX-License-Identifier: MIT
#pragma once

#include "link.h"

void usb_init(void);
int usb_poll(link_t *link, link_frame_t *out, int cap);
bool usb_hello_due(void);
void usb_hello_sent(void);
