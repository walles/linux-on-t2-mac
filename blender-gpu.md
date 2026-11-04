# Blender GPU Rendering

Goal: Cycles renders on the Radeon Pro (Navi 14, `gfx1012`, RDNA1) using HIP,
with denoising.

Status: works with the Blender Foundation's snap, Blender 5.2.3 LTS, verified
2026-11-04.

## Setup

```sh
sudo snap install blender --channel=5.2lts/stable --classic
sudo apt install libamdhip64-7 rocminfo
```

Then in Preferences → System → Cycles Render Devices pick HIP and check "AMD
Radeon Graphics". OpenImageDenoise is available under Render Properties →
Sampling → Denoise.

Leave the CPU unchecked. In a test render, adding the CPU made it only 8-15%
faster, and it keeps all CPU cores busy and the fans loud for the whole
render. The CPU alone was 2-3 times slower than the GPU:

| Devices | Seconds |
|---|---|
| GPU | 63, 64 |
| GPU + CPU | 54, 59 |
| CPU | 121, then 209 right after while hot |

The test was with Ubuntu's Blender 5.0.1, 1280×720, 512 samples without
adaptive sampling or denoising, of a glass Suzanne with subdivision level 3
over a plane.

## Why the snap and not Ubuntu's blender

Ubuntu's `blender` package is built without OpenImageDenoise, and OIDN isn't
packaged in Ubuntu, so Cycles has no denoiser there. The other denoiser,
OptiX, is NVIDIA only. The snap is the official build, with OIDN. It has
classic confinement, so it can load the system HIP runtime.

The snap also ships precompiled HIP kernels, including
`kernel_gfx1012.fatbin.zst`, so no `hipcc` is needed. Ubuntu's blender has
only the kernel source and compiles it with `hipcc` on the first render,
which took about two minutes.

## Why those packages

- `libamdhip64-7` is the HIP runtime. The snap doesn't bundle it. Without
  it, the HIP tab says "No compatible GPUs found for Cycles".
- `rocminfo` isn't needed by Blender. It shows whether ROCm sees the GPU: it
  should list `gfx1012`.

No `render` group membership is needed: logind gives the logged in user access
to `/dev/kfd` and `/dev/dri/renderD*`.

ROCm doesn't officially support `gfx1012`, but Ubuntu's ROCm build works with
it.

## Checking it from the command line

This renders the default scene on the GPU with denoising, without opening a
window:

```sh
cat > /tmp/hip.py <<'EOF'
import bpy, _cycles
print('OIDN', _cycles.with_openimagedenoise)
p = bpy.context.preferences.addons['cycles'].preferences
p.compute_device_type = 'HIP'
p.get_devices()
for d in p.devices:
    d.use = d.type == 'HIP'
    print(d.type, d.name, d.use)
s = bpy.context.scene
s.render.engine = 'CYCLES'
s.cycles.device = 'GPU'
s.cycles.use_denoising = True
s.cycles.denoiser = 'OPENIMAGEDENOISE'
s.render.filepath = '/tmp/hip.png'
bpy.ops.render.render(write_still=True)
EOF
blender -b --factory-startup -P /tmp/hip.py
```

It should print `OIDN True` and `HIP AMD Radeon Graphics True`, and save
`/tmp/hip.png`.
