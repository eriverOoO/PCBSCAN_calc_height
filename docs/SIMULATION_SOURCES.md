# Source-informed PCB simulation profiles

The profiles below are independent 2.5D raster test fixtures. They use public
board dimensions, component classes, and layout characteristics to broaden the
decoder test set. They do not redistribute the upstream STEP, STL, KiCad,
Gerber, product image, or rendering code and are not substitutes for a full CAD
render.

| Profile | Upstream reference | Facts used | Upstream license |
|---|---|---|---|
| `adafruit_bme280` | [Adafruit CAD Parts — product 2652](https://github.com/adafruit/Adafruit_CAD_Parts/tree/main/2652%20Adafruit%20BME280) | STL bounds (17.78 × 19.05 mm), two mounting holes, through-hole row, sensor/IC/passive height classes | MIT |
| `soldered_simple_light` | [Simple light sensor board hardware design](https://github.com/SolderedElectronics/Simple-light-sensor-board-hardware-design) | V1.1.1 Edge.Cuts (22 × 22 mm), LM393, trimmer, LDR, connectors, holes and passive distribution | TAPR Open Hardware License 1.0 for upstream hardware documentation |
| `soldered_w5500` | [Ethernet controller W5500 board hardware design](https://github.com/SolderedElectronics/Ethernet-controller-W5500-board-hardware-design) | V1.2.0 Edge.Cuts (38 × 54 mm), W5500, RJ-45, level shifter, header, holes and dense passive distribution | TAPR Open Hardware License 1.0 for upstream hardware documentation |

The camera/projector separation, explicit optical axis, focus split, custom
pattern support, turntable semantics, and ground-truth separation are adapted
as design concepts from [Hardware Design and Accurate Simulation of
Structured-Light Scanning](https://geometryprocessing.github.io/scanner-sim/).
No GPL scanner-sim rendering source is copied. The local procedural generator
and Blender boundary remain project code. Scanner-sim reports a mixed BSD/GPL
codebase and CC BY 4.0 datasets; consult its upstream license before importing
code or data directly.

These fixtures support phase-domain regression only. Their component heights,
materials, optics, and camera/projector calibration are approximations and must
not be used to claim physical millimetre accuracy.

## Generate and compare all profiles

Double-click `run_reference_board_suite.bat`, or run:

```powershell
.\run_reference_board_suite.bat
```

The command generates all three 4-view × 22-frame datasets, runs L0 and the
normal L1 stress profile, and opens:

`validation_results/open_hardware_boards/index.html`

Choose a different stress envelope with, for example:

```powershell
.\run_reference_board_suite.bat --stress-profile hard
```
