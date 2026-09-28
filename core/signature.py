from .config import SignatureConfig


def build_signature(config: SignatureConfig) -> str:
    lines = ["[right]Sincerely,"]
    if config.image_url.strip():
        lines.append(f"[img]{config.image_url.strip()}[/img]")
    position = config.position.strip()
    staff_name = config.staff_name.strip()
    if position and staff_name:
        lines.append(f"[b]{position}[/b], [i]{staff_name}[/i]")
    elif position:
        lines.append(f"[b]{position}[/b]")
    elif staff_name:
        lines.append(f"[i]{staff_name}[/i]")
    lines.append("[/right]")
    return "\n".join(lines)


def signature_or_default(config: SignatureConfig | None) -> str:
    return build_signature(config or SignatureConfig())
