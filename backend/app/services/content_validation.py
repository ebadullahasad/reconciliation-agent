class ContentValidationError(RuntimeError):
    pass


def validate_content(suffix: str, content: bytes) -> None:
    """Lightweight magic-byte check: does the file's actual content match what
    its extension claims? Catches a renamed/mislabeled file before we ever
    parse or trust it - this is the "post" validation, the real gate, as
    opposed to the "pre" check at request-url time which only trusts what the
    client claims."""

    if suffix == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise ContentValidationError(
                "file claims to be PDF but doesn't start with the PDF signature (%PDF-)"
            )
    elif suffix == ".csv":
        if b"\x00" in content[:4096]:
            raise ContentValidationError("file claims to be CSV but contains binary data (null bytes)")
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContentValidationError(f"file claims to be CSV but isn't valid UTF-8 text: {exc}")
    else:
        raise ContentValidationError(f"no content validator for suffix '{suffix}'")
