"""Coin Storm, the event effect for a currency boost: the textures and the big coin, made in Blender from code.

Run:  blender --background --python tools/vfx/coin_storm.py -- <out folder> [--fast]
Out (all PNG with a transparent background, made for Roblox):
- CoinSpin.png     8x8 flipbook (64 frames, 128 px each): a gold coin turning once around, lit like the big coin;
- CoinGlint.png    4x4 flipbook: a star glint that opens, flashes and closes (the shine on falling coins);
- GoldDust.png     a soft gold glow (dust left on the grass, the aura of the big coin);
- GoldRing.png     a soft gold shock ring (where the big coin lands);
- BigCoin.fbx      the big coin of the intro (import once in Studio: Import 3D) with its SurfaceAppearance maps
                   BigCoin_Color.png, BigCoin_Normal.png, BigCoin_Roughness.png, BigCoin_Metalness.png (1024 px);
- Icon.png         the event's icon (512 px): the round event icon and its start countdown;
- preview_*.png    pictures to look at."""
import math
import os
import random
import sys

import bmesh
import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

GOLD = (1.0, 0.64, 0.17)  # linear base color of polished gold
DEEP = (0.80, 0.39, 0.07)  # the satin field inside the rim
THICK = 0.12  # half of the coin's thickness (the coin is 2 wide)


# ---------- the coin ----------

