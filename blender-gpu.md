# Blender GPU Rendering

Goal: Cycles renders on the Radeon Pro (Navi 14, `gfx1012`, RDNA1) using HIP.

Status: works with Blender 5.0.1 from Ubuntu 26.04, verified 2026-11-03.

## Setup

```sh
sudo apt install libamdhip64-7 hipcc rocminfo
```

Then restart Blender, and in Preferences → System → Cycles Render Devices
pick HIP and check "AMD Radeon Graphics".

Leave the CPU unchecked. In a test render, adding the CPU made it only 8-15%
faster, and it keeps all CPU cores busy and the fans loud for the whole
render. The CPU alone was 2-3 times slower than the GPU:

| Devices | Seconds |
|---|---|
| GPU | 63, 64 |
| GPU + CPU | 54, 59 |
| CPU | 121, then 209 right after while hot |

The test was 1280×720, 512 samples without adaptive sampling or denoising,
of a glass Suzanne with subdivision level 3 over a plane.

## Why those packages

Without them, the HIP tab says "No compatible GPUs found for Cycles". Ubuntu's
`blender` package is built with HIP support but doesn't depend on any of it:

- `libamdhip64-7` is the HIP runtime. Blender loads `libamdhip64.so.7` (or
  `.so.6`) when it starts and shows no HIP devices if it can't.
- `hipcc` compiles the Cycles kernels. Ubuntu's Blender ships no precompiled
  HIP kernels, only their source, so it builds them for the GPU on first use.
  `hipcc` is a wrapper around clang, which is why the install pulls in clang
  and LLVM 21, and why you see clang running the first time you render.
  The first render took about two minutes because of this. The result is
  cached in `~/.cache/cycles/kernels/`, so it's only done again when Blender
  or the GPU changes.
- `rocminfo` isn't needed by Blender. It shows whether ROCm sees the GPU: it
  should list `gfx1012`.

No `render` group membership is needed: logind gives the logged in user access
to `/dev/kfd` and `/dev/dri/renderD*`.

ROCm doesn't officially support `gfx1012`, but Ubuntu's ROCm build works with
it.

## Checking it from the command line

This renders the default scene on the GPU without opening a window:

```sh
cat > /tmp/hip.py <<'EOF'
import bpy
p = bpy.context.preferences.addons['cycles'].preferences
p.compute_device_type = 'HIP'
p.get_devices()
for d in p.devices:
    d.use = d.type == 'HIP'
    print(d.type, d.name, d.use)
s = bpy.context.scene
s.render.engine = 'CYCLES'
s.cycles.device = 'GPU'
s.render.filepath = '/tmp/hip.png'
bpy.ops.render.render(write_still=True)
EOF
blender -b --factory-startup -P /tmp/hip.py
```

It should print `HIP AMD Radeon Graphics True` and save `/tmp/hip.png`.
