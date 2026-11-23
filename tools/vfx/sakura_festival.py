"""Sakura Festival, the event effect for "everything x2" or a weekend event: the textures, made in Blender from code.

Run:  blender --background --python tools/vfx/sakura_festival.py -- <out folder> [--fast] [--small] [--backdrop]
Out (all PNG with a transparent background, made for Roblox):
- PetalTumble.png  4x4 flipbook (Cycles): a cherry petal (a notched teardrop, pink to white, light shining through)
                   tumbling once (the turn loops, so any frame can start);
- Lantern.png      4x4 flipbook (Cycles): a red paper lantern lit from inside, swaying a little, its light flickering;
- Blossom.png      (Cycles) a big open cherry blossom with a gold heart and a soft pink glow (the start, the icon);
- SakuraTree.png   (Cycles) a cherry tree in full bloom, for the horizon (a picture on a part turned to the camera);
- Moon.png         a big pale full moon in a pink halo;
- Mountain.png     a big snow-capped mountain (like Mount Fuji) fading into pink mist (2:1, the horizon behind the trees);
- Pagoda.png       (Cycles) a five-roof pagoda with warm lit windows (the horizon);
- Torii.png        (Cycles) a red torii gate (the horizon);
- Mist.png         a soft wide band of pink mist (wider than tall) for the horizon;
- Icon.png         the event's icon (512 px): the blossom;
- preview_*.png    pictures to look at.
--small: only the textures drawn from math (quick, the rest needs Cycles)."""
import math
import os
import random
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Quaternion, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

PINK = np.array((1.0, 0.62, 0.78))
WARM = np.array((1.0, 0.82, 0.62))


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


def halo_sheet(path, color, strength):
    sheet = common.read_png(path)
    tile = 256
    for i in range(16):
        row, column = divmod(i, 4)
        part = sheet[row * tile:(row + 1) * tile, column * tile:(column + 1) * tile]
        sheet[row * tile:(row + 1) * tile, column * tile:(column + 1) * tile] = add_halo(part, color, strength)
    common.save_rgba(sheet, path)


# ---------- the petal and the blossom ----------

def petal_outline(n=48):
    """A cherry petal: narrow at the base, widest near the top, a round top with a small notch in the middle
    (y: 0 base .. 1 top). Right side from the base up, then the left side back down."""
    right = []
    for k in range(n + 1):  # the side: from the base to the widest point
        y = 0.78 * k / n
        right.append((0.40 * math.sin(math.pi / 2 * (y / 0.78)) ** 0.75 + 0.01, y))
    for k in range(1, n + 1):  # the round top, to the notch
        a = math.pi / 2 * k / n
        x = 0.41 * math.cos(a) * (1 - 0.82 * (k / n) ** 4)
        y = 0.78 + 0.21 * math.sin(a)
        right.append((max(x, 0.0), y - 0.09 * (k / n) ** 6))
    left = [(-x, y) for x, y in reversed(right[:-1])]
    return right + left[1:]


