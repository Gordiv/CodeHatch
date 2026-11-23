"""Lucky Breeze, the event effect for a luck boost: the textures, made in Blender from code.

Run:  blender --background --python tools/vfx/lucky_breeze.py -- <out folder> [--fast] [--small]
Out (all PNG with a transparent background, made for Roblox):
- CloverTumble.png 4x4 flipbook (Cycles): a four-leaf clover tumbling once around a slanted axis (the leaves the wind
                   carries; the turn loops, so any frame can start);
- CloverTurn.png   4x4 flipbook (Cycles): the clover turning once around its upright axis, with a soft gold glow
                   (the little clover over each egg);
- Rainbow.png      a soft rainbow band for a Beam (red outside, violet inside), the same all along the beam; turned a
                   quarter to the left (a Beam lays the picture's height along its length), red on the left;
- WindStreak.png   a thin soft streak of wind, upright (a particle that flies along its length);
- Wisp.png         a ribbon of wind for a Trail: a bright soft core with mint-green edges and fine glitter, the same all
                   along it (along the trail: the picture's height; across: its width);
- LightShafts.png  golden rays of sun for a Beam from the clouds to the ground (along the beam: the picture's height,
                   soft at both ends; across: rays of different widths);
- Icon.png         the event's icon (512 px): the clover with a small rainbow behind it and a gold glow;
- preview_*.png    pictures to look at.
The gold glints, the gold glow and the gold ring come from Coin Storm (the same look, already uploaded)."""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Quaternion

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

GOLD = np.array((1.0, 0.82, 0.32))
RAINBOW = [  # from the inside of the arc to the outside
    (0.0, (0.58, 0.36, 1.00)),
    (0.2, (0.28, 0.52, 1.00)),
    (0.4, (0.30, 0.95, 0.45)),
    (0.6, (1.00, 0.93, 0.30)),
    (0.8, (1.00, 0.58, 0.20)),
    (1.0, (1.00, 0.26, 0.26)),
]


# ---------- the clover ----------

def heart_outline(n=140):
    """A leaflet: a heart with its point at the middle of the clover and its two lobes outward (+y), about 1 long."""
    points = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        points.append((x / 29 * 1.08, (y + 17) / 29))
    # a few smoothing passes round the notch (a sharp notch makes a spike in the rounded edge)
    outline = np.array(points)
    for _ in range(8):
        outline = 0.5 * outline + 0.25 * (np.roll(outline, 1, axis=0) + np.roll(outline, -1, axis=0))
    return [tuple(point) for point in outline]


def math_node(nodes, operation, *values):
    node = nodes.new("ShaderNodeMath")
    node.operation = operation
    for i, value in enumerate(values):
        if value is not None:
            node.inputs[i].default_value = value
    return node


