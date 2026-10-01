def classify_lesson_type(subject: str) -> str:
    """
    Classifies a lesson by type based on the subject string.

    Rules (case-sensitive):
      - Returns 'nachhilfe' if 'Nachhilfe' is in subject (checked first).
      - Returns 'individual' if 'Ind.' is in subject.
      - Returns 'group' otherwise (including None / empty string).

    Args:
        subject: lesson subject string, may be None or empty.

    Returns:
        One of: 'group', 'individual', 'nachhilfe'
    """
    if not subject or not isinstance(subject, str):
        return "group"
    if "Nachhilfe" in subject:
        return "nachhilfe"
    if "Ind." in subject:
        return "individual"
    return "group"
