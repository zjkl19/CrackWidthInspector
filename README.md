# Crack Width Inspector

`Crack Width Inspector` is a Windows-oriented crack measurement tool for concrete surface images. It combines classical image processing with a pre-trained HED edge prior, then estimates crack width from the skeleton and distance transform. The project now provides both a command-line workflow and a simple `PySide6` desktop GUI for non-technical users.

## Features

- Automatic crack candidate enhancement and segmentation
- Optional HED deep edge prior to suppress background noise
- Skeleton extraction and pixel-level width estimation
- Main-path extraction and sampled width annotation
- Batch processing for folders while preserving subfolder structure
- Desktop GUI for customer delivery
- `PyInstaller` directory-mode packaging for Windows

## Project Structure

```text
CrackWidthInspector/
|-- crack_width_inspector.py        # Core processing logic + CLI entry
|-- crack_width_inspector_gui.py    # PySide6 desktop GUI
|-- CrackWidthInspector.spec        # PyInstaller spec
|-- build_exe.ps1                   # Packaging helper script
|-- requirements.txt                # Python dependencies
|-- models/
|   `-- hed/
|       |-- deploy.prototxt
|       `-- hed_pretrained_bsds.caffemodel
|-- docs/
|   `-- 技术说明.md
|-- crack.jpeg
|-- crack2.jpeg
`-- outputs/                        # Existing sample outputs
```

## Algorithm Pipeline

1. Convert the image to grayscale and enhance contrast with `CLAHE`.
2. Use median filtering and black-hat morphology to highlight thin dark cracks.
3. Use Otsu thresholding to build an initial crack candidate mask.
4. If the HED model is available, keep only candidate pixels that stay close to strong edge responses.
5. Skeletonize the crack mask and compute width with Euclidean distance transform.
6. Build a graph on the skeleton, extract the longest main path, and sample representative width points.
7. Export masks, overlays, and CSV tables.

## Environment Setup

Create and activate the virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Command Line Usage

Single image:

```powershell
python .\crack_width_inspector.py --input .\crack.jpeg --out-dir .\outputs
```

Folder batch processing:

```powershell
python .\crack_width_inspector.py --input .\images --out-dir .\outputs --scale 0.1 --sample-count 5
```

Arguments:

- `--input`: input image or directory
- `--out-dir`: output directory
- `--scale`: millimeters per pixel
- `--sample-count`: number of annotated sampling points
- `--model-dir`: HED model directory

## GUI Usage

Run the desktop GUI:

```powershell
python .\crack_width_inspector_gui.py
```

GUI workflow:

1. Select one image or a folder.
2. Select an output directory.
3. Enter `scale (mm/px)` and `sample count`.
4. Click `Start`.
5. Review the overlay preview and open the output directory if needed.

## Output Files

For every input image, the tool generates:

- `*_mask.png`: final crack mask
- `*_skeleton.png`: crack skeleton
- `*_overlay.png`: width annotation overlay
- `*_widths.csv`: width values on every skeleton pixel
- `*_profile.csv`: width profile along the main path
- `*_samples.csv`: sampled representative measurement points

When processing a folder, the output directory mirrors the input subfolder structure to avoid filename collisions.

## Build EXE

Build the Windows directory-mode executable:

```powershell
.\build_exe.ps1
```

The packaged application will be created under `dist\CrackWidthInspector\`.

## Notes

- Width results in `mm` are meaningful only after proper scale calibration.
- The main-path profile focuses on the dominant crack branch, not every branch in a complex crack network.
- If the bundled HED model is missing, the tool falls back to morphology-only segmentation.

## Documentation

Detailed technical notes are available at [docs/技术说明.md](docs/%E6%8A%80%E6%9C%AF%E8%AF%B4%E6%98%8E.md).
