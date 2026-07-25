// SPDX-License-Identifier: MIT
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

// Генератор синусоїдної обвідної + керування unfolder.
// Працює від власного gptimer з частотою INV_CARRIER_HZ / INV_MOD_DECIM,
// бо компаратори MCPWM оновлюються атомарно на межі періоду - джитер ISR не критичний.
esp_err_t inv_mod_init(void);
esp_err_t inv_mod_start(void);
void      inv_mod_stop(void);

// Цільова частота виходу, Гц (обмежується INV_OUT_FREQ_HZ_MIN/MAX).
void inv_mod_set_out_freq(float hz);

// Цільова амплітуда, Q15 (0..INV_DUTY_MAX_Q15). Досягається через софт-старт.
void inv_mod_set_amplitude(uint16_t amp_q15);

// Телеметрія
uint16_t inv_mod_get_amplitude(void);
float    inv_mod_get_out_freq(void);
uint32_t inv_mod_get_isr_count(void);
