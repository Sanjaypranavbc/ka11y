
import cv2
import numpy as np
def estimate_boldness(img, bbox):
    x_coords = [p[0] for p in bbox]
    y_coords = [p[1] for p in bbox]

    x1, x2 = min(x_coords), max(x_coords)
    y1, y2 = min(y_coords), max(y_coords)

    crop = img[y1:y2, x1:x2]

    if crop.size == 0:
        return False

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    _, thresh = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    text_pixels = np.sum(thresh == 0)
    total_pixels = thresh.size

    density = text_pixels / total_pixels

    return density > 0.35  # tune if needed


def bbox_height_rotated(bbox):
    p0 = np.array(bbox[0])  # top-left
    p3 = np.array(bbox[3])  # bottom-left
    return np.linalg.norm(p3 - p0)


def load_image_with_alpha(image_path):
    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)

    if img is None:
        return None

    # Handle RGBA → composite onto white background
    if len(img.shape) == 3 and img.shape[2] == 4:
        alpha = img[:, :, 3] / 255.0
        background = np.ones_like(img[:, :, :3]) * 255

        img = (
            img[:, :, :3] * alpha[..., None]
            + background * (1 - alpha[..., None])
        ).astype(np.uint8)

    return img