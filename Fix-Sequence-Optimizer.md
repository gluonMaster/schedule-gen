# Optimizer Fix Sequence (SchedGen_PreRelease)

Цель: привести CP‑SAT модель к **корректности** (нет ложных INFEASIBLE/пропусков конфликтов), затем — к **устойчивости** на “живых” Excel‑кейcах и адекватной диагностике.

---

## Coverage Map (что чем покрыто)

| Проблема из анализа | Где фиксируется |
|---|---|
| Коллизии `_find_class_index` / “слипание” занятий → самоссылка `start[k] >= start[k] + N` | `Prompt-Fix-Optimizer-01-ClassMapCollision.md` |
| `linked_chains` обрывается на первом звене → D “вне цепочки” | `Prompt-Fix-Optimizer-02-LinkedChainTraversal.md` |
| Жёсткая фиксация первого оконного занятия `start == slot` | `Prompt-Fix-Optimizer-03-TimewindowAdapterFixes.md` (3A) |
| Искусственный разрыв 15 мин через `max(1, ...)` | `Prompt-Fix-Optimizer-03-TimewindowAdapterFixes.md` (3B) + `Prompt-Fix-Optimizer-05B-PauseSlotRounding.md` |
| Day‑model mismatch: `day_indices` с “дырами”, а домен `day_var` 0..N-1 | `Prompt-Fix-Optimizer-06-DayIndexDomainMismatch.md` |
| Несогласованное округление времени в слоты + “минуты vs слоты” | `Prompt-Fix-Optimizer-07-TimeDiscretizationAndUnits.md` + `Prompt-Fix-Optimizer-04-ConflictConstraintLogic.md` (4H) |
| Перекос по аудиториям: shared_rooms → всегда запрет по времени | `Prompt-Fix-Optimizer-04-ConflictConstraintLogic.md` (4F, 4G) |
| `times_overlap` как предфильтр пропускает обязательные пары (окна) | `Prompt-Fix-Optimizer-04-ConflictConstraintLogic.md` (4E) |
| В `time_conflict_constraints` “условные” ограничения по комнате мёртвые | `Prompt-Fix-Optimizer-04-ConflictConstraintLogic.md` (4G) |
| Диагностика “0 conflicting constraints” (assumptions не используются) | `Prompt-Fix-Optimizer-05D-InfeasibilityDiagnostics.md` |
| CLI маскирует INFEASIBLE как “time limit” | `Prompt-Fix-Optimizer-08-SolverStatusPropagation.md` |
| Латентный `AttributeError` в `_check_sequential_scheduling` | `Prompt-Fix-Optimizer-05A-SequentialSchedulingChecker.md` |
| Мёртвый импорт/дублирование `enforce_window_chain_sequencing` | `Prompt-Fix-Optimizer-05C-EnforceWindowChainSequencing.md` |

---

## Рекомендуемая последовательность применения фиксов

### Phase 0 — Observability (чтобы не “лечить вслепую”)

1) `Prompt-Fix-Optimizer-08-SolverStatusPropagation.md`
   - цель: различать INFEASIBLE vs UNKNOWN(timeout) в CLI/логах.

2) `Prompt-Fix-Optimizer-05D-InfeasibilityDiagnostics.md`
   - цель: убрать вводящий в заблуждение вывод “Found 0 conflicting constraints”.

### Phase 1 — Hard correctness (устранить гарантированные ложные INFEASIBLE/краши)

3) `Prompt-Fix-Optimizer-01-ClassMapCollision.md`
   - критично: убирает самоссылочные ограничения и “слипание” занятий.

4) `Prompt-Fix-Optimizer-02-LinkedChainTraversal.md`
   - важно: корректная `linked_chains` нужна для `timewindow_adapter` и “цепочных” правил.

5) `Prompt-Fix-Optimizer-06-DayIndexDomainMismatch.md`
   - важно: устраняет “дыры” в днях, предотвращает краш при сборке solution.

### Phase 2 — Time modeling normalization (единые слоты и паузы)

6) `Prompt-Fix-Optimizer-07-TimeDiscretizationAndUnits.md`
   - цель: единые правила ceil/floor/slot_to_minutes и устранение “минуты vs слоты”.

7) `Prompt-Fix-Optimizer-05B-PauseSlotRounding.md`
   - цель: единый перевод пауз в слоты (0→0, 1..14→1, …) во всех модулях.

8) `Prompt-Fix-Optimizer-03-TimewindowAdapterFixes.md`
   - 3B (разрывы/паузы) логически связан с шагом 7;
   - 3A (снять жёсткую фиксацию) увеличивает свободу и снижает шанс ложного INFEASIBLE.

### Phase 3 — Resource conflict modeling (комнаты/преподаватели/окна)

9) `Prompt-Fix-Optimizer-04-ConflictConstraintLogic.md`
   - применять после Phase 2, потому что 4H и часть конфликтной логики зависит от корректной конвертации “слот→минуты” и правил округления.

### Phase 4 — Cleanup / dead code

10) `Prompt-Fix-Optimizer-05C-EnforceWindowChainSequencing.md`
   - убрать мёртвые импорты/функции или интегрировать их корректно.

11) `Prompt-Fix-Optimizer-05A-SequentialSchedulingChecker.md` (опционально, если планируется использовать `_check_sequential_scheduling`)
   - убрать латентный `AttributeError` и привести конвертацию “минуты→слоты” к единому стандарту.

---

## Мини‑чеклист валидации после каждого этапа

1) Базовый прогон на эталонном файле:
   - `python main_sch.py xlsx_initial/schedule_planning.xlsx --time-limit 60 --verbose`

2) Проверки логов:
   - статус CP‑SAT (OPTIMAL/FEASIBLE/INFEASIBLE/UNKNOWN) отражается корректно;
   - нет “самоссылок” вида `start[i] >= start[i] + k`;
   - `linked_chains` включает все звенья (например, B→C→D).

3) Проверки “единиц”:
   - нигде не сравниваются “минуты от полуночи” с `slot_idx * interval` без `slot_to_minutes`.
