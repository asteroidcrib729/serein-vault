"""Build crisp multi-resolution branding with a build-only Pillow dependency."""

from pathlib import Path

from PIL import Image, ImageDraw


def make_assets(destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (1024, 1024), "#121c2c")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((48, 48, 976, 976), radius=200, fill="#0e1726")
    draw.polygon(
        [
            (512, 160),
            (804, 280),
            (772, 590),
            (690, 738),
            (512, 862),
            (334, 738),
            (252, 590),
            (220, 280),
        ],
        fill="#5eead4",
    )
    draw.ellipse((428, 360, 596, 528), fill="#042f2e")
    draw.polygon([(480, 470), (544, 470), (570, 666), (454, 666)], fill="#042f2e")
    for name, size in (
        ("icon", 256),
        ("Square44x44Logo", 44),
        ("Square150x150Logo", 150),
        ("StoreLogo", 50),
    ):
        image.resize((size, size), Image.Resampling.LANCZOS).save(destination / f"{name}.png")
    image.save(
        destination / "SereinVault.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
    )


if __name__ == "__main__":
    make_assets(Path(__file__).resolve().parents[1] / "src" / "serein_vault" / "assets")
