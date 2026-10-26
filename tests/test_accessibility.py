from serein_vault.gui import COLORS


def luminance(color):
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return sum(
        channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True)
    )


def contrast(first, second):
    high, low = sorted([luminance(first), luminance(second)], reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_interface_text_contrast():
    for foreground, background in (
        (COLORS["text"], COLORS["surface"]),
        (COLORS["muted"], COLORS["surface"]),
        (COLORS["text"], COLORS["input"]),
        (COLORS["accent_text"], COLORS["accent"]),
        (COLORS["accent_text"], COLORS["accent_active"]),
        (COLORS["error"], COLORS["surface"]),
        (COLORS["selection_text"], COLORS["selection"]),
    ):
        assert contrast(foreground, background) >= 4.5


def test_focus_and_field_boundaries_are_visible():
    assert contrast(COLORS["focus"], COLORS["surface"]) >= 3
    assert contrast(COLORS["border"], COLORS["input"]) >= 3
