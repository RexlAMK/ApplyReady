"""
image_utils.py
Smart Passport/ID Photo Generator core logic.

Pipeline:
  1. Load image (from upload or camera).
  2. Detect the face (OpenCV Haar cascade) to guide cropping.
  3. Remove background (rembg) if available; otherwise fall back gracefully.
  4. Composite onto the chosen background color (or keep original).
  5. Crop/center around the face + head/shoulders region, preserving aspect ratio.
  6. Resize to the exact requested pixel dimensions.
  7. Gently improve brightness/contrast.
  8. Optionally convert to black & white (grayscale) with good contrast.
  9. Build a print-ready sheet (JPG grid) and a matching PDF.

Everything here is defensive: any failure degrades to a reasonable
fallback rather than raising an exception up into the Streamlit app.
"""

import io
import logging

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

logger = logging.getLogger("applyready.image")

# Professional (not neon) passport-photo blue.
PASSPORT_BLUE = (66, 133, 168)
PASSPORT_WHITE = (255, 255, 255)

DPI = 300  # standard print resolution used for unit conversions

# Standard default passport photo size (a very common size internationally,
# e.g. US 2x2in / many countries' 35x45mm equivalents are close but differ --
# we use 35mm x 45mm as a broadly recognizable default and clearly label it).
DEFAULT_WIDTH_MM = 35
DEFAULT_HEIGHT_MM = 45

_face_cascade = None


def _get_face_cascade():
    """Lazily load the OpenCV Haar cascade for frontal face detection."""
    global _face_cascade
    if _face_cascade is not None:
        return _face_cascade
    try:
        import cv2
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(cascade_path)
        if cascade.empty():
            _face_cascade = False
        else:
            _face_cascade = cascade
    except Exception:
        logger.warning("OpenCV face cascade unavailable; falling back to center-crop.")
        _face_cascade = False
    return _face_cascade


def convert_to_pixels(value, unit):
    """Convert a width/height value in mm, cm, inches, or px to pixels at DPI."""
    unit = (unit or "px").lower()
    if unit == "px":
        return int(round(value))
    if unit == "mm":
        inches = value / 25.4
    elif unit == "cm":
        inches = value / 2.54
    elif unit in ("in", "inch", "inches"):
        inches = value
    else:
        inches = value / 25.4  # default to mm behavior
    return max(1, int(round(inches * DPI)))


def load_image_from_bytes(raw_bytes):
    """Load bytes into a PIL Image (RGB), or return None on failure."""
    try:
        img = Image.open(io.BytesIO(raw_bytes))
        img = ImageOps.exif_transpose(img)  # respect camera orientation
        return img.convert("RGB")
    except Exception:
        logger.exception("Failed to load image bytes.")
        return None


