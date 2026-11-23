"""Meteor Shower, the event effect for a big currency (Gems) or a big event: the textures, made in Blender from code.

Run:  blender --background --python tools/vfx/meteor_shower.py -- <out folder> [--fast] [--small]
Out (all PNG with a transparent background, made for Roblox):
- CrystalTumble.png 4x4 flipbook (Cycles): a violet-blue crystal tumbling once (the crystals of an impact; the turn
                    loops, so any frame can start);
- MeteorCore.png    the head of a meteor: a white-hot core in a violet-blue glow;
- MeteorTrail.png   the tail of a meteor for a Trail: a white core with blue and violet edges and sparks in it, the same
                    all along it (along the trail: the picture's height; across: its width);
- ShockRing.png     a soft white ring with a violet edge (the wave of an impact; tinted in the game);
- Dust.png          a soft cloud of dust (a meteor that breaks up, the smoke of an impact; tinted in the game);
- Planet.png        (Cycles) a ringed planet of violet, pink and blue gas with glowing air and a halo (it rises over
                    the horizon at the start);
- NebulaCloud1-2.png big soft clouds of glowing gas with stars (pink and violet; blue and violet) for the sky;
- CrystalCluster.png (Cycles) five crystals growing out of one point (where a meteor fell close);
- Icon.png          the event's icon (512 px): the crystal with a meteor streak behind it;
- preview_*.png     pictures to look at.
--small: only the textures drawn from math (quick, the crystal needs Cycles)."""
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Quaternion

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

VIOLET = np.array((0.62, 0.38, 1.00))
BLUE = np.array((0.35, 0.62, 1.00))
WHITE = np.array((1.0, 1.0, 1.0))


# ---------- the crystal ----------

