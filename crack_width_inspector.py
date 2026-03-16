import argparse
import math
import ssl
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

HED_PROTO_URL = (
    "https://raw.githubusercontent.com/s9xie/hed/master/examples/hed/deploy.prototxt"
)
HED_MODEL_URL = "https://vcl.ucsd.edu/hed/hed_pretrained_bsds.caffemodel"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

StatusCallback = Optional[Callable[[str], None]]


@dataclass
class ProcessingResult:
    input_path: Path
    output_dir: Path
    mask_path: Path
    skeleton_path: Path
    overlay_path: Path
    widths_csv: Path
    profile_csv: Optional[Path]
    samples_csv: Optional[Path]
    skeleton_points: int
    sampled_points: int
    max_width_px: float
    max_width_mm: float
    mean_width_px: float
    mean_width_mm: float
    main_path_length_px: float


class CropLayer(cv2.dnn.Layer):
    def __init__(self, params, blobs):
        super().__init__()
        self.xstart = 0
        self.xend = 0
        self.ystart = 0
        self.yend = 0

    def getMemoryShapes(self, inputs):
        input_shape = inputs[0]
        target_shape = inputs[1]
        batch, channels = input_shape[0], input_shape[1]
        height, width = target_shape[2], target_shape[3]
        self.ystart = int((input_shape[2] - height) / 2)
        self.xstart = int((input_shape[3] - width) / 2)
        self.yend = self.ystart + height
        self.xend = self.xstart + width
        return [[batch, channels, height, width]]

    def forward(self, inputs):
        return [inputs[0][:, :, self.ystart : self.yend, self.xstart : self.xend]]


def emit_status(status_callback: StatusCallback, message: str):
    if status_callback is not None:
        status_callback(message)
    else:
        print(message)


def resource_base_dir() -> Path:
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_model_dir() -> Path:
    bundled = resource_base_dir() / "models" / "hed"
    if bundled.exists():
        return bundled
    return runtime_base_dir() / "models" / "hed"


def default_input_path() -> Path:
    sample = runtime_base_dir() / "crack.jpeg"
    if sample.exists():
        return sample
    return Path("crack.jpeg")


def register_hed_layers():
    try:
        cv2.dnn_registerLayer("Crop", CropLayer)
    except Exception:
        pass


def download_if_missing(url: str, dest_path: Path, status_callback: StatusCallback):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists() and dest_path.stat().st_size > 0:
        return True

    emit_status(status_callback, f"Downloading {url} -> {dest_path}")
    try:
        urllib.request.urlretrieve(url, dest_path)
        return True
    except Exception as exc:
        emit_status(status_callback, f"Download failed for {url}: {exc}")
        if dest_path.exists():
            try:
                dest_path.unlink()
            except Exception:
                pass

    try:
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(url, context=ctx) as response:
            dest_path.write_bytes(response.read())
        return True
    except Exception as exc:
        emit_status(status_callback, f"Download retry failed for {url}: {exc}")
        if dest_path.exists():
            try:
                dest_path.unlink()
            except Exception:
                pass
        return False


def load_hed_model(model_dir: Path, status_callback: StatusCallback = None):
    proto_path = model_dir / "deploy.prototxt"
    model_path = model_dir / "hed_pretrained_bsds.caffemodel"
    ok_proto = download_if_missing(HED_PROTO_URL, proto_path, status_callback)
    ok_model = download_if_missing(HED_MODEL_URL, model_path, status_callback)
    if not (ok_proto and ok_model):
        return None

    register_hed_layers()
    try:
        return cv2.dnn.readNetFromCaffe(str(proto_path), str(model_path))
    except Exception as exc:
        emit_status(status_callback, f"Failed to load HED model: {exc}")
        return None


