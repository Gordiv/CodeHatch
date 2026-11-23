"""Shared parts of the event effect builders (tools/vfx/*.py), run inside Blender:
    blender --background --python tools/vfx/<effect>.py -- <out folder> [--fast]

- render_sheet(): renders an animation into one flipbook sheet (8x8 or 4x4 frames, 1024 px) with a transparent
  background, the layout Roblox's ParticleEmitter reads (FlipbookLayout Grid8x8 / Grid4x4, frames row by row);
- save_rgba(): writes a numpy image (rows top to bottom, 0..1) as PNG, for textures drawn from math (glints, glows);
- studio_world(): image-based light from Blender's own CC0 studio HDRIs (only the light: the background stays empty).
Everything is made here from code, so any texture can be changed and built again."""
import math
import os
import sys

import bpy
import numpy as np

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(ARGS[0] if ARGS else ".")
FAST = "--fast" in ARGS  # quick drafts: fewer samples
os.makedirs(OUT, exist_ok=True)

HDRI_DIR = os.path.join(os.path.dirname(bpy.app.binary_path), f"{bpy.app.version[0]}.{bpy.app.version[1]}",
                        "datafiles", "studiolights", "world")


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def studio_world(hdri: str = "studio.exr", strength: float = 1.0, rotation: float = 0.0):
    scene = bpy.context.scene
    world = bpy.data.worlds.new("Light")
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    background = nodes["Background"]
    env = nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(os.path.join(HDRI_DIR, hdri))
    mapping = nodes.new("ShaderNodeMapping")
    coords = nodes.new("ShaderNodeTexCoord")
    mapping.inputs["Rotation"].default_value[2] = rotation
    links.new(coords.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    links.new(env.outputs["Color"], background.inputs["Color"])
    background.inputs["Strength"].default_value = strength
    scene.world = world


def cycles(samples: int = 128, size: int = 128):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 24 if FAST else samples
    scene.cycles.use_denoising = True
    try:  # the graphics card when Blender can use it
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for kind in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
            try:
                prefs.compute_device_type = kind
                prefs.get_devices()
                if any(d.type == kind for d in prefs.devices):
                    for device in prefs.devices:
                        device.use = True
                    scene.cycles.device = "GPU"
                    break
            except TypeError:
                continue
    except (KeyError, AttributeError):
        pass
    scene.render.film_transparent = True
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"  # true colors, like Roblox shows them
    scene.view_settings.look = "None"


def ortho_camera(scale: float, location=(0, -10, 0)):
    bpy.ops.object.camera_add(location=location, rotation=(math.pi / 2, 0, 0))
    camera = bpy.context.active_object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = scale
    bpy.context.scene.camera = camera
    return camera


def read_png(path: str) -> np.ndarray:
    image = bpy.data.images.load(path)
    width, height = image.size
    pixels = np.array(image.pixels[:], dtype=np.float32).reshape(height, width, 4)[::-1]  # top row first
    bpy.data.images.remove(image)
    return pixels


def save_rgba(pixels: np.ndarray, path: str):
    """pixels: (height, width, 4), top row first, values 0..1 (sRGB colors, straight alpha)."""
    height, width = pixels.shape[:2]
    image = bpy.data.images.new(os.path.basename(path), width=width, height=height, alpha=True)
    image.colorspace_settings.name = "sRGB"
    image.alpha_mode = "STRAIGHT"
    image.pixels = np.clip(pixels[::-1], 0, 1).astype(np.float32).ravel()
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def render_sheet(name: str, frames: int, grid: int, pose) -> str:
    """Renders `frames` frames (pose(i, t) sets the scene for frame i, t = 0..1) into a grid x grid sheet of 1024 px."""
    size = 1024 // grid
    bpy.context.scene.render.resolution_x = bpy.context.scene.render.resolution_y = size
    sheet = np.zeros((1024, 1024, 4), dtype=np.float32)
    temp = os.path.join(OUT, "_frame.png")
    for i in range(frames):
        pose(i, i / frames)
        bpy.context.scene.render.filepath = temp
        bpy.ops.render.render(write_still=True)
        frame = read_png(temp)
        row, column = divmod(i, grid)
        sheet[row * size:(row + 1) * size, column * size:(column + 1) * size] = frame
    os.remove(temp)
    path = os.path.join(OUT, f"{name}.png")
    save_rgba(sheet, path)
    return path


def grid_coords(size: int):
    """x, y from -1 to 1 over a size x size image (y up)."""
    axis = (np.arange(size) + 0.5) / size * 2 - 1
    x, y = np.meshgrid(axis, -axis)
    return x, y


def glow_image(size: int, color, falloff: float = 3.0) -> np.ndarray:
    """A soft round glow: white-hot middle, color at the edge, alpha fading to 0 well inside the square."""
    x, y = grid_coords(size)
    r = np.sqrt(x * x + y * y)
    a = np.clip(1 - r, 0, 1) ** falloff
    core = np.clip(1 - r * 3, 0, 1) ** 2
    image = np.zeros((size, size, 4), dtype=np.float32)
    for c in range(3):
        image[..., c] = color[c] * (1 - core) + core
    image[..., 3] = a
    return image