def build_crystal():
    """A long gem: a six-sided prism with a tall point on top and a short one below, flat facets."""
    mesh = bpy.data.meshes.new("Crystal")
    bm = bmesh.new()
    top = bm.verts.new((0, 0, 1.35))
    bottom = bm.verts.new((0, 0, -0.95))
    upper, lower = [], []
    for k in range(6):
        a = 2 * math.pi * k / 6
        upper.append(bm.verts.new((math.cos(a) * 0.5, math.sin(a) * 0.5, 0.45)))
        lower.append(bm.verts.new((math.cos(a) * 0.5, math.sin(a) * 0.5, -0.25)))
    for k in range(6):
        n = (k + 1) % 6
        bm.faces.new((top, upper[k], upper[n]))
        bm.faces.new((upper[k], lower[k], lower[n], upper[n]))
        bm.faces.new((lower[n], lower[k], bottom))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    crystal = bpy.data.objects.new("Crystal", mesh)
    bpy.context.collection.objects.link(crystal)
    crystal.rotation_mode = "QUATERNION"
    mat = bpy.data.materials.new("Gem")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.38, 0.16, 0.95, 1)
    bsdf.inputs["Roughness"].default_value = 0.12
    bsdf.inputs["Transmission Weight"].default_value = 0.3
    bsdf.inputs["IOR"].default_value = 1.6
    bsdf.inputs["Coat Weight"].default_value = 0.4
    # an inner glow, stronger toward the facets' middles (it reads as light inside the gem in the game)
    layer = nodes.new("ShaderNodeLayerWeight")
    layer.inputs["Blend"].default_value = 0.45
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.55, 0.3, 1.0, 1)
    ramp.color_ramp.elements[1].color = (0.15, 0.35, 1.0, 1)
    links.new(layer.outputs["Facing"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 0.35
    crystal.data.materials.append(mat)
    return crystal


def lights():
    common.studio_world("night.exr", strength=0.5)
    for location, energy, color, rotation in (((-3, -5, 3), 140, (0.75, 0.82, 1.0), (55, 0, -30)),
                                              ((3.5, 3, 1.5), 260, (1.0, 0.6, 1.0), (-70, 0, 130)),
                                              ((0, -4, -3), 60, (0.5, 0.7, 1.0), (125, 0, 0))):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.active_object
        light.data.energy = energy
        light.data.size = 3
        light.data.color = color
        light.rotation_euler = tuple(math.radians(v) for v in rotation)


def add_halo(picture, color, strength, radius=0.95, falloff=2.2):
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


def crystal_tumble(crystal):
    axis = (0.5, 0.7, 0.4)

    def pose(_, t):
        crystal.rotation_quaternion = Quaternion(axis, 2 * math.pi * t) @ Quaternion((1, 0, 0), math.radians(20))
    path = common.render_sheet("CrystalTumble", 16, 4, pose)
    sheet = common.read_png(path)
    tile = 256
    for i in range(16):
        row, column = divmod(i, 4)
        part = sheet[row * tile:(row + 1) * tile, column * tile:(column + 1) * tile]
        sheet[row * tile:(row + 1) * tile, column * tile:(column + 1) * tile] = add_halo(part, tuple(VIOLET), 0.35)
    common.save_rgba(sheet, path)
    return path


def icon(crystal):
    crystal.rotation_quaternion = Quaternion((0, 1, 0), math.radians(-18)) @ Quaternion((0, 0, 1), math.radians(20))
    bpy.context.scene.camera.data.ortho_scale = 3.9
    scene = bpy.context.scene
    scene.render.resolution_x = scene.render.resolution_y = 512
    path = os.path.join(common.OUT, "Icon.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    picture = common.read_png(path)
    x, y = common.grid_coords(picture.shape[0])
    # a meteor streak behind the crystal, from the upper right down to the lower left (its head)
    u = (-x - y) / math.sqrt(2)  # along the streak
    v = (x - y) / math.sqrt(2)  # across it
    along = np.clip((u + 0.95) / 1.5, 0, 1)
    width = 0.02 + 0.09 * along
    streak = np.exp(-(v / width) ** 2) * along ** 1.5 * (u < 0.55)
    head = np.exp(-((u - 0.5) ** 2 + v ** 2) / 0.012)
    band = np.zeros_like(picture)
    mix = np.clip(np.exp(-(v / (width * 0.4)) ** 2) + head, 0, 1)[..., None]
    band[..., :3] = VIOLET * (1 - mix) + WHITE * mix
    band[..., 3] = np.clip(streak * 0.9 + head, 0, 1)
    out = add_halo(over(picture, band), tuple(VIOLET), 0.4, radius=0.85)
    common.save_rgba(out, path)
    return path


# ---------- the textures drawn from math ----------

def meteor_core():
    size = 256
    x, y = common.grid_coords(size)
    r = np.sqrt(x * x + y * y)
    core = np.clip(1 - r / 0.18, 0, 1) ** 1.5
    glow = np.clip(1 - r, 0, 1) ** 2.4
    image = np.zeros((size, size, 4), dtype=np.float32)
    tint = np.clip(r / 0.6, 0, 1)[..., None]
    color = WHITE * (1 - tint) + (BLUE * 0.5 + VIOLET * 0.5) * tint
    image[..., :3] = color * (1 - core[..., None]) + core[..., None]
    image[..., 3] = np.clip(core + glow * 0.9, 0, 1)
    path = os.path.join(common.OUT, "MeteorCore.png")
    common.save_rgba(image, path)
    return path


def meteor_trail():
    width, height = 128, 512
    x = common.grid_coords(width)[0][0]
    core = np.exp(-(x / 0.16) ** 2)
    edge = np.exp(-(x / 0.55) ** 2)
    rng = np.random.default_rng(12)
    sparks = np.zeros((height, width))
    for _ in range(120):
        sy, sx = rng.integers(0, height), rng.normal(0, 0.35)
        sparks += np.exp(-(((np.arange(height) - sy) / 4.0) ** 2))[:, None] * np.exp(-((x - sx) / 0.04) ** 2)[None, :]
    alpha = np.clip(edge * 0.6 + core * 0.5 + sparks * 0.5, 0, 1)
    mix = np.clip(core[None, :] * 1.3 + sparks * 0.8, 0, 1)[..., None]
    side = np.clip(np.abs(x) / 0.8, 0, 1)[None, :, None]
    rim = BLUE * (1 - side) + VIOLET * side
    image = np.zeros((height, width, 4), dtype=np.float32)
    image[..., :3] = rim * (1 - mix) + WHITE * mix
    image[..., 3] = np.broadcast_to(alpha, (height, width))
    path = os.path.join(common.OUT, "MeteorTrail.png")
    common.save_rgba(image, path)
    return path


def shock_ring():
    size = 512
    x, y = common.grid_coords(size)
    r = np.sqrt(x * x + y * y)
    angle = np.arctan2(y, x)
    wobble = 0.012 * np.sin(angle * 9) + 0.008 * np.sin(angle * 17 + 1)
    band = np.exp(-((r - 0.8 - wobble) / 0.05) ** 2)
    inner = np.exp(-((r - 0.62) / 0.2) ** 2) * 0.25
    image = np.zeros((size, size, 4), dtype=np.float32)
    h = np.clip((r - 0.6) / 0.3, 0, 1)[..., None]
    image[..., :3] = WHITE * (1 - h * 0.5) + VIOLET * h * 0.5
    image[..., 3] = np.clip(band + inner, 0, 1) * (r < 0.98)
    path = os.path.join(common.OUT, "ShockRing.png")
    common.save_rgba(image, path)
    return path


def dust():
    size = 256
    x, y = common.grid_coords(size)
    r = np.sqrt(x * x + y * y)
    rng = np.random.default_rng(3)
    lumps = np.zeros_like(r)
    for _ in range(14):  # a soft cloud made of a few round puffs
        cx, cy, s = rng.normal(0, 0.25), rng.normal(0, 0.25), rng.uniform(0.25, 0.45)
        lumps = np.maximum(lumps, np.clip(1 - np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / s, 0, 1) ** 1.6)
    alpha = lumps * np.clip(1 - r / 0.95, 0, 1) ** 0.8 * 0.85
    image = np.zeros((size, size, 4), dtype=np.float32)
    image[..., :3] = 1.0
    image[..., 3] = np.clip(alpha, 0, 1)
    path = os.path.join(common.OUT, "Dust.png")
    common.save_rgba(image, path)
    return path


# ---------- the sky: a ringed planet, clouds of nebula, a cluster of crystals ----------

def planet_material():
    """Bands of violet, pink and blue gas (bent by a noise) and a thin glowing air at the edge of the disk."""
    mat = bpy.data.materials.new("Planet")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    coords = nodes.new("ShaderNodeTexCoord")
    wave = nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = 1.15
    wave.inputs["Distortion"].default_value = 2.6
    wave.inputs["Detail"].default_value = 3
    wave.inputs["Detail Scale"].default_value = 0.8
    links.new(coords.outputs["Object"], wave.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    stops = ramp.color_ramp.elements
    stops[0].position, stops[0].color = 0.0, (0.16, 0.06, 0.42, 1)
    stops[1].position, stops[1].color = 1.0, (0.30, 0.18, 0.75, 1)
    for position, color in ((0.22, (0.62, 0.38, 0.95)), (0.4, (0.95, 0.55, 0.85)), (0.55, (0.42, 0.25, 0.85)),
                            (0.72, (0.35, 0.6, 1.0)), (0.86, (0.85, 0.75, 1.0))):
        stop = stops.new(position)
        stop.color = (*color, 1)
    links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.6
    layer = nodes.new("ShaderNodeLayerWeight")
    layer.inputs["Blend"].default_value = 0.2
    rim = nodes.new("ShaderNodeMapRange")
    rim.inputs["From Min"].default_value = 0.55
    rim.inputs["From Max"].default_value = 1.0
    links.new(layer.outputs["Facing"], rim.inputs["Value"])
    bsdf.inputs["Emission Color"].default_value = (0.55, 0.6, 1.0, 1)
    links.new(rim.outputs["Result"], bsdf.inputs["Emission Strength"])
    return mat


def ring_material():
    """Rings of dust: bands of different strength with a dark gap (seen through), pale lavender and blue."""
    mat = bpy.data.materials.new("Rings")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    coords = nodes.new("ShaderNodeTexCoord")
    length = nodes.new("ShaderNodeVectorMath")
    length.operation = "LENGTH"
    links.new(coords.outputs["Object"], length.inputs[0])
    remap = nodes.new("ShaderNodeMapRange")
    remap.inputs["From Min"].default_value = 1.45
    remap.inputs["From Max"].default_value = 2.45
    links.new(length.outputs["Value"], remap.inputs["Value"])
    ramp = nodes.new("ShaderNodeValToRGB")
    links.new(remap.outputs["Result"], ramp.inputs["Fac"])
    stops = ramp.color_ramp.elements
    stops[0].position, stops[0].color = 0.0, (0.6, 0.55, 0.95, 0.0)
    stops[1].position, stops[1].color = 1.0, (0.55, 0.7, 1.0, 0.0)
    for position, color, alpha in ((0.06, (0.75, 0.7, 1.0), 0.55), (0.25, (0.95, 0.85, 1.0), 0.85),
                                   (0.42, (0.85, 0.78, 1.0), 0.7), (0.47, (0.3, 0.25, 0.5), 0.05),
                                   (0.53, (0.7, 0.8, 1.0), 0.75), (0.75, (0.6, 0.75, 1.0), 0.55), (0.93, (0.5, 0.6, 1.0), 0.25)):
        stop = stops.new(position)
        stop.color = (*color, alpha)
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(ramp.outputs["Alpha"], bsdf.inputs["Alpha"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 0.35
    bsdf.inputs["Roughness"].default_value = 0.8
    return mat


def build_planet():
    holder = bpy.data.objects.new("PlanetHolder", None)
    bpy.context.collection.objects.link(holder)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=96, ring_count=48, radius=1.0)
    sphere = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    sphere.data.materials.append(planet_material())
    sphere.parent = holder
    mesh = bpy.data.meshes.new("Rings")
    bm = bmesh.new()
    inner, outer = [], []
    for k in range(256):
        a = 2 * math.pi * k / 256
        inner.append(bm.verts.new((math.cos(a) * 1.45, math.sin(a) * 1.45, 0)))
        outer.append(bm.verts.new((math.cos(a) * 2.45, math.sin(a) * 2.45, 0)))
    for k in range(256):
        n = (k + 1) % 256
        bm.faces.new((inner[k], outer[k], outer[n], inner[n]))
    bm.to_mesh(mesh)
    bm.free()
    rings = bpy.data.objects.new("Rings", mesh)
    bpy.context.collection.objects.link(rings)
    rings.data.materials.append(ring_material())
    rings.parent = holder
    # the rings open about 20 degrees toward the camera, the whole planet leans a little
    holder.rotation_euler = (math.radians(20), math.radians(-16), 0)
    return [sphere, rings]


def planet(crystals):
    for obj in crystals:
        obj.hide_render = True
    parts = build_planet()
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 5))
    sun = bpy.context.active_object
    sun.data.energy = 3.5
    sun.data.color = (1.0, 0.95, 1.0)
    sun.rotation_euler = (math.radians(50), math.radians(-35), math.radians(-30))
    scene = bpy.context.scene
    scene.camera.data.ortho_scale = 5.4
    scene.render.resolution_x = scene.render.resolution_y = 1024
    path = os.path.join(common.OUT, "Planet.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    picture = common.read_png(path)
    common.save_rgba(add_halo(picture, tuple(VIOLET * 0.7 + BLUE * 0.3), 0.45, radius=0.6, falloff=1.6), path)
    for obj in parts:
        obj.hide_render = True
    sun.hide_render = True
    return path


def crystal_cluster(crystal):
    """Five crystals growing out of one point, the tallest in the middle (the crystals a close meteor leaves)."""
    crystal.hide_render = True
    made = []
    for x, scale, tilt, yaw in ((0, 1.2, 0, 10), (-0.42, 0.85, -24, 35), (0.45, 0.9, 26, -25), (-0.2, 0.6, -42, 70),
                                (0.24, 0.55, 40, 15)):
        copy = bpy.data.objects.new("ClusterCrystal", crystal.data)
        bpy.context.collection.objects.link(copy)
        copy.rotation_mode = "XYZ"
        copy.rotation_euler = (0, math.radians(tilt), math.radians(yaw))
        copy.scale = (scale, scale, scale)
        lift = 0.95 * scale
        copy.location = (x + math.sin(math.radians(tilt)) * lift, 0, -1.5 + math.cos(math.radians(tilt)) * lift)
        made.append(copy)
    scene = bpy.context.scene
    scene.camera.data.ortho_scale = 3.9
    scene.render.resolution_x = scene.render.resolution_y = 512
    path = os.path.join(common.OUT, "CrystalCluster.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    common.save_rgba(add_halo(common.read_png(path), tuple(VIOLET), 0.5, radius=0.9), path)
    return path, made


def value_noise(size, cells, rng):
    grid = rng.random((cells + 1, cells + 1))
    coords = np.linspace(0, cells, size, endpoint=False)
    i0 = np.floor(coords).astype(int)
    f = coords - i0
    f = f * f * (3 - 2 * f)
    i1 = np.minimum(i0 + 1, cells)
    top = grid[np.ix_(i0, i0)] * (1 - f[None, :]) + grid[np.ix_(i0, i1)] * f[None, :]
    bottom = grid[np.ix_(i1, i0)] * (1 - f[None, :]) + grid[np.ix_(i1, i1)] * f[None, :]
    return top * (1 - f[:, None]) + bottom * f[:, None]


def fbm(size, octaves, rng):
    total, amplitude, weight = np.zeros((size, size)), 1.0, 0.0
    for octave in range(octaves):
        total += amplitude * value_noise(size, 2 ** (octave + 2), rng)
        weight += amplitude
        amplitude *= 0.55
    return total / weight


def nebula_cloud(name, first, second, seed):
    """A big soft cloud of glowing gas with darker lanes and stars in it (a sky picture on a part turned to the camera)."""
    size = 1024
    rng = np.random.default_rng(seed)
    gas, tint, lanes = fbm(size, 7, rng), fbm(size, 5, rng), fbm(size, 6, rng)
    x, y = common.grid_coords(size)
    r = np.sqrt(x * x + y * y)
    mask = np.clip(1 - r / 0.95, 0, 1) ** 1.1
    density = np.clip((gas - 0.38) * 2.6, 0, 1) * mask
    density = density * (1 - 0.45 * np.clip((lanes - 0.55) * 4, 0, 1))
    alpha = density ** 1.25 * 0.9
    mix = np.clip((tint - 0.35) * 2.2, 0, 1)[..., None]
    color = np.array(first) * (1 - mix) + np.array(second) * mix
    color = color + np.clip(density - 0.6, 0, 1)[..., None] * 0.8  # bright hearts of the cloud
    for _ in range(420):
        sx, sy, radius = rng.integers(0, size), rng.integers(0, size), rng.uniform(0.6, 1.8)
        ys, xs = np.ogrid[-6:7, -6:7]
        star = np.exp(-(xs ** 2 + ys ** 2) / radius ** 2) * rng.uniform(0.5, 1.0)
        y0, x0 = max(sy - 6, 0), max(sx - 6, 0)
        y1, x1 = min(sy + 7, size), min(sx + 7, size)
        piece = star[y0 - (sy - 6):y1 - (sy - 6), x0 - (sx - 6):x1 - (sx - 6)] * mask[y0:y1, x0:x1] ** 0.3
        alpha[y0:y1, x0:x1] = np.maximum(alpha[y0:y1, x0:x1], piece)
        color[y0:y1, x0:x1] = color[y0:y1, x0:x1] * (1 - piece[..., None]) + piece[..., None]
    image = np.zeros((size, size, 4), dtype=np.float32)
    image[..., :3] = np.clip(color, 0, 1)
    image[..., 3] = np.clip(alpha, 0, 1)
    path = os.path.join(common.OUT, f"{name}.png")
    common.save_rgba(image, path)
    return path


def previews(paths):
    """The textures on a violet dusk sky, to look at."""
    sky = np.array((0.18, 0.14, 0.32))
    for name, path in paths.items():
        if isinstance(path, list):  # the variants side by side
            picture = np.concatenate([common.read_png(one) for one in path], axis=1)
        else:
            picture = common.read_png(path)
        out = np.ones_like(picture)
        out[..., :3] = picture[..., :3] * picture[..., 3:4] + sky * (1 - picture[..., 3:4])
        common.save_rgba(out, os.path.join(common.OUT, f"preview_{name}.png"))


def main():
    common.clear()
    paths = {"MeteorCore": meteor_core(), "MeteorTrail": meteor_trail(), "ShockRing": shock_ring(), "Dust": dust(),
             "NebulaCloud": [nebula_cloud("NebulaCloud1", (1.0, 0.45, 0.8), (0.55, 0.35, 1.0), 31),
                             nebula_cloud("NebulaCloud2", (0.3, 0.55, 1.0), (0.6, 0.4, 1.0), 47)]}
    if "--small" not in sys.argv:
        common.cycles(samples=128)
        common.ortho_camera(3.0)
        lights()
        crystal = build_crystal()
        paths.update({"CrystalTumble": crystal_tumble(crystal), "Icon": icon(crystal)})
        paths["CrystalCluster"], cluster = crystal_cluster(crystal)
        paths["Planet"] = planet(cluster + [crystal])
    previews(paths)
    for made in paths.values():
        for path in made if isinstance(made, list) else [made]:
            print("VFX made:", path)


main()
