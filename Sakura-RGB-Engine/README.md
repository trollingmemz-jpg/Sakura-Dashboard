# Sakura RGB Engine 0.1 — development preview
Standalone Python/Tk application with native HID enumeration (HIDAPI), Windows memory inventory (CIM), and native Linux multicolour LED class control. No OpenRGB, SignalRGB or OpenLinkHub required. Python instead of Rust for this prototype to minimise build complexity.

## Windows
Install Python 3 with Tcl/Tk, then `py -3 -m pip install -r requirements.txt` and `py -3 app.py`. For a standalone executable run `powershell -NoProfile -File build-windows.ps1` from this folder (subject to your existing execution policy). Output: `dist/Sakura-RGB-Engine.exe`. No admin or kernel driver installation is requested. Native Windows build not tested yet.

## Linux
Use Python with Tk and install requirements into a virtual environment. Run `python app.py` or `python app.py --scan`. Native lighting only works on RGB devices exposed by the OS multicolor LED class and writable by your account. Do not grant blanket device permissions or run the app as root.

## Hardware status
- MP810 candidate 09DA:FAEF: detection only, no packets sent. Confirm exact device and capture documented lighting-only commands before implementing a writable HID driver.
- Trident Z RGB: Windows CIM inventory only; does not establish lighting capability. Need exact DIMM part and motherboard, verified ENE/Aura protocol, signed low-level access mechanism and safe SMBus arbitration. No arbitrary SMBus scanning, SPD writes, or kernel driver included.
- Other USB devices: discovery only. HID interfaces may appear more than once.
- Linux multicolour LEDs: actual RGB writes through kernel LED class; not a generic USB driver.

Reports exclude device paths, serial numbers and credentials, but include reported product names, hardware IDs and RAM model information; review before sharing. No network service, telemetry, or dashboard integration yet. This is not a complete OpenRGB replacement.

Protocol research: https://github.com/apo5tol/bloody_keyboard_rgb_control (different default PID, not verified on MP810); https://gitlab.com/CalcProgrammer1/OpenRGB/-/issues/8 (RAM research); https://docs.kernel.org/leds/leds-class-multicolor.html (Linux multicolor API).