def revolve(name, profile, segments=160):
    """A round solid from a (radius, height) outline turned around the Z axis."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    rings = []
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        rings.append([bm.verts.new((r * math.cos(angle), r * math.sin(angle), z)) for r, z in profile])
    for i in range(segments):
        a, b = rings[i], rings[(i + 1) % segments]
        for j in range(len(profile) - 1):
            if profile[j][0] == 0 and profile[j + 1][0] == 0:
                continue
            verts = [a[j], b[j], b[j + 1], a[j + 1]]
            if profile[j][0] == 0:
                verts = [a[j], b[j + 1], a[j + 1]]
            elif profile[j + 1][0] == 0:
                verts = [a[j], b[j], a[j + 1]]
            try:
                bm.faces.new(verts)
            except ValueError:
                pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def star(name, outer, inner, height, z, flip=False):
    """A five-pointed star standing on the face of the coin, with soft beveled edges."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    points = []
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        radius = outer if i % 2 == 0 else inner
        points.append((radius * math.cos(angle), radius * math.sin(angle)))
    sign = -1 if flip else 1
    bottom = [bm.verts.new((x, y, sign * z)) for x, y in points]
    top = [bm.verts.new((x, y, sign * (z + height))) for x, y in points]
    bm.faces.new(top if not flip else list(reversed(top)))
    bm.faces.new(list(reversed(bottom)) if not flip else bottom)
    for i in range(10):
        j = (i + 1) % 10
        bm.faces.new([bottom[i], bottom[j], top[j], top[i]] if not flip else [bottom[j], bottom[i], top[i], top[j]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bevel = obj.modifiers.new("Bevel", "BEVEL")
    bevel.width = height * 0.55
    bevel.segments = 4
    bevel.limit_method = "ANGLE"
    return obj


def beads(name, count, radius, size, z):
    """Small round beads in a ring on the rim (both sides)."""
    objects = []
    for side in (1, -1):
        for i in range(count):
            angle = 2 * math.pi * (i + 0.5) / count
            bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6, radius=size,
                                                 location=(radius * math.cos(angle), radius * math.sin(angle), side * z))
            bead = bpy.context.active_object
            bead.scale = (1, 1, 0.55)
            objects.append(bead)
    for bead in objects:
        bead.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    objects[0].name = name
    return objects[0]


def material(name, color, roughness, bump_scale, bump_strength):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = roughness
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = bump_scale
    noise.inputs["Detail"].default_value = 8
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.02
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def build_coin():
    t = THICK
    profile = [(0, 0.075), (0.70, 0.075), (0.72, 0.08), (0.75, t), (0.93, t), (0.985, t - 0.02), (1.0, t - 0.06),
               (1.0, -(t - 0.06)), (0.985, -(t - 0.02)), (0.93, -t), (0.75, -t), (0.72, -0.08), (0.70, -0.075), (0, -0.075)]
    body = revolve("Body", profile)
    star_front = star("StarFront", 0.52, 0.22, 0.05, 0.075)
    star_back = star("StarBack", 0.52, 0.22, 0.05, 0.075, flip=True)
    rim = beads("Beads", 36, 0.84, 0.028, t)
    polished = material("Polished", GOLD, 0.19, 180, 0.04)
    satin = material("Satin", DEEP, 0.40, 420, 0.10)
    body.data.materials.append(polished)
    body.data.materials.append(satin)
    for poly in body.data.polygons:
        center = poly.center
        if math.hypot(center.x, center.y) < 0.705 and abs(center.z) < 0.08:
            poly.material_index = 1  # the field inside the rim
    for obj in (star_front, star_back, rim):
        obj.data.materials.append(polished)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in (body, star_front, star_back, rim):
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        for modifier in list(obj.modifiers):
            bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()
    coin = bpy.context.active_object
    coin.name = "BigCoin"
    bpy.ops.object.shade_smooth()
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    except (AttributeError, RuntimeError):
        pass
    return coin


def sky_world():
    """What the gold reflects: a bright warm sky above, a soft glow around, warm brown below (a metal shows its
    surroundings, so a game-bright coin needs bright surroundings in every direction it turns to)."""
    scene = bpy.context.scene
    world = bpy.data.worlds.new("Sky")
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    coords = nodes.new("ShaderNodeTexCoord")
    split = nodes.new("ShaderNodeSeparateXYZ")
    ramp = nodes.new("ShaderNodeValToRGB")
    links.new(coords.outputs["Generated"], split.inputs["Vector"])
    remap = nodes.new("ShaderNodeMapRange")
    remap.inputs["From Min"].default_value = -1
    remap.inputs["From Max"].default_value = 1
    links.new(split.outputs["Z"], remap.inputs["Value"])
    links.new(remap.outputs["Result"], ramp.inputs["Fac"])
    stops = ramp.color_ramp.elements
    stops[0].position, stops[0].color = 0.0, (0.10, 0.04, 0.01, 1)
    stops[1].position, stops[1].color = 1.0, (1.0, 0.96, 0.88, 1)
    for position, color in ((0.44, (0.45, 0.22, 0.06)), (0.50, (1.0, 0.86, 0.62)), (0.53, (1.0, 0.92, 0.78)),
                            (0.60, (0.62, 0.42, 0.22)), (0.80, (0.92, 0.84, 0.70))):
        stop = stops.new(position)
        stop.color = (*color, 1)
    links.new(ramp.outputs["Color"], nodes["Background"].inputs["Color"])
    nodes["Background"].inputs["Strength"].default_value = 1.05
    scene.world = world


def lights():
    sky_world()
    bpy.ops.object.light_add(type="AREA", location=(-3.0, -5.0, 3.0))
    key = bpy.context.active_object
    key.data.energy = 170
    key.data.size = 5
    key.data.color = (1.0, 0.93, 0.82)
    key.rotation_euler = (math.radians(60), 0, math.radians(-30))
    bpy.ops.object.light_add(type="AREA", location=(3.5, 3.0, 1.5))
    rim = bpy.context.active_object
    rim.data.energy = 500
    rim.data.size = 2
    rim.data.color = (1.0, 0.85, 0.60)
    rim.rotation_euler = (math.radians(-70), 0, math.radians(130))


# ---------- the textures ----------

def coin_spin(coin):
    common.cycles(samples=96)
    common.ortho_camera(2.35)
    lights()

    def pose(_, t):
        # the face looks at the camera at t = 0, a slight tilt shows the rim
        coin.rotation_euler = (math.radians(90 - 14), 0, 2 * math.pi * t)
    path = common.render_sheet("CoinSpin", 64, 8, pose)
    coin.rotation_euler = (math.radians(76), 0, math.radians(25))
    bpy.context.scene.render.resolution_x = bpy.context.scene.render.resolution_y = 768
    bpy.context.scene.render.filepath = os.path.join(common.OUT, "preview_BigCoin.png")
    bpy.ops.render.render(write_still=True)
    # the event's own icon (the round icon of the event and its start countdown): the coin a little turned, 512 px
    coin.rotation_euler = (math.radians(80), 0, math.radians(18))
    bpy.context.scene.render.resolution_x = bpy.context.scene.render.resolution_y = 512
    bpy.context.scene.render.filepath = os.path.join(common.OUT, "Icon.png")
    bpy.ops.render.render(write_still=True)
    return path


def coin_glint():
    """16 frames of a four-pointed star glint with a warm halo, opening and closing, slowly turning."""
    size, grid = 256, 4
    sheet = np.zeros((1024, 1024, 4), dtype=np.float32)
    x, y = common.grid_coords(size)
    for i in range(16):
        t = i / 15
        power = math.sin(math.pi * t) ** 1.5  # 0 -> 1 -> 0
        turn = math.radians(25 * t)
        xr = x * math.cos(turn) - y * math.sin(turn)
        yr = x * math.sin(turn) + y * math.cos(turn)
        long_rays = np.exp(-np.abs(yr) * 60) * np.clip(1 - np.abs(xr) / (0.25 + 0.7 * power), 0, 1) ** 2
        long_rays += np.exp(-np.abs(xr) * 60) * np.clip(1 - np.abs(yr) / (0.25 + 0.7 * power), 0, 1) ** 2
        d1, d2 = (xr + yr) / math.sqrt(2), (xr - yr) / math.sqrt(2)
        short_rays = (np.exp(-np.abs(d1) * 80) * np.clip(1 - np.abs(d2) / (0.12 + 0.3 * power), 0, 1) ** 2
                      + np.exp(-np.abs(d2) * 80) * np.clip(1 - np.abs(d1) / (0.12 + 0.3 * power), 0, 1) ** 2) * 0.6
        r = np.sqrt(x * x + y * y)
        core = np.exp(-(r / (0.05 + 0.06 * power)) ** 2)
        halo = np.exp(-(r / (0.18 + 0.2 * power)) ** 2) * 0.35
        light = np.clip((long_rays + short_rays + core) * power + halo * power, 0, 1)
        frame = np.zeros((size, size, 4), dtype=np.float32)
        white = np.clip(core * 1.5 + long_rays * 0.6, 0, 1)
        frame[..., 0] = 1.0
        frame[..., 1] = 0.82 + 0.18 * white
        frame[..., 2] = 0.45 + 0.55 * white
        frame[..., 3] = light
        row, column = divmod(i, grid)
        sheet[row * size:(row + 1) * size, column * size:(column + 1) * size] = frame
    path = os.path.join(common.OUT, "CoinGlint.png")
    common.save_rgba(sheet, path)
    return path


def gold_dust():
    image = common.glow_image(256, (1.0, 0.78, 0.30), falloff=2.4)
    path = os.path.join(common.OUT, "GoldDust.png")
    common.save_rgba(image, path)
    return path


def gold_ring():
    size = 512
    x, y = common.grid_coords(size)
    r = np.sqrt(x * x + y * y)
    ring = np.exp(-((r - 0.78) / 0.07) ** 2)
    inner = np.exp(-((r - 0.62) / 0.22) ** 2) * 0.25
    sparkle = np.clip(np.sin(np.arctan2(y, x) * 24) * 0.5 + 0.5, 0, 1) ** 6 * np.exp(-((r - 0.8) / 0.05) ** 2) * 0.6
    image = np.zeros((size, size, 4), dtype=np.float32)
    white = np.clip(ring * 0.6 + sparkle, 0, 1)
    image[..., 0] = 1.0
    image[..., 1] = 0.75 + 0.25 * white
    image[..., 2] = 0.30 + 0.6 * white
    image[..., 3] = np.clip(ring + inner + sparkle, 0, 1) * (r < 0.98)
    path = os.path.join(common.OUT, "GoldRing.png")
    common.save_rgba(image, path)
    return path


# ---------- the big coin for Roblox: mesh and maps ----------

def bake_maps(coin):
    """Color, roughness and normal maps baked from the materials (a 1024 px image each) and a white metalness map."""
    bpy.ops.object.select_all(action="DESELECT")
    coin.select_set(True)
    bpy.context.view_layer.objects.active = coin
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.01)
    bpy.ops.object.mode_set(mode="OBJECT")
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 16
    scene.render.bake.margin = 8
    images = {}
    for kind in ("Color", "Roughness", "Normal"):
        image = bpy.data.images.new(f"BigCoin_{kind}", 1024, 1024, alpha=False)
        image.colorspace_settings.name = "sRGB" if kind == "Color" else "Non-Color"
        images[kind] = image
    for mat in coin.data.materials:
        node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        mat.node_tree.nodes.active = node
        mat["bake_node"] = node.name

    def target(kind):
        for mat in coin.data.materials:
            mat.node_tree.nodes[mat["bake_node"]].image = images[kind]

    # color and roughness through emission: a metal has no diffuse color for Cycles to bake
    saved = {}
    for kind, source in (("Color", "Base Color"), ("Roughness", "Roughness")):
        target(kind)
        for mat in coin.data.materials:
            nodes, links = mat.node_tree.nodes, mat.node_tree.links
            bsdf, output = nodes["Principled BSDF"], nodes["Material Output"]
            emission = nodes.new("ShaderNodeEmission")
            value = bsdf.inputs[source].default_value
            emission.inputs["Color"].default_value = tuple(value) if source == "Base Color" else (value, value, value, 1)
            saved[mat.name] = output.inputs["Surface"].links[0].from_socket
            links.new(emission.outputs["Emission"], output.inputs["Surface"])
        bpy.ops.object.bake(type="EMIT")
        for mat in coin.data.materials:
            mat.node_tree.links.new(saved[mat.name], mat.node_tree.nodes["Material Output"].inputs["Surface"])
    target("Normal")
    bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT")
    paths = {}
    for kind, image in images.items():
        path = os.path.join(common.OUT, f"BigCoin_{kind}.png")
        image.filepath_raw = path
        image.file_format = "PNG"
        image.save()
        paths[kind] = path
    metal = np.ones((256, 256, 4), dtype=np.float32)
    paths["Metalness"] = os.path.join(common.OUT, "BigCoin_Metalness.png")
    common.save_rgba(metal, paths["Metalness"])
    return paths


def export_coin(coin):
    bpy.ops.object.select_all(action="DESELECT")
    coin.select_set(True)
    coin.rotation_euler = (0, 0, 0)
    path = os.path.join(common.OUT, "BigCoin.fbx")
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, apply_unit_scale=True, mesh_smooth_type="FACE",
                             axis_forward="-Z", axis_up="Y")
    return path


def main():
    random.seed(7)
    common.clear()
    coin = build_coin()
    triangles = sum(len(p.vertices) - 2 for p in coin.data.polygons)
    made = [coin_spin(coin), coin_glint(), gold_dust(), gold_ring()]
    made += list(bake_maps(coin).values())
    made.append(export_coin(coin))
    print(f"VFX coin_storm: triangles={triangles}")
    for path in made:
        print("VFX made:", path)


main()