def petal_material():
    mat = bpy.data.materials.new("Petal")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    coords = nodes.new("ShaderNodeTexCoord")
    xyz = nodes.new("ShaderNodeSeparateXYZ")
    links.new(coords.outputs["Object"], xyz.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    stops = ramp.color_ramp.elements
    stops[0].position, stops[0].color = 0.0, (0.95, 0.22, 0.48, 1)
    stops[1].position, stops[1].color = 0.85, (1.0, 0.72, 0.84, 1)
    links.new(xyz.outputs["Y"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.45
    bsdf.inputs["Subsurface Weight"].default_value = 0.35
    bsdf.inputs["Sheen Weight"].default_value = 0.6
    bsdf.inputs["Sheen Tint"].default_value = (1.0, 0.85, 0.9, 1)
    bsdf.inputs["Transmission Weight"].default_value = 0.15
    veins = nodes.new("ShaderNodeTexWave")
    veins.bands_direction = "X"
    veins.inputs["Scale"].default_value = 9
    veins.inputs["Distortion"].default_value = 2
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    links.new(veins.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def build_petal(name, mat, cup=0.18):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "2D"
    curve.fill_mode = "BOTH"
    curve.extrude = 0.006
    spline = curve.splines.new("POLY")
    outline = petal_outline()
    spline.points.add(len(outline) - 1)
    for point, (x, y) in zip(spline.points, outline):
        point.co = (x, y, 0, 1)
    spline.use_cyclic_u = True
    curve.materials.append(mat)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.active_object
    # a soft cup: the sides and the tip curl up a little
    for v in obj.data.vertices:
        v.co.z += cup * (v.co.x ** 2 * 3 + 0.4 * v.co.y ** 2)
    bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj


def lights(world="sunset.exr", strength=0.7):
    common.studio_world(world, strength=strength)
    for location, energy, color, rotation in (((-3, -5, 4), 220, (1.0, 0.95, 0.9), (55, 0, -30)),
                                              ((3.5, 3, 2), 260, (1.0, 0.75, 0.85), (-65, 0, 135))):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.active_object
        light.data.energy = energy
        light.data.size = 4
        light.data.color = color
        light.rotation_euler = tuple(math.radians(v) for v in rotation)


def petal_tumble():
    mat = petal_material()
    petal = build_petal("Petal", mat)
    petal.rotation_mode = "QUATERNION"
    holder = bpy.data.objects.new("PetalHolder", None)
    bpy.context.collection.objects.link(holder)
    holder.rotation_mode = "QUATERNION"
    petal.parent = holder
    petal.location = (0, -0.5, 0)  # turn around the petal's middle
    axis = (0.55, 0.35, 0.75)

    def pose(_, t):
        holder.rotation_quaternion = Quaternion(axis, 2 * math.pi * t) @ Quaternion((1, 0, 0), math.radians(70))
    common.ortho_camera(1.35)
    path = common.render_sheet("PetalTumble", 16, 4, pose)
    halo_sheet(path, tuple(PINK), 0.15)
    for obj in (petal, holder):
        obj.hide_render = True
    return path, mat


def blossom(mat):
    holder = bpy.data.objects.new("Blossom", None)
    bpy.context.collection.objects.link(holder)
    parts = [holder]
    for k in range(5):
        petal = build_petal(f"BlossomPetal{k}", mat, cup=0.3)
        petal.parent = holder
        petal.rotation_euler = (math.radians(-12), 0, math.radians(72 * k))
        petal.location = (0, 0, 0)
        parts.append(petal)
    # the heart: a little gold disc and stamens
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.11, location=(0, 0, 0.05))
    heart = bpy.context.active_object
    heart.scale = (1, 1, 0.45)
    gold = bpy.data.materials.new("Heart")
    gold.use_nodes = True
    g = gold.node_tree.nodes["Principled BSDF"]
    g.inputs["Base Color"].default_value = (1.0, 0.75, 0.25, 1)
    g.inputs["Emission Color"].default_value = (1.0, 0.7, 0.3, 1)
    g.inputs["Emission Strength"].default_value = 0.6
    heart.data.materials.append(gold)
    parts.append(heart)
    stamen_mat = bpy.data.materials.new("Stamen")
    stamen_mat.use_nodes = True
    stamen_mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (1.0, 0.92, 0.85, 1)
    tip_mat = gold
    rng = random.Random(4)
    for k in range(18):
        a = 2 * math.pi * k / 18 + rng.uniform(-0.1, 0.1)
        length = rng.uniform(0.22, 0.32)
        end = Vector((math.cos(a) * length, math.sin(a) * length, 0.18 + rng.uniform(0, 0.06)))
        bpy.ops.mesh.primitive_cylinder_add(radius=0.008, depth=end.length, location=end / 2)
        stem = bpy.context.active_object
        stem.rotation_mode = "QUATERNION"
        stem.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(end.normalized())
        stem.data.materials.append(stamen_mat)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.025, location=end)
        tip = bpy.context.active_object
        tip.data.materials.append(tip_mat)
        parts += [stem, tip]
    for part in parts[1:]:
        if part.parent is None:
            part.parent = holder
    holder.rotation_euler = (math.radians(18), 0, math.radians(10))
    scene = bpy.context.scene
    scene.camera.data.ortho_scale = 2.4
    scene.camera.location = (0, 0, 10)
    scene.camera.rotation_euler = (0, 0, 0)
    scene.render.resolution_x = scene.render.resolution_y = 1024
    path = os.path.join(common.OUT, "Blossom.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    picture = add_halo(common.read_png(path), tuple(PINK), 0.45, radius=0.75, falloff=1.8)
    common.save_rgba(picture, path)
    # the icon: the blossom at 512 px
    icon_path = os.path.join(common.OUT, "Icon.png")
    common.save_rgba(picture[::2, ::2], icon_path)
    for part in parts:
        part.hide_render = True
    return path, icon_path


# ---------- the lantern ----------

def lantern_sheet():
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=32, radius=1.0)
    body = bpy.context.active_object
    body.scale = (0.85, 0.85, 1.05)
    bpy.ops.object.shade_smooth()
    paper = bpy.data.materials.new("Paper")
    paper.use_nodes = True
    nodes, links = paper.node_tree.nodes, paper.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.75, 0.08, 0.05, 1)
    bsdf.inputs["Roughness"].default_value = 0.8
    ribs = nodes.new("ShaderNodeTexWave")
    ribs.bands_direction = "Z"
    ribs.inputs["Scale"].default_value = 6
    ribs.inputs["Distortion"].default_value = 0
    coords = nodes.new("ShaderNodeTexCoord")
    links.new(coords.outputs["Object"], ribs.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    links.new(ribs.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    # the light inside: strongest in the middle of the facing side, warm orange
    layer = nodes.new("ShaderNodeLayerWeight")
    layer.inputs["Blend"].default_value = 0.5
    glow = nodes.new("ShaderNodeMapRange")
    glow.inputs["From Min"].default_value = 0.0
    glow.inputs["From Max"].default_value = 1.0
    glow.inputs["To Min"].default_value = 1.7
    glow.inputs["To Max"].default_value = 0.35
    links.new(layer.outputs["Facing"], glow.inputs["Value"])
    strength = nodes.new("ShaderNodeMath")
    strength.operation = "MULTIPLY"
    links.new(glow.outputs["Result"], strength.inputs[0])
    strength.inputs[1].default_value = 1.0
    bsdf.inputs["Emission Color"].default_value = (1.0, 0.36, 0.1, 1)
    links.new(strength.outputs[0], bsdf.inputs["Emission Strength"])
    body.data.materials.append(paper)
    cap = bpy.data.materials.new("Cap")
    cap.use_nodes = True
    cap.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.08, 0.05, 0.04, 1)
    parts = [body]
    for z in (1.0, -1.0):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.42, depth=0.16, location=(0, 0, z))
        ring = bpy.context.active_object
        ring.data.materials.append(cap)
        parts.append(ring)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.02, depth=0.5, location=(0, 0, -1.3))
    tassel = bpy.context.active_object
    gold = bpy.data.materials.new("Tassel")
    gold.use_nodes = True
    gold.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (1.0, 0.7, 0.2, 1)
    tassel.data.materials.append(gold)
    parts.append(tassel)
    holder = bpy.data.objects.new("Lantern", None)
    bpy.context.collection.objects.link(holder)
    for part in parts:
        part.parent = holder

    def pose(_, t):
        holder.rotation_euler = (math.radians(4 * math.sin(2 * math.pi * t)), math.radians(6 * math.sin(2 * math.pi * t + 1)),
                                 2 * math.pi * t * 0.25)
        strength.inputs[1].default_value = 0.85 + 0.15 * math.sin(2 * math.pi * t * 3) + 0.05 * math.sin(2 * math.pi * t * 7)
    scene = bpy.context.scene
    scene.camera.data.ortho_scale = 3.2
    scene.camera.location = (0, -10, -0.15)
    scene.camera.rotation_euler = (math.pi / 2, 0, 0)
    path = common.render_sheet("Lantern", 16, 4, pose)
    halo_sheet(path, (1.0, 0.6, 0.3), 0.55)
    for part in parts + [holder]:
        part.hide_render = True
    return path


