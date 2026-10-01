"""
Модуль для добавления ограничений для связанных занятий.
"""

from time_utils import pause_to_slots


def build_linked_chains(optimizer):
    """Формирует список связанных цепочек занятий (индексы классов)."""
    chains = []
    seen = set()

    for idx, c in enumerate(optimizer.classes):
        if not getattr(c, "linked_classes", None):
            continue

        chain = [idx]
        for linked_class in c.linked_classes:
            linked_idx = optimizer._find_class_index(linked_class)

            if linked_idx in chain:
                break
            chain.append(linked_idx)

        chain_tuple = tuple(chain)
        if chain_tuple not in seen:
            chains.append(chain)
            seen.add(chain_tuple)

    optimizer.linked_chains = chains

def add_linked_constraints(optimizer):
    """Add constraints for linked classes."""
    build_linked_chains(optimizer)
    
    for idx, c in enumerate(optimizer.classes):
        if hasattr(c, 'linked_classes') and c.linked_classes:
            # Process linked classes (classes that must occur in sequence)
            prev_class = c
            prev_idx = idx
            
            for linked_class in c.linked_classes:
                # Find the index of the linked class using our helper method.
                linked_idx = optimizer._find_class_index(linked_class)

                # Classes must be on the same day.
                if isinstance(optimizer.day_vars[prev_idx], int) and isinstance(optimizer.day_vars[linked_idx], int):
                    # Both days are fixed, verify they are the same.
                    if optimizer.day_vars[prev_idx] != optimizer.day_vars[linked_idx]:
                        raise ValueError(
                            f"Linked classes {prev_class.subject} and {linked_class.subject} "
                            f"have different fixed days"
                        )
                elif isinstance(optimizer.day_vars[prev_idx], int):
                    # Previous day is fixed, linked day must match.
                    optimizer.model.Add(optimizer.day_vars[linked_idx] == optimizer.day_vars[prev_idx])
                elif isinstance(optimizer.day_vars[linked_idx], int):
                    # Linked day is fixed, previous day must match.
                    optimizer.model.Add(optimizer.day_vars[prev_idx] == optimizer.day_vars[linked_idx])
                else:
                    # Neither day is fixed, they must be equal.
                    optimizer.model.Add(optimizer.day_vars[prev_idx] == optimizer.day_vars[linked_idx])

                # Second class must start after first class ends.
                if isinstance(optimizer.start_vars[prev_idx], int) and isinstance(optimizer.start_vars[linked_idx], int):
                    # Both start times are fixed, verify sequence.
                    prev_end = optimizer.start_vars[prev_idx] + (prev_class.duration // optimizer.time_interval) + pause_to_slots(prev_class.pause_after, optimizer.time_interval)
                    if prev_end + pause_to_slots(linked_class.pause_before, optimizer.time_interval) > optimizer.start_vars[linked_idx]:
                        raise ValueError(
                            f"Fixed start times for linked classes {prev_class.subject} and "
                            f"{linked_class.subject} do not allow sufficient time between them"
                        )
                elif isinstance(optimizer.start_vars[prev_idx], int):
                    # Previous start is fixed, calculate end time.
                    prev_end = optimizer.start_vars[prev_idx] + (prev_class.duration // optimizer.time_interval) + pause_to_slots(prev_class.pause_after, optimizer.time_interval)
                    min_linked_start = prev_end + pause_to_slots(linked_class.pause_before, optimizer.time_interval)
                    optimizer.model.Add(optimizer.start_vars[linked_idx] >= min_linked_start)
                elif isinstance(optimizer.start_vars[linked_idx], int):
                    # Linked start is fixed, calculate latest previous end.
                    max_prev_end = optimizer.start_vars[linked_idx] - pause_to_slots(linked_class.pause_before, optimizer.time_interval)
                    slots_needed = (prev_class.duration // optimizer.time_interval) + pause_to_slots(prev_class.pause_after, optimizer.time_interval)
                    max_prev_start = max_prev_end - slots_needed
                    optimizer.model.Add(optimizer.start_vars[prev_idx] <= max_prev_start)
                else:
                    # Neither start is fixed.
                    prev_slots = (prev_class.duration // optimizer.time_interval) + pause_to_slots(prev_class.pause_after, optimizer.time_interval)
                    linked_pause_slots = pause_to_slots(linked_class.pause_before, optimizer.time_interval)

                    # Next class must start after previous class ends plus pause.
                    optimizer.model.Add(
                        optimizer.start_vars[linked_idx] >=
                        optimizer.start_vars[prev_idx] + prev_slots + linked_pause_slots
                    )

                # Update for next iteration.
                prev_class = linked_class
                prev_idx = linked_idx