def leaf_material():
    """Rich green, lighter toward the tips, with the pale chevron a clover leaflet has, a soft sheen and fine veins."""
    mat = bpy.data.materials.new("Leaf")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    coords = nodes.new("ShaderNodeTexCoord")
    xyz = nodes.new("ShaderNodeSeparateXYZ")
    links.new(coords.outputs["Object"], xyz.inputs["Vector"])
    # the chevron: a pale band along y = 0.42 + 0.55 |x|
    abs_x = math_node(nodes, "ABSOLUTE", None)
    links.new(xyz.outputs["X"], abs_x.inputs[0])
    line = math_node(nodes, "MULTIPLY_ADD", None, 0.55, 0.42)
    links.new(abs_x.outputs[0], line.inputs[0])
    off = math_node(nodes, "SUBTRACT", None, None)
    links.new(xyz.outputs["Y"], off.inputs[0])
    links.new(line.outputs[0], off.inputs[1])
    abs_off = math_node(nodes, "ABSOLUTE", None)
    links.new(off.outputs[0], abs_off.inputs[0])
    band = nodes.new("ShaderNodeMapRange")
    band.inputs["From Min"].default_value = 0.0
    band.inputs["From Max"].default_value = 0.13
    band.inputs["To Min"].default_value = 0.45
    band.inputs["To Max"].default_value = 0.0
    links.new(abs_off.outputs[0], band.inputs["Value"])
    # darker at the middle, brighter at the tips
    tips = nodes.new("ShaderNodeMix")
    tips.data_type = "RGBA"
    tips.inputs["A"].default_value = (0.02, 0.24, 0.04, 1)
    tips.inputs["B"].default_value = (0.08, 0.52, 0.08, 1)
    links.new(xyz.outputs["Y"], tips.inputs["Factor"])
    chevron = nodes.new("ShaderNodeMix")
    chevron.data_type = "RGBA"
    chevron.inputs["B"].default_value = (0.62, 0.92, 0.48, 1)
    links.new(tips.outputs["Result"], chevron.inputs["A"])
    links.new(band.outputs["Result"], chevron.inputs["Factor"])
    links.new(chevron.outputs["Result"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.42
    bsdf.inputs["Sheen Weight"].default_value = 0.5
    bsdf.inputs["Sheen Tint"].default_value = (1.0, 0.95, 0.7, 1)
    bsdf.inputs["Subsurface Weight"].default_value = 0.15
    bsdf.inputs["Coat Weight"].default_value = 0.25
    # fine veins
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 70
    noise.inputs["Detail"].default_value = 6
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.01
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def stem_material():
    mat = bpy.data.materials.new("Stem")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.08, 0.38, 0.06, 1)
    bsdf.inputs["Roughness"].default_value = 0.5
    bsdf.inputs["Sheen Weight"].default_value = 0.3
    return mat


def leaflet(name, mat):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "2D"
    curve.fill_mode = "BOTH"
    curve.extrude = 0.016
    curve.bevel_depth = 0.008
    curve.bevel_resolution = 2
    spline = curve.splines.new("POLY")
    outline = heart_outline()
    spline.points.add(len(outline) - 1)
    for point, (x, y) in zip(spline.points, outline):
        point.co = (x, y, 0, 1)
    spline.use_cyclic_u = True
    curve.materials.append(mat)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    return obj


def build_clover():
    """Four heart-shaped leaflets on the diagonals, each lifted a little (a soft cup), and a short curved stem."""
    holder = bpy.data.objects.new("Clover", None)
    bpy.context.collection.objects.link(holder)
    holder.rotation_mode = "QUATERNION"
    leaf = leaf_material()
    for k in range(4):
        angle = math.radians(45 + 90 * k)
        part = leaflet(f"Leaflet{k}", leaf)
        part.rotation_euler = (math.radians(14), 0, angle - math.pi / 2)
        part.location = (math.cos(angle) * 0.03, math.sin(angle) * 0.03, 0)
        part.parent = holder
    curve = bpy.data.curves.new("Stem", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.028
    curve.bevel_resolution = 3
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(1)
    for point, co in zip(spline.bezier_points, ((0, 0, -0.02), (0.14, -0.86, -0.22))):
        point.co = co
        point.handle_left_type = point.handle_right_type = "AUTO"
    curve.materials.append(stem_material())
    stem = bpy.data.objects.new("Stem", curve)
    bpy.context.collection.objects.link(stem)
    stem.parent = holder
    return holder


FACE = Quaternion((1, 0, 0), math.radians(90))  # the clover's face toward the camera (it looks along +y)


def lights():
    common.studio_world("forest.exr", strength=0.7)
    bpy.ops.object.light_add(type="AREA", location=(-3.0, -5.0, 4.0))
    key = bpy.context.active_object
    key.data.energy = 260
    key.data.size = 5
    key.data.color = (1.0, 0.96, 0.86)
    key.rotation_euler = (math.radians(55), 0, math.radians(-30))
    bpy.ops.object.light_add(type="AREA", location=(3.0, 3.0, 2.5))
    rim = bpy.context.active_object
    rim.data.energy = 220
    rim.data.size = 2
    rim.data.color = (1.0, 0.88, 0.55)
    rim.rotation_euler = (math.radians(-65), 0, math.radians(135))


def add_halo(picture, color, strength, radius=0.95, falloff=2.2):
    """A soft glow under a rendered picture (numpy, top row first)."""
    size = picture.shape[0]
    halo = common.glow_image(size, color, falloff=falloff)
    x, y = common.grid_coords(size)
    r = np.sqrt(x * x + y * y) / radius
    halo[..., 3] = np.clip(1 - r, 0, 1) ** falloff * strength
    return over(picture, halo)


def over(top, under):
    alpha = top[..., 3:4]
    out = np.zeros_like(top)
    out[..., 3:4] = alpha + under[..., 3:4] * (1 - alpha)
    safe = np.maximum(out[..., 3:4], 1e-4)
    out[..., :3] = (top[..., :3] * alpha + under[..., :3] * under[..., 3:4] * (1 - alpha)) / safe
    return out


def halo_sheet(path, strength):
    sheet = common.read_png(path)
    tile = 256
    for i in range(16):
        row, column = divmod(i, 4)
        part = sheet[row * tile:(row + 1) * tile, column * tile:(column + 1) * tile]
        sheet[row * tile:(row + 1) * tile, column * tile:(column + 1) * tile] = add_halo(part, tuple(GOLD), strength)
    common.save_rgba(sheet, path)


def clover_tumble(clover):
    axis = (0.62, 0.34, 0.71)

    def pose(_, t):
        clover.rotation_quaternion = Quaternion(axis, 2 * math.pi * t) @ FACE
    path = common.render_sheet("CloverTumble", 16, 4, pose)
    halo_sheet(path, 0.22)
    return path


def clover_turn(clover):
    def pose(_, t):
        clover.rotation_quaternion = Quaternion((0, 0, 1), 2 * math.pi * t) @ Quaternion((1, 0, 0), math.radians(78))
    path = common.render_sheet("CloverTurn", 16, 4, pose)
    halo_sheet(path, 0.45)
    return path


def icon(clover):
    clover.rotation_quaternion = Quaternion((0, 1, 0), math.radians(-14)) @ Quaternion((0, 0, 1), math.radians(12)) @ FACE
    scene = bpy.context.scene
    scene.render.resolution_x = scene.render.resolution_y = 512
    path = os.path.join(common.OUT, "Icon.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    picture = common.read_png(path)
    size = picture.shape[0]
    x, y = common.grid_coords(size)
    # a small rainbow arc behind the clover
    r = np.sqrt(x * x + (y + 0.25) ** 2)
    across = np.clip((r - 0.62) / 0.3, 0, 1)
    arc = np.zeros_like(picture)
    for c in range(3):
        arc[..., c] = np.interp(across, [p for p, _ in RAINBOW], [color[c] for _, color in RAINBOW])
    arc[..., 3] = np.sin(np.pi * across) ** 0.8 * 0.9 * (y > -0.35) * ((r > 0.62) & (r < 0.92))
    out = add_halo(over(picture, arc), tuple(GOLD), 0.4, radius=0.85)
    common.save_rgba(out, path)
    return path


# ---------- the small textures ----------

def rainbow():
    width, height = 64, 256  # upright: across the band is the picture's height (inside at the bottom)
    v = 1 - (np.arange(height) + 0.5) / height
    across = np.clip((v - 0.1) / 0.8, 0, 1)
    color = np.stack([np.interp(across, [p for p, _ in RAINBOW], [c[k] for _, c in RAINBOW]) for k in range(3)], -1)
    alpha = np.sin(np.pi * np.clip((v - 0.04) / 0.92, 0, 1)) ** 0.9 * 0.9
    alpha = alpha + 0.12 * np.exp(-((v - 0.03) / 0.06) ** 2)  # a faint light just inside the arc, like a real one
    image = np.zeros((height, width, 4), dtype=np.float32)
    image[..., :3] = color[:, None, :]
    image[..., 3] = np.clip(alpha, 0, 1)[:, None]
    path = os.path.join(common.OUT, "Rainbow.png")
    common.save_rgba(np.ascontiguousarray(np.rot90(image, k=1)), path)
    return path


def wind_streak():
    size = 256
    x, y = common.grid_coords(size)
    head = np.clip((y + 1) / 2, 0, 1)  # brighter toward the front (the top)
    alpha = np.exp(-(x / 0.07) ** 2) * np.sin(np.pi * head) ** 1.2 * (0.35 + 0.65 * head)
    image = np.zeros((size, size, 4), dtype=np.float32)
    image[..., 0], image[..., 1], image[..., 2] = 1.0, 0.98, 0.88
    image[..., 3] = np.clip(alpha, 0, 1)
    path = os.path.join(common.OUT, "WindStreak.png")
    common.save_rgba(image, path)
    return path


def wisp():
    width, height = 128, 512
    x, y = common.grid_coords(width)[0][0], np.linspace(0, 1, height)
    core = np.exp(-(x / 0.22) ** 2)  # across
    edge = np.exp(-(x / 0.6) ** 2)
    rng = np.random.default_rng(4)
    glitter = np.zeros((height, width))
    for _ in range(90):  # fine glitter along the ribbon
        gy, gx = rng.integers(0, height), rng.normal(0, 0.3)
        glitter += np.exp(-(((np.arange(height) - gy) / 3.0) ** 2))[:, None] * np.exp(-((x - gx) / 0.05) ** 2)[None, :]
    alpha = np.clip(edge * 0.55 + core * 0.45 + glitter * 0.6, 0, 1)
    mix = np.clip(core[None, :] * 1.2 + glitter, 0, 1)[..., None]
    mint, white = np.array((0.55, 1.0, 0.7)), np.array((1.0, 0.97, 0.82))
    image = np.zeros((height, width, 4), dtype=np.float32)
    image[..., :3] = mint * (1 - mix) + white * mix
    image[..., 3] = np.broadcast_to(alpha, (height, width))
    path = os.path.join(common.OUT, "Wisp.png")
    common.save_rgba(image, path)
    return path


def light_shafts():
    width, height = 512, 512
    u = (np.arange(width) + 0.5) / width
    t = (np.arange(height) + 0.5) / height  # along the beam
    rng = np.random.default_rng(9)
    rays = np.zeros(width)
    for _ in range(18):  # rays of different widths and strengths
        center, size, strength = rng.uniform(0.08, 0.92), rng.uniform(0.008, 0.045), rng.uniform(0.3, 1.0)
        rays += strength * np.exp(-((u - center) / size) ** 2)
    rays = np.clip(rays, 0, 1) * np.sin(np.pi * u) ** 0.6  # soft sides
    along = np.sin(np.pi * t) ** 0.8  # soft at both ends (it does not matter which end is up)
    image = np.zeros((height, width, 4), dtype=np.float32)
    image[..., 0], image[..., 1], image[..., 2] = 1.0, 0.88, 0.58
    image[..., 3] = np.clip(along[:, None] * rays[None, :] * 0.8, 0, 1)
    path = os.path.join(common.OUT, "LightShafts.png")
    common.save_rgba(image, path)
    return path


def previews(paths):
    """The textures on a day sky, to look at."""
    sky = np.array((0.45, 0.68, 0.95))
    for name in ("CloverTumble", "CloverTurn", "Icon", "WindStreak", "Wisp", "LightShafts"):
        if name not in paths:
            continue
        picture = common.read_png(paths[name])
        out = np.ones_like(picture)
        out[..., :3] = picture[..., :3] * picture[..., 3:4] + sky * (1 - picture[..., 3:4])
        common.save_rgba(out, os.path.join(common.OUT, f"preview_{name}.png"))
    band = np.rot90(common.read_png(paths["Rainbow"]), k=-1)  # upright again
    band = np.repeat(band, 8, axis=1)
    out = np.ones_like(band)
    out[..., :3] = band[..., :3] * band[..., 3:4] * 0.6 + sky * (1 - band[..., 3:4] * 0.6)  # as in the game: see-through
    common.save_rgba(out, os.path.join(common.OUT, "preview_Rainbow.png"))


def main():
    common.clear()
    paths = {"Rainbow": rainbow(), "WindStreak": wind_streak(), "Wisp": wisp(), "LightShafts": light_shafts()}
    if "--small" not in sys.argv:  # --small: only the textures drawn from math (quick, the clover needs Cycles)
        common.cycles(samples=96)
        common.ortho_camera(2.7)
        lights()
        clover = build_clover()
        paths.update({"CloverTumble": clover_tumble(clover), "CloverTurn": clover_turn(clover), "Icon": icon(clover)})
    previews(paths)
    for path in paths.values():
        print("VFX made:", path)


main()