# ---------- the tree on the horizon ----------

def tree():
    rng = random.Random(11)
    bark = bpy.data.materials.new("Bark")
    bark.use_nodes = True
    bark.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.13, 0.07, 0.07, 1)
    bloom = bpy.data.materials.new("Bloom")
    bloom.use_nodes = True
    nodes, links = bloom.node_tree.nodes, bloom.node_tree.links
    bsdf = nodes["Principled BSDF"]
    info = nodes.new("ShaderNodeObjectInfo")
    ramp = nodes.new("ShaderNodeValToRGB")
    stops = ramp.color_ramp.elements
    stops[0].position, stops[0].color = 0.0, (0.95, 0.45, 0.65, 1)
    stops[1].position, stops[1].color = 1.0, (1.0, 0.92, 0.95, 1)
    middle = stops.new(0.5)
    middle.color = (1.0, 0.68, 0.8, 1)
    links.new(info.outputs["Random"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.7
    bsdf.inputs["Subsurface Weight"].default_value = 0.3
    links.new(ramp.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 0.15
    made = []
    tips = []

    def branch(start, direction, length, radius, depth):
        end = start + direction * length
        curve = bpy.data.curves.new("Branch", "CURVE")
        curve.dimensions = "3D"
        curve.bevel_depth = radius
        curve.bevel_resolution = 2
        spline = curve.splines.new("BEZIER")
        spline.bezier_points.add(1)
        bend = Vector((rng.uniform(-0.15, 0.15), 0, rng.uniform(-0.05, 0.1))) * length
        for point, co in zip(spline.bezier_points, (start, end)):
            point.co = co
            point.handle_left_type = point.handle_right_type = "AUTO"
        spline.bezier_points[1].co = end + bend * 0.3
        spline.bezier_points[0].radius, spline.bezier_points[1].radius = 1.0, 0.55
        curve.materials.append(bark)
        obj = bpy.data.objects.new("Branch", curve)
        bpy.context.collection.objects.link(obj)
        made.append(obj)
        if depth == 0:
            tips.append(end)
            return
        for _ in range(2 if depth > 1 else 3):
            spread = Vector((rng.uniform(-0.9, 0.9), rng.uniform(-0.3, 0.3), rng.uniform(0.3, 0.9))).normalized()
            new = (direction * 0.45 + spread * 0.75).normalized()
            branch(end, new, length * rng.uniform(0.6, 0.75), radius * 0.6, depth - 1)

    branch(Vector((0, 0, -1.6)), Vector((0, 0, 1)), 1.1, 0.12, 4)
    # the blossom: clusters of little balls around the tips (and a few in between)
    for tip in tips:
        for _ in range(40):
            offset = Vector((rng.gauss(0, 0.26), rng.gauss(0, 0.12), rng.gauss(0.05, 0.2)))
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=rng.uniform(0.05, 0.1), location=tip + offset)
            ball = bpy.context.active_object
            bpy.ops.object.shade_smooth()
            ball.data.materials.append(bloom)
            made.append(ball)
    scene = bpy.context.scene
    scene.camera.data.ortho_scale = 4.6
    scene.camera.location = (0, -10, 0.4)
    scene.camera.rotation_euler = (math.pi / 2, 0, 0)
    scene.render.resolution_x = scene.render.resolution_y = 1024
    path = os.path.join(common.OUT, "SakuraTree.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    common.save_rgba(add_halo(common.read_png(path), tuple(PINK), 0.25, radius=0.85, falloff=2.0), path)
    for obj in made:
        obj.hide_render = True
    return path


# ---------- the textures drawn from math ----------

def moon():
    size = 1024
    rng = np.random.default_rng(5)
    x, y = common.grid_coords(size)
    r = np.sqrt(x * x + y * y)
    disc_r = 0.42
    disc = np.clip((disc_r - r) / 0.006, 0, 1)
    shade = np.ones_like(r)
    for _ in range(26):  # soft craters and seas
        cx, cy, s, d = rng.normal(0, 0.2), rng.normal(0, 0.2), rng.uniform(0.02, 0.12), rng.uniform(0.05, 0.16)
        shade -= d * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (s * s))
    limb = np.sqrt(np.clip(1 - (r / disc_r) ** 2, 0, 1)) ** 0.25  # a little darker at the edge
    color = np.stack([np.full_like(r, 1.0), np.full_like(r, 0.95), np.full_like(r, 0.92)], -1) * (shade * limb)[..., None]
    halo = np.clip(1 - (r - disc_r) / 0.55, 0, 1) ** 2.2 * (r > disc_r) * 0.75
    alpha = np.clip(disc + halo, 0, 1)
    tint = (halo / np.maximum(alpha, 1e-4))[..., None]
    color = color * (1 - tint) + PINK * tint
    image = np.zeros((size, size, 4), dtype=np.float32)
    image[..., :3] = np.clip(color, 0, 1)
    image[..., 3] = alpha
    path = os.path.join(common.OUT, "Moon.png")
    common.save_rgba(image, path)
    return path


def mist():
    width, height = 1024, 256
    rng = np.random.default_rng(8)
    u = (np.arange(width) + 0.5) / width
    v = (np.arange(height) + 0.5) / height
    U, V = np.meshgrid(u, v)
    lumps = np.zeros_like(U)
    for _ in range(16):
        f, phase, amp = rng.integers(1, 6), rng.random(), rng.uniform(0.3, 1)
        lumps += amp * np.cos(2 * np.pi * (f * U + phase))
    lumps = 0.5 + 0.5 * lumps / 8
    body = np.exp(-((V - 0.6) / 0.22) ** 2) * (0.55 + 0.45 * lumps)
    sides = np.clip(np.minimum(U, 1 - U) / 0.2, 0, 1) ** 1.5
    image = np.zeros((height, width, 4), dtype=np.float32)
    image[..., :3] = PINK * 0.6 + WARM * 0.4
    image[..., 3] = np.clip(body * sides * 0.8, 0, 1)
    path = os.path.join(common.OUT, "Mist.png")
    common.save_rgba(image, path)
    return path


# ---------- the backdrop: a snowy mountain, a pagoda, a torii gate ----------

def mountain():
    """A big snow-capped mountain (like Mount Fuji) fading into pink mist at its foot, wider than tall."""
    width, height = 1024, 512
    u = (np.arange(width) + 0.5) / width
    v = (np.arange(height) + 0.5) / height  # 0 at the top
    U, V = np.meshgrid(u, v)
    x = (U - 0.5) * 2
    # the slopes: steep near the top, flatter toward the foot, a flat crater on the top, a few small bumps
    profile = 0.22 + 0.9 * np.abs(x) ** 1.5 + 0.006 * np.sin(x * 31) * (np.abs(x) > 0.1)
    profile = np.where(np.abs(x) < 0.07, 0.22 + 0.9 * 0.07 ** 1.5, profile)
    inside = np.clip((V - profile) / 0.004, 0, 1)
    depth = np.clip((V - profile) / 0.6, 0, 1)
    # the snow cap: thick on the top, thinner down the slopes, a ragged lower edge with gullies running down
    gullies = 0.04 * np.abs(np.sin(x * 26 + 0.5)) + 0.02 * np.sin(x * 71)
    snow_depth = np.clip(0.2 - np.abs(x) * 0.22, 0, None) + gullies
    snow = np.clip((profile + snow_depth - V) / 0.008, 0, 1) * inside
    shade = 0.82 + 0.18 * np.clip(-x * 2, -1, 1)  # the side away from the sun is darker
    base = np.array((0.42, 0.38, 0.62)) * (1 - depth[..., None]) + np.array((0.95, 0.62, 0.75)) * depth[..., None]
    white = np.array((1.0, 0.95, 0.97)) * shade[..., None]
    color = base * shade[..., None] * (1 - snow[..., None]) + white * snow[..., None]
    fade = np.clip((1 - V) / 0.25, 0, 1)  # the foot melts into the mist
    alpha = inside * fade * 0.95
    image = np.zeros((height, width, 4), dtype=np.float32)
    image[..., :3] = np.clip(color, 0, 1)
    image[..., 3] = np.clip(alpha, 0, 1)
    path = os.path.join(common.OUT, "Mountain.png")
    common.save_rgba(image, path)
    return path


def simple_material(name, color, emission=0.0, emission_color=None, roughness=0.6):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*(emission_color or color), 1)
        bsdf.inputs["Emission Strength"].default_value = emission
    return mat


def box(name, size, location, mat, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = size
    obj.data.materials.append(mat)
    return obj


def roof(name, width, height, z, mat):
    """A flared roof: a flat four-sided pyramid with its corners lifted."""
    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=width, radius2=width * 0.12, depth=height, location=(0, 0, z),
                                    rotation=(0, 0, math.pi / 4))
    obj = bpy.context.active_object
    obj.name = name
    for v in obj.data.vertices:
        if v.co.z < 0:  # the lower corners curl up a little
            v.co.z += 0.12 * height * (abs(v.co.x) + abs(v.co.y)) / width
    obj.data.materials.append(mat)
    return obj


def render_object(name, parts, scale, location=(0, -10, 0), halo=0.3):
    scene = bpy.context.scene
    scene.camera.data.ortho_scale = scale
    scene.camera.location = location
    scene.camera.rotation_euler = (math.pi / 2, 0, 0)
    scene.render.resolution_x = scene.render.resolution_y = 1024
    path = os.path.join(common.OUT, f"{name}.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    common.save_rgba(add_halo(common.read_png(path), tuple(PINK), halo, radius=0.85, falloff=2.0), path)
    for obj in parts:
        obj.hide_render = True
    return path


def pagoda():
    wall = simple_material("PagodaWall", (0.55, 0.12, 0.08))
    wood = simple_material("PagodaRoof", (0.12, 0.1, 0.13))
    window = simple_material("PagodaWindow", (1.0, 0.6, 0.3), emission=3.0)
    gold = simple_material("PagodaGold", (1.0, 0.75, 0.3), emission=0.4, roughness=0.3)
    parts = []
    z = -2.0
    for tier in range(5):
        w = 0.62 - tier * 0.08
        h = 0.42
        parts.append(box(f"Wall{tier}", (w * 2, w * 2, h), (0, 0, z + h / 2), wall))
        for dx in (-w * 0.45, 0, w * 0.45):  # warm lit windows on the front
            parts.append(box(f"Window{tier}", (0.11, 0.02, 0.16), (dx, -w - 0.005, z + h * 0.5), window))
        parts.append(roof(f"Roof{tier}", w * 1.65, 0.28, z + h + 0.1, wood))
        z += h + 0.22
    bpy.ops.mesh.primitive_cylinder_add(radius=0.035, depth=0.9, location=(0, 0, z + 0.4))
    spire = bpy.context.active_object
    spire.data.materials.append(gold)
    parts.append(spire)
    for k in range(5):
        bpy.ops.mesh.primitive_torus_add(major_radius=0.08, minor_radius=0.02, location=(0, 0, z + 0.15 + k * 0.13))
        ring = bpy.context.active_object
        ring.data.materials.append(gold)
        parts.append(ring)
    return render_object("Pagoda", parts, 4.6, location=(0.0, -10, 0.25), halo=0.25)


def torii():
    red = simple_material("ToriiRed", (0.85, 0.12, 0.06), emission=0.25, emission_color=(1.0, 0.3, 0.15))
    black = simple_material("ToriiBlack", (0.05, 0.04, 0.05))
    parts = []
    for x in (-0.75, 0.75):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.09, depth=2.2, location=(x, 0, -0.3))
        pillar = bpy.context.active_object
        pillar.data.materials.append(red)
        parts.append(pillar)
        parts.append(box("Foot", (0.26, 0.26, 0.18), (x, 0, -1.35), black))
    parts.append(box("Nuki", (1.9, 0.12, 0.13), (0, 0, 0.45), red))
    parts.append(box("Shimaki", (2.4, 0.2, 0.14), (0, 0, 0.82), red))
    parts.append(box("Kasagi", (2.75, 0.24, 0.13), (0, 0, 0.98), black))
    for x, turn in ((-1.35, 8), (1.35, -8)):  # the ends of the top beam curl up
        parts.append(box("KasagiEnd", (0.3, 0.24, 0.12), (x, 0, 1.01), black, rotation=(0, math.radians(turn), 0)))
    parts.append(box("Gakuzuka", (0.12, 0.08, 0.3), (0, 0, 0.64), red))
    return render_object("Torii", parts, 3.4, location=(0, -10, -0.15), halo=0.2)


def previews(paths):
    sky = np.array((0.55, 0.42, 0.62))
    for name, path in paths.items():
        picture = common.read_png(path)
        out = np.ones_like(picture)
        out[..., :3] = picture[..., :3] * picture[..., 3:4] + sky * (1 - picture[..., 3:4])
        common.save_rgba(out, os.path.join(common.OUT, f"preview_{name}.png"))


def main():
    common.clear()
    if "--backdrop" in sys.argv:  # only the mountain, the pagoda and the torii (quick)
        common.cycles(samples=96)
        common.ortho_camera(4.6)
        lights()
        paths = {"Mountain": mountain(), "Pagoda": pagoda(), "Torii": torii()}
        previews(paths)
        return
    paths = {"Moon": moon(), "Mist": mist(), "Mountain": mountain()}
    if "--small" not in sys.argv:
        common.cycles(samples=96)
        lights()
        paths["PetalTumble"], mat = petal_tumble()
        paths["Lantern"] = lantern_sheet()
        paths["Blossom"], paths["Icon"] = blossom(mat)
        paths["SakuraTree"] = tree()
        paths["Pagoda"] = pagoda()
        paths["Torii"] = torii()
    previews(paths)
    for path in paths.values():
        print("VFX made:", path)


main()