def hed_edges(net, image_bgr):
    if net is None:
        return None

    height, width = image_bgr.shape[:2]
    blob = cv2.dnn.blobFromImage(
        image_bgr,
        scalefactor=1.0,
        size=(width, height),
        mean=(104.00698793, 116.66876762, 122.67891434),
        swapRB=False,
        crop=False,
    )
    net.setInput(blob)
    hed = net.forward()[0, 0]
    hed = cv2.resize(hed, (width, height))
    hed = cv2.normalize(hed, None, 0, 255, cv2.NORM_MINMAX)
    return hed.astype(np.uint8)


def segment_crack(gray, hed=None):
    height, width = gray.shape
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    blurred = cv2.medianBlur(enhanced, 5)

    k = max(7, (min(height, width) // 60) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    blackhat = cv2.morphologyEx(blurred, cv2.MORPH_BLACKHAT, kernel)
    blackhat = cv2.normalize(blackhat, None, 0, 255, cv2.NORM_MINMAX)
    blackhat = cv2.GaussianBlur(blackhat, (5, 5), 0)

    _, cand = cv2.threshold(
        blackhat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    if hed is not None:
        edge_thresh = np.percentile(hed, 85)
        edge_bin = (hed >= edge_thresh).astype(np.uint8)
        edge_inv = np.where(edge_bin > 0, 0, 255).astype(np.uint8)
        dist = cv2.distanceTransform(edge_inv, cv2.DIST_L2, 3)
        max_dist = max(2.0, min(height, width) * 0.01)
        cand = np.where((cand > 0) & (dist <= max_dist), 255, 0).astype(np.uint8)

    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    cand = cv2.morphologyEx(cand, cv2.MORPH_CLOSE, close_kernel, iterations=1)
    cand = cv2.morphologyEx(cand, cv2.MORPH_OPEN, close_kernel, iterations=1)
    cand = remove_small_components(cand, max(30, (height * width) // 5000))
    return cand


def remove_small_components(binary, min_area):
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    if num_labels <= 1:
        return binary

    out = np.zeros_like(binary)
    for idx in range(1, num_labels):
        area = stats[idx, cv2.CC_STAT_AREA]
        if area >= min_area:
            out[labels == idx] = 255
    return out


def zhang_suen_thinning(binary, max_iters=200):
    img = (binary > 0).astype(np.uint8)
    rows, cols = img.shape
    changed = True
    iters = 0
    while changed and iters < max_iters:
        changed = False
        iters += 1
        for step in (0, 1):
            to_remove = []
            for i in range(1, rows - 1):
                for j in range(1, cols - 1):
                    if img[i, j] != 1:
                        continue
                    p2 = img[i - 1, j]
                    p3 = img[i - 1, j + 1]
                    p4 = img[i, j + 1]
                    p5 = img[i + 1, j + 1]
                    p6 = img[i + 1, j]
                    p7 = img[i + 1, j - 1]
                    p8 = img[i, j - 1]
                    p9 = img[i - 1, j - 1]
                    neighbors = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
                    if neighbors < 2 or neighbors > 6:
                        continue
                    seq = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
                    transitions = 0
                    for k in range(8):
                        if seq[k] == 0 and seq[k + 1] == 1:
                            transitions += 1
                    if transitions != 1:
                        continue
                    if step == 0:
                        if p2 * p4 * p6 != 0:
                            continue
                        if p4 * p6 * p8 != 0:
                            continue
                    else:
                        if p2 * p4 * p8 != 0:
                            continue
                        if p2 * p6 * p8 != 0:
                            continue
                    to_remove.append((i, j))
            if to_remove:
                for i, j in to_remove:
                    img[i, j] = 0
                changed = True
    return (img * 255).astype(np.uint8)


def skeletonize(binary):
    if hasattr(cv2, "ximgproc") and hasattr(cv2.ximgproc, "thinning"):
        return cv2.ximgproc.thinning(binary)
    return zhang_suen_thinning(binary)


def width_map_from_mask(mask):
    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
    return dist * 2.0


def largest_component(binary):
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    if num_labels <= 1:
        return binary

    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    out = np.zeros_like(binary)
    out[labels == largest] = 255
    return out


def build_graph(skeleton):
    ys, xs = np.where(skeleton > 0)
    coords = list(zip(ys, xs))
    index = {coord: i for i, coord in enumerate(coords)}
    adj = [[] for _ in coords]
    for i, (y, x) in enumerate(coords):
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                neighbor = (y + dy, x + dx)
                if neighbor in index:
                    weight = math.sqrt(2.0) if dx != 0 and dy != 0 else 1.0
                    adj[i].append((index[neighbor], weight))
    return coords, adj


def dijkstra(start, adj):
    import heapq

    dist = [math.inf] * len(adj)
    parent = [-1] * len(adj)
    dist[start] = 0.0
    heap = [(0.0, start)]
    while heap:
        cur_dist, u = heapq.heappop(heap)
        if cur_dist != dist[u]:
            continue
        for v, weight in adj[u]:
            nd = cur_dist + weight
            if nd < dist[v]:
                dist[v] = nd
                parent[v] = u
                heapq.heappush(heap, (nd, v))
    return dist, parent


def longest_path_coords(skeleton):
    if np.count_nonzero(skeleton) == 0:
        return []

    skeleton = largest_component(skeleton)
    coords, adj = build_graph(skeleton)
    if not coords:
        return []

    degrees = [len(neighbors) for neighbors in adj]
    endpoints = [i for i, deg in enumerate(degrees) if deg == 1]
    start = endpoints[0] if endpoints else 0

    dist, _ = dijkstra(start, adj)
    far_a = max(endpoints, key=lambda i: dist[i]) if endpoints else int(np.argmax(dist))

    dist_b, parent = dijkstra(far_a, adj)
    far_b = (
        max(endpoints, key=lambda i: dist_b[i]) if endpoints else int(np.argmax(dist_b))
    )

    path = []
    cur = far_b
    while cur != -1:
        path.append(coords[cur])
        if cur == far_a:
            break
        cur = parent[cur]
    path.reverse()
    return path


def local_normal(path, idx):
    if len(path) == 1:
        return 0.0, -1.0
    if idx == 0:
        y1, x1 = path[idx]
        y2, x2 = path[idx + 1]
    elif idx == len(path) - 1:
        y1, x1 = path[idx - 1]
        y2, x2 = path[idx]
    else:
        y1, x1 = path[idx - 1]
        y2, x2 = path[idx + 1]

    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length == 0.0:
        return 0.0, -1.0
    return -dy / length, dx / length


def sample_along_path(path, width_map, scale, sample_count):
    if not path or sample_count <= 0:
        return []

    distances = [0.0]
    for i in range(1, len(path)):
        y1, x1 = path[i - 1]
        y2, x2 = path[i]
        distances.append(distances[-1] + math.hypot(x2 - x1, y2 - y1))

    total = distances[-1]
    if total == 0.0:
        return []

    targets = [total * (idx + 1) / (sample_count + 1) for idx in range(sample_count)]
    samples = []
    idx = 0
    for target in targets:
        while idx < len(distances) and distances[idx] < target:
            idx += 1
        if idx >= len(path):
            idx = len(path) - 1
        y, x = path[idx]
        width_px = float(width_map[y, x])
        nx, ny = local_normal(path, idx)
        samples.append(
            {
                "x": int(x),
                "y": int(y),
                "width_px": width_px,
                "width_mm": width_px * scale,
                "nx": nx,
                "ny": ny,
                "distance_px": distances[idx],
            }
        )
    return samples


def path_length(path):
    if len(path) < 2:
        return 0.0

    total = 0.0
    for idx in range(1, len(path)):
        y1, x1 = path[idx - 1]
        y2, x2 = path[idx]
        total += math.hypot(x2 - x1, y2 - y1)
    return total


def save_csv(path: Path, rows, header):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(row))
    path.write_text("\n".join(lines), encoding="ascii")


def draw_overlay(image, mask, skeleton, samples, scale):
    overlay = image.copy()
    mask_color = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    overlay = cv2.addWeighted(overlay, 1.0, mask_color, 0.35, 0)
    ys, xs = np.where(skeleton > 0)
    overlay[ys, xs] = (0, 0, 255)

    for sample in samples:
        x = sample["x"]
        y = sample["y"]
        width_px = sample["width_px"]
        nx = sample["nx"]
        ny = sample["ny"]
        half = max(3.0, width_px / 2.0)
        x1 = int(round(x - nx * half))
        y1 = int(round(y - ny * half))
        x2 = int(round(x + nx * half))
        y2 = int(round(y + ny * half))
        cv2.line(overlay, (x1, y1), (x2, y2), (255, 0, 0), 1)

        width_mm = sample["width_mm"]
        label = f"{width_mm:.2f} mm" if scale > 0 else f"{width_px:.2f} px"
        text_pos = (int(x + 3), int(y - 3))
        cv2.putText(
            overlay,
            label,
            text_pos,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            overlay,
            label,
            text_pos,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    return overlay


def process_image(
    image_path: Path,
    image_out_dir: Path,
    net,
    scale: float,
    sample_count: int,
    status_callback: StatusCallback = None,
):
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Failed to read image: {image_path}")

    emit_status(status_callback, f"Processing {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hed = hed_edges(net, image)
    mask = segment_crack(gray, hed)
    skeleton = skeletonize(mask)
    width_map = width_map_from_mask(mask)
    path_coords = longest_path_coords(skeleton)
    samples = sample_along_path(path_coords, width_map, scale, sample_count)

    image_out_dir.mkdir(parents=True, exist_ok=True)
    base = image_path.stem
    mask_path = image_out_dir / f"{base}_mask.png"
    skeleton_path = image_out_dir / f"{base}_skeleton.png"
    overlay_path = image_out_dir / f"{base}_overlay.png"
    widths_csv = image_out_dir / f"{base}_widths.csv"
    profile_csv = image_out_dir / f"{base}_profile.csv"
    samples_csv = image_out_dir / f"{base}_samples.csv"

    cv2.imwrite(str(mask_path), mask)
    cv2.imwrite(str(skeleton_path), skeleton)
    cv2.imwrite(str(overlay_path), draw_overlay(image, mask, skeleton, samples, scale))

    ys, xs = np.where(skeleton > 0)
    skeleton_widths_px = [float(width_map[y, x]) for y, x in zip(ys, xs)]
    max_width_px = max(skeleton_widths_px, default=0.0)
    mean_width_px = (
        float(sum(skeleton_widths_px) / len(skeleton_widths_px))
        if skeleton_widths_px
        else 0.0
    )
    main_path_length = path_length(path_coords)
    width_rows = []
    for y, x in zip(ys, xs):
        width_px = float(width_map[y, x])
        width_rows.append(
            [str(x), str(y), f"{width_px:.6f}", f"{width_px * scale:.6f}"]
        )
    save_csv(widths_csv, width_rows, ["x", "y", "width_px", "width_mm"])

    if path_coords:
        profile_rows = []
        dist = 0.0
        first_y, first_x = path_coords[0]
        first_width_px = float(width_map[first_y, first_x])
        profile_rows.append(
            [
                "0",
                str(first_x),
                str(first_y),
                f"{dist:.6f}",
                f"{first_width_px:.6f}",
                f"{first_width_px * scale:.6f}",
            ]
        )
        for idx in range(1, len(path_coords)):
            y1, x1 = path_coords[idx - 1]
            y2, x2 = path_coords[idx]
            dist += math.hypot(x2 - x1, y2 - y1)
            width_px = float(width_map[y2, x2])
            profile_rows.append(
                [
                    str(idx),
                    str(x2),
                    str(y2),
                    f"{dist:.6f}",
                    f"{width_px:.6f}",
                    f"{width_px * scale:.6f}",
                ]
            )
        save_csv(
            profile_csv,
            profile_rows,
            ["path_index", "x", "y", "distance_px", "width_px", "width_mm"],
        )
    else:
        profile_csv = None

    if samples:
        sample_rows = []
        for idx, sample in enumerate(samples):
            sample_rows.append(
                [
                    str(idx),
                    str(sample["x"]),
                    str(sample["y"]),
                    f"{sample['distance_px']:.6f}",
                    f"{sample['width_px']:.6f}",
                    f"{sample['width_mm']:.6f}",
                ]
            )
        save_csv(
            samples_csv,
            sample_rows,
            ["sample_index", "x", "y", "distance_px", "width_px", "width_mm"],
        )
    else:
        samples_csv = None

    emit_status(status_callback, f"Finished {image_path.name}")
    return ProcessingResult(
        input_path=image_path,
        output_dir=image_out_dir,
        mask_path=mask_path,
        skeleton_path=skeleton_path,
        overlay_path=overlay_path,
        widths_csv=widths_csv,
        profile_csv=profile_csv,
        samples_csv=samples_csv,
        skeleton_points=len(xs),
        sampled_points=len(samples),
        max_width_px=max_width_px,
        max_width_mm=max_width_px * scale,
        mean_width_px=mean_width_px,
        mean_width_mm=mean_width_px * scale,
        main_path_length_px=main_path_length,
    )


def collect_images(input_path: Path):
    if input_path.is_file():
        return [input_path]

    images = []
    for path in input_path.rglob("*"):
        if path.suffix.lower() in IMAGE_EXTS:
            images.append(path)
    return sorted(images)


def process_images(
    input_path: Path,
    out_dir: Path,
    scale: float = 0.1,
    sample_count: int = 5,
    model_dir: Optional[Path] = None,
    status_callback: StatusCallback = None,
):
    input_path = Path(input_path)
    out_dir = Path(out_dir)
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    resolved_model_dir = Path(model_dir) if model_dir else default_model_dir()
    net = load_hed_model(resolved_model_dir, status_callback)
    if net is None:
        emit_status(
            status_callback,
            "HED model unavailable, continuing without deep edge guidance.",
        )

    images = collect_images(input_path)
    if not images:
        raise FileNotFoundError(f"No supported images found in {input_path}")

    emit_status(status_callback, f"Found {len(images)} image(s).")
    input_root = input_path if input_path.is_dir() else input_path.parent
    results = []
    for idx, image_path in enumerate(images, start=1):
        relative_parent = (
            image_path.parent.relative_to(input_root)
            if input_path.is_dir()
            else Path(".")
        )
        image_out_dir = out_dir / relative_parent
        emit_status(status_callback, f"[{idx}/{len(images)}] {image_path.name}")
        results.append(
            process_image(
                image_path=image_path,
                image_out_dir=image_out_dir,
                net=net,
                scale=scale,
                sample_count=sample_count,
                status_callback=status_callback,
            )
        )
    emit_status(status_callback, f"Completed {len(results)} image(s).")
    return results


def build_parser():
    parser = argparse.ArgumentParser(description="Crack width inspector")
    parser.add_argument(
        "--input",
        type=Path,
        default=default_input_path(),
        help="Input image or directory",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=runtime_base_dir() / "outputs",
        help="Output directory",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=0.1,
        help="Millimeters per pixel",
    )
    parser.add_argument(
        "--sample-count",
        type=int,
        default=5,
        help="Sample points to annotate",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=default_model_dir(),
        help="Directory for HED model files",
    )
    return parser


def main():
    args = build_parser().parse_args()
    try:
        process_images(
            input_path=args.input,
            out_dir=args.out_dir,
            scale=args.scale,
            sample_count=args.sample_count,
            model_dir=args.model_dir,
        )
    except Exception as exc:
        print(exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
