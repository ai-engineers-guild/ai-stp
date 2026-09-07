"""Valid, generated image bytes for media boundary tests."""

from io import BytesIO

from PIL import Image, PngImagePlugin


def image_bytes(
    *, size: tuple[int, int] = (24, 16), format: str = "PNG", metadata: bool = False
) -> bytes:
    image = Image.new("RGB", size, (17, 83, 149))
    output = BytesIO()
    kwargs: dict[str, object] = {}
    if metadata:
        if format == "PNG":
            info = PngImagePlugin.PngInfo()
            info.add_text("private_note", "must not be public")
            kwargs["pnginfo"] = info
        else:
            exif = Image.Exif()
            exif[270] = "must not be public"
            kwargs["exif"] = exif
    image.save(output, format=format, **kwargs)
    return output.getvalue()
