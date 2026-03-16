# Crack Width Inspector / 裂缝宽度检测系统

`Crack Width Inspector` 是一个面向 Windows 的混凝土裂缝宽度检测项目。它采用“传统图像处理 + 预训练 HED 边缘先验”的混合方案，对裂缝图像进行自动分割、骨架提取、宽度估计和结果导出。当前项目同时提供命令行处理方式和适合客户交付的 `PySide6` 桌面界面。

`Crack Width Inspector` is a Windows-oriented crack measurement tool for concrete surface images. It combines classical image processing with a pre-trained HED edge prior, then estimates crack width from the skeleton and distance transform. The project now provides both a command-line workflow and a customer-facing `PySide6` desktop GUI.

## 中文说明

### 功能特点

- 自动完成裂缝候选增强、分割、骨架提取和宽度估计
- 支持 HED 深度边缘先验，降低复杂背景误检
- 支持单张图片或文件夹批处理
- 导出掩膜图、骨架图、叠加标注图和 CSV 数据表
- 提供适合交付客户使用的桌面 GUI
- 支持 `PyInstaller` 目录版 Windows 打包

### 项目结构

```text
CrackWidthInspector/
|-- crack_width_inspector.py        # 核心处理逻辑 + CLI 入口
|-- crack_width_inspector_gui.py    # PySide6 桌面 GUI
|-- CrackWidthInspector.spec        # PyInstaller 打包配置
|-- build_exe.ps1                   # 打包脚本
|-- requirements.txt                # Python 依赖
|-- models/
|   `-- hed/
|       |-- deploy.prototxt
|       `-- hed_pretrained_bsds.caffemodel
|-- docs/
|   `-- 技术说明.md
|-- crack.jpeg
|-- crack2.jpeg
`-- outputs/                        # 样例输出目录
```

### 算法流程

1. 将输入图像转为灰度图，并使用 `CLAHE` 增强局部对比度。
2. 使用中值滤波和黑帽变换突出暗线状裂缝。
3. 通过 `Otsu` 阈值分割得到初始裂缝候选区域。
4. 若 HED 模型可用，则保留靠近强边缘响应的候选像素。
5. 对裂缝掩膜进行骨架化，并通过欧氏距离变换计算骨架点宽度。
6. 在骨架图上提取最长主路径，并进行等距采样。
7. 导出掩膜图、骨架图、叠加图和 CSV 数据。

### 环境安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 命令行运行

单张图片：

```powershell
python .\crack_width_inspector.py --input .\crack.jpeg --out-dir .\outputs
```

文件夹批处理：

```powershell
python .\crack_width_inspector.py --input .\images --out-dir .\outputs --scale 0.1 --sample-count 5
```

主要参数：

- `--input`：输入图片或目录
- `--out-dir`：输出目录
- `--scale`：像素到毫米的换算系数，单位 `mm/px`
- `--sample-count`：沿主路径标注的采样点数量
- `--model-dir`：HED 模型目录

### GUI 运行

```powershell
python .\crack_width_inspector_gui.py
```

GUI 使用流程：

1. 选择单张裂缝图像或一个图片文件夹。
2. 选择结果输出目录。
3. 设置 `标定系数 (mm/px)` 和 `采样点数`。
4. 点击“开始检测”。
5. 在界面中查看结果总览、叠加图预览、关键统计和运行日志。

### 输出文件说明

每张输入图像会生成以下文件：

- `*_mask.png`：最终裂缝掩膜
- `*_skeleton.png`：裂缝骨架图
- `*_overlay.png`：宽度叠加标注图
- `*_widths.csv`：所有骨架点宽度数据
- `*_profile.csv`：主路径沿程宽度剖面
- `*_samples.csv`：代表性采样点宽度

批处理时，输出目录会保留输入目录的层级结构，避免同名文件互相覆盖。

### 打包 EXE

```powershell
.\build_exe.ps1
```

打包后的目录版程序位于：

```text
dist\CrackWidthInspector\
```

### 整理发布包

```powershell
.\build_release.ps1
```

执行后会生成：

```text
release\CrackWidthInspector-v1.0.0-win64\
release\CrackWidthInspector-v1.0.0-win64.zip
```

发布包中包含主程序、客户使用说明、技术文档、示例图片和空的输出目录。

### 注意事项

- `mm` 结果依赖 `scale` 参数，若未做标定，则毫米值仅作估算。
- 当前主路径分析聚焦于主要裂缝分支，不覆盖所有复杂分叉。
- 若打包时未携带 HED 模型，系统会退化为纯形态学分割。

### 详细文档

更多技术细节请参见 [docs/技术说明.md](docs/%E6%8A%80%E6%9C%AF%E8%AF%B4%E6%98%8E.md)。

## English

### Features

- Automatic crack candidate enhancement, segmentation, skeleton extraction, and width estimation
- Optional HED deep edge prior to suppress background noise
- Supports both single-image and batch folder processing
- Exports masks, skeletons, overlays, and CSV tables
- Customer-facing desktop GUI built with `PySide6`
- Windows packaging via `PyInstaller` directory mode

### Project Structure

```text
CrackWidthInspector/
|-- crack_width_inspector.py
|-- crack_width_inspector_gui.py
|-- CrackWidthInspector.spec
|-- build_exe.ps1
|-- requirements.txt
|-- models/hed/
|-- docs/技术说明.md
`-- outputs/
```

### Algorithm Pipeline

1. Convert the input image to grayscale and enhance local contrast with `CLAHE`.
2. Use median filtering and black-hat morphology to highlight thin dark cracks.
3. Generate an initial crack candidate mask with Otsu thresholding.
4. If the HED model is available, keep only candidate pixels close to strong edge responses.
5. Skeletonize the crack mask and compute widths using Euclidean distance transform.
6. Extract the dominant main path and sample representative measurement points.
7. Export masks, overlays, and CSV tables.

### Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### CLI Usage

```powershell
python .\crack_width_inspector.py --input .\crack.jpeg --out-dir .\outputs
```

### GUI Usage

```powershell
python .\crack_width_inspector_gui.py
```

### Build EXE

```powershell
.\build_exe.ps1
```

The packaged directory-mode application will be created in `dist\CrackWidthInspector\`.

### Build Release Package

```powershell
.\build_release.ps1
```

This will generate:

```text
release\CrackWidthInspector-v1.0.0-win64\
release\CrackWidthInspector-v1.0.0-win64.zip
```

The release package includes the application, customer quick-start guide, technical documents, sample images, and an empty output folder.

### Notes

- Width values in `mm` are meaningful only after proper scale calibration.
- The current path analysis focuses on the dominant crack branch.
- If the bundled HED model is missing, the tool falls back to morphology-only segmentation.
