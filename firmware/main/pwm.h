// SPDX-License-Identifier: MIT
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

// Ініціалізація LV-моста (MCPWM0) і синхронного випрямляча (MCPWM1).
// Виходи створюються, але таймери НЕ запускаються.
esp_err_t inv_pwm_init(void);

// Синхронний запуск обох таймерів. Обидві групи MCPWM тактуються від одного
// PLL_160M з однаковим періодом, тому після одноразового вирівнювання фазовий
// звʼязок не розʼїжджається.
esp_err_t inv_pwm_start(void);

// Аварійне гальмування: усі виходи в низький рівень, драйвери в shutdown.
void inv_pwm_brake(void);

// Скидання аварії. Повертає false, якщо вивід FAULT_N усе ще активний.
bool inv_pwm_clear_fault(void);

// Оновлення фазового зсуву. phi_ticks у діапазоні [0, INV_HALF_PERIOD_TICKS].
// Прикладений до первинки duty = 2*phi/T. Викликається з ISR модуляції.
void inv_pwm_set_phase(uint32_t phi_ticks);

// Чи спрацював апаратний захист.
bool inv_pwm_faulted(void);
