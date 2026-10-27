"""Small text normalizers shared by complaint intake and alert rules."""


def normalize_block(raw: str | None) -> str:
    """Normalize a student-supplied block value.

    " b ", "Block B", "block-b" and "B" all become "B", so the repeat-problem
    alert rule compares canonical values. Keeps other values (e.g. "C-annex")
    intact apart from casing/trim.
    """
    import re

    text = (raw or "").strip()
    # Drop a leading "block" token (case-insensitive) with any separator tail.
    text = re.sub(r"^block[\s\-_.]*", "", text, flags=re.IGNORECASE).strip()
    return text.upper()