def detect_face_box(pil_image):
    """
    Detect the largest face in the image.
    Returns (x, y, w, h) in pixel coordinates, or None if no face found.
    """
    cascade = _get_face_cascade()
    if not cascade:
        return None
    try:
        import cv2
        arr = np.array(pil_image.convert("L"))
        faces = cascade.detectMultiScale(arr, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
        if len(faces) == 0:
            return None
        # pick the largest detected face
        faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        x, y, w, h = faces[0]
        return int(x), int(y), int(w), int(h)
    except Exception:
        logger.exception("Face detection failed.")
        return None


def remove_background(pil_image):
    """
    Attempt to remove the background using rembg, returning an RGBA image
    with transparency where the background was. Returns None if rembg is
    unavailable or the operation fails, so callers can fall back cleanly.
    """
    try:
        from rembg import remove
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        result_bytes = remove(buf.getvalue())
        result = Image.open(io.BytesIO(result_bytes)).convert("RGBA")
        return result
    except Exception:
        logger.warning("Background removal unavailable or failed; using original background.")
        return None


def composite_on_background(rgba_image, bg_color):
    """Flatten an RGBA (subject with transparency) image onto a solid background color."""
    background = Image.new("RGB", rgba_image.size, bg_color)
    background.paste(rgba_image, mask=rgba_image.split()[-1])
    return background


def crop_to_face(pil_image, face_box, target_w, target_h):
    """
    Crop the image around the detected face so the result matches the
    target aspect ratio, keeping head + shoulders in frame and the
    subject centered. Falls back to a centered crop if no face box.
    """
    img_w, img_h = pil_image.size
    target_ratio = target_w / target_h

    if face_box:
        fx, fy, fw, fh = face_box
        face_cx = fx + fw / 2
        face_cy = fy + fh / 2
        # Passport convention: head height ~= 60-70% of frame height.
        # So overall crop height ≈ face height / 0.35 (generous headroom + shoulders).
        crop_h = fh / 0.35
        crop_w = crop_h * target_ratio

        # Ensure crop box fits within the image; shrink proportionally if needed.
        scale = min(1.0, img_w / crop_w, img_h / crop_h)
        crop_w *= scale
        crop_h *= scale

        left = face_cx - crop_w / 2
        # Give slightly more room below the face for shoulders than above for hair.
        top = face_cy - crop_h * 0.42
    else:
        # No face detected: fall back to a centered crop matching the aspect ratio.
        if img_w / img_h > target_ratio:
            crop_h = img_h
            crop_w = crop_h * target_ratio
        else:
            crop_w = img_w
            crop_h = crop_w / target_ratio
        left = (img_w - crop_w) / 2
        top = (img_h - crop_h) / 2

    # Clamp crop box inside image bounds.
    left = max(0, min(left, img_w - crop_w))
    top = max(0, min(top, img_h - crop_h))
    right = left + crop_w
    bottom = top + crop_h

    cropped = pil_image.crop((int(left), int(top), int(right), int(bottom)))
    return cropped


def enhance_image(pil_image):
    """Gentle brightness/contrast/sharpness improvement -- avoid over-editing."""
    img = ImageEnhance.Brightness(pil_image).enhance(1.04)
    img = ImageEnhance.Contrast(img).enhance(1.06)
    img = ImageEnhance.Sharpness(img).enhance(1.08)
    return img


def to_grayscale_high_contrast(pil_image):
    """Convert to grayscale while preserving good contrast."""
    gray = ImageOps.grayscale(pil_image)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    return gray.convert("RGB")


def generate_passport_photo(raw_bytes, target_w_px, target_h_px, background_choice, black_and_white):
    """
    Full pipeline. background_choice is one of: "blue", "white", "original".
    Returns a dict:
      {
        "ok": bool,
        "image": PIL.Image or None,       # final processed image (RGB)
        "original": PIL.Image or None,    # original image for side-by-side preview
        "warning": str or None,           # non-fatal note (e.g. bg removal fallback)
        "error": str or None,             # fatal error message
      }
    """
    original = load_image_from_bytes(raw_bytes)
    if original is None:
        return {"ok": False, "image": None, "original": None, "warning": None,
                 "error": "Could not read this image. Please try a different JPG or PNG file."}

    warning = None
    working = original

    if background_choice in ("blue", "white"):
        rgba = remove_background(working)
        if rgba is not None:
            bg_color = PASSPORT_BLUE if background_choice == "blue" else PASSPORT_WHITE
            working = composite_on_background(rgba, bg_color)
        else:
            warning = ("Automatic background removal wasn't available, so the original "
                        "background was kept. You can still crop, resize, and use black & white.")

    face_box = detect_face_box(working)
    try:
        cropped = crop_to_face(working, face_box, target_w_px, target_h_px)
    except Exception:
        logger.exception("Cropping failed; using center-cropped fallback.")
        cropped = ImageOps.fit(working, (target_w_px, target_h_px), method=Image.LANCZOS)
        try:
            resized = cropped
            final = enhance_image(resized)
            if black_and_white:
                final = to_grayscale_high_contrast(final)
            return {"ok": True, "image": final, "original": original,
                     "warning": warning or "Used a general center-crop fallback.", "error": None}
        except Exception as e:
            return {"ok": False, "image": None, "original": original, "warning": warning,
                     "error": f"Image processing failed: {e}"}

    try:
        resized = cropped.resize((target_w_px, target_h_px), Image.LANCZOS)
        final = enhance_image(resized)
        if black_and_white:
            final = to_grayscale_high_contrast(final)
        if not face_box:
            note = "No face was clearly detected, so the photo was centered automatically."
            warning = f"{warning} {note}" if warning else note
        return {"ok": True, "image": final, "original": original, "warning": warning, "error": None}
    except Exception as e:
        logger.exception("Final resize/enhance failed.")
        return {"ok": False, "image": None, "original": original, "warning": warning,
                 "error": f"Image processing failed: {e}"}


def image_to_jpg_bytes(pil_image, quality=95):
    buf = io.BytesIO()
    pil_image.convert("RGB").save(buf, format="JPEG", quality=quality, dpi=(DPI, DPI))
    return buf.getvalue()


# ---------------------------------------------------------------------
# Print sheet generation
# ---------------------------------------------------------------------

PAPER_SIZES_MM = {
    "4x6 inch": (101.6, 152.4),
    "A4": (210, 297),
}


def build_print_sheet(pil_photo, paper_choice, margin_mm=5, gap_mm=3):
    """
    Arrange as many copies of pil_photo as fit on the chosen paper size.
    Returns (sheet_image, count) where sheet_image is a PIL RGB image at
    print DPI, and count is how many photos were placed.
    """
    paper_w_mm, paper_h_mm = PAPER_SIZES_MM.get(paper_choice, PAPER_SIZES_MM["4x6 inch"])
    sheet_w = convert_to_pixels(paper_w_mm, "mm")
    sheet_h = convert_to_pixels(paper_h_mm, "mm")
    margin = convert_to_pixels(margin_mm, "mm")
    gap = convert_to_pixels(gap_mm, "mm")

    photo_w, photo_h = pil_photo.size

    usable_w = sheet_w - 2 * margin
    usable_h = sheet_h - 2 * margin

    cols = max(1, (usable_w + gap) // (photo_w + gap))
    rows = max(1, (usable_h + gap) // (photo_h + gap))
    cols, rows = int(cols), int(rows)

    sheet = Image.new("RGB", (sheet_w, sheet_h), (255, 255, 255))
    count = 0
    for r in range(rows):
        for c in range(cols):
            x = margin + c * (photo_w + gap)
            y = margin + r * (photo_h + gap)
            if x + photo_w <= sheet_w - margin + 1 and y + photo_h <= sheet_h - margin + 1:
                sheet.paste(pil_photo, (int(x), int(y)))
                count += 1

    if count == 0:
        # Photo is larger than the sheet's usable area -- just center one copy.
        x = max(0, (sheet_w - photo_w) // 2)
        y = max(0, (sheet_h - photo_h) // 2)
        sheet.paste(pil_photo.resize((min(photo_w, sheet_w), min(photo_h, sheet_h))), (x, y))
        count = 1

    return sheet, count


def sheet_to_pdf_bytes(sheet_image):
    """Convert the print sheet PIL image into a single-page PDF (bytes)."""
    buf = io.BytesIO()
    sheet_image.convert("RGB").save(buf, format="PDF", resolution=DPI)
    return buf.getvalue()
