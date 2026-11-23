"""Aurora, the event effect for an EXP boost: the textures, made in Blender from code.

Run:  blender --background --python tools/vfx/aurora.py -- <out folder> [--fast] [--curtains]
Out (all PNG with a transparent background, made for Roblox):
- CurtainA1-4.png 512x1024, the aurora's curtain for a Beam: soft rays over a bright wavy lower edge, green at the
                  edge, violet at the tips; four variants with the same edges (each beam of a ribbon shows one,
                  any can follow any: no seam and no repeating pattern); turned a quarter to the left (a Beam lays
                  the picture's height along its length), the lower edge on the right;
- CurtainB1-4.png the same kind of curtain in turquoise and pink (a second layer: the two cross-fade, so the
                  aurora slowly changes color);
- Haze1-3.png     256x512, the soft glow around a curtain (no rays, a wide blur of green to violet light): the
                  aurora spreads into the sky instead of ending at a line; variants and turned like the curtains;
- ExpOrb.png      4x4 flipbook (Cycles): a glass orb of light with a bright core and a little ring of light turning
                  around it, pulsing once (the EXP that rises from the ground);
- StarTwinkle.png 4x4 flipbook: a cold four-pointed star that opens and closes (the stars of the night);
- Glow.png        a soft turquoise glow (the trail of the orbs, the light of the shooting stars);
- Ring.png        a soft turquoise ring (the wave on the ground at the start);
- Icon.png        the event's icon (512 px): the orb with an aurora band, the round icon and its start countdown;
- preview_*.png   pictures to look at."""
import math
import os
import random
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

GREEN = np.array((0.30, 1.00, 0.55))
AURORA_GREEN = np.array((0.2, 1.00, 0.32))  # the curtain's lower edge: the classic green of an aurora
TEAL = np.array((0.18, 0.92, 0.88))
VIOLET = np.array((0.62, 0.38, 1.00))
PINK = np.array((1.00, 0.42, 0.78))


# ---------- the curtains ----------

def periodic_noise(u, count, low, high, rng, power=0.9):
    """A noise that repeats every 1 in u: a sum of cosines with whole-number frequencies (random phases)."""
    total = np.zeros_like(u)
    weight = 0.0
    for _ in range(count):
        frequency = rng.integers(low, high + 1)
        amplitude = 1 / frequency ** power
        total += amplitude * np.cos(2 * np.pi * (frequency * u + rng.random()))
        weight += amplitude
    return total / weight  # about -1..1


def soften(values, passes=2, size=5):
    """A box blur along u (the picture repeats left to right, so the blur wraps around)."""
    for _ in range(passes):
        values = sum(np.roll(values, shift, axis=1) for shift in range(-(size // 2), size // 2 + 1)) / size
    return values


def curtain_picture(bottom, middle, top, fringe, seed):
    """One curtain, upright (the lower edge at the bottom), seamless left to right."""
    width, height = 1024, 512
    rng = np.random.default_rng(seed)
    u = (np.arange(width) + 0.5) / width
    v = 1 - (np.arange(height) + 0.5) / height  # 0 at the bottom row, 1 at the top
    U, V = np.meshgrid(u, v)
    # the rays lean a little and bend with height, like folds of a curtain
    bend = 0.018 * periodic_noise(u, 6, 1, 4, rng)[None, :] * (V * 2.2) + 0.012 * np.sin(2 * np.pi * (2 * U + V * 1.3))
    ray_u = (U + bend) % 1.0
    fine = periodic_noise(ray_u, 40, 18, 160, rng, power=0.6)
    coarse = periodic_noise(ray_u, 12, 4, 30, rng, power=0.8)
    # soft rays: the light is a blur with streaks in it, not hard lines
    rays = np.clip(0.55 + 0.45 * fine * 1.4, 0, 1) ** 1.6 * 0.55 + np.clip(0.5 + 0.5 * coarse * 1.4, 0, 1) ** 1.3 * 0.6
    rays = soften(np.clip(rays, 0, 1))
    # the lower edge: bright and wavy
    edge = 0.2 + 0.05 * periodic_noise(u, 8, 1, 7, rng)[None, :] + 0.012 * periodic_noise(u, 10, 10, 40, rng)[None, :]
    above = V - edge
    rise = np.clip(above / 0.06 + 1, 0, 1) ** 2  # 0 below the edge, 1 just above it
    fade = np.exp(-np.clip(above, 0, None) * 1.2)  # the light thins out upward
    # the rays end at different heights (no straight top edge between the beams of a ribbon)
    tips = 0.7 + 0.2 * periodic_noise(u, 10, 2, 24, rng)[None, :] + 0.1 * coarse
    top_fade = np.clip((tips - V) / 0.4, 0, 1) ** 1.4 * np.clip((1 - V) / 0.08, 0, 1)
    seam = 0.85 * np.exp(-((above - 0.015) / 0.035) ** 2)  # the bright line along the edge
    brightness = 0.5 + 0.5 * np.clip(0.5 + 0.5 * periodic_noise(u, 6, 1, 5, rng)[None, :] * 1.5, 0, 1)
    light = (rise * fade * (0.4 + 0.6 * rays) + seam * rays) * top_fade * brightness
    under = np.exp(-((above + 0.04) / 0.04) ** 2) * 0.3 * rays * brightness  # a faint pink fringe under the edge
    # color by height over the edge
    h = np.clip(above / 0.42, 0, 1)[..., None]
    color = np.where(h < 0.4, bottom + (middle - bottom) * (h / 0.4), middle + (top - middle) * np.clip((h - 0.4) / 0.4, 0, 1))
    hot = np.clip(seam * rays, 0, 1)[..., None] * 0.2  # the edge burns almost white
    color = color * (1 - hot) + hot
    total = light + under
    mix = (under / np.maximum(total, 1e-4))[..., None]
    color = color * (1 - mix) + fringe * mix
    image = np.zeros((height, width, 4), dtype=np.float32)
    image[..., :3] = np.clip(color, 0, 1)
    image[..., 3] = np.clip(total, 0, 1)
    return image


def haze_picture(seed):
    """The soft glow around a curtain, upright, seamless left to right."""
    width, height = 512, 256
    rng = np.random.default_rng(seed)
    u = (np.arange(width) + 0.5) / width
    v = 1 - (np.arange(height) + 0.5) / height  # 0 at the bottom row, 1 at the top
    U, V = np.meshgrid(u, v)
    # the glow's lower edge and strength wander along the beam (whole periods: no seam between beams)
    edge = 0.16 + 0.06 * periodic_noise(u, 5, 1, 4, rng)[None, :]
    strength = 0.65 + 0.35 * periodic_noise(u, 5, 1, 4, rng)[None, :]
    above = V - edge
    rise = np.clip((above + 0.1) / 0.2, 0, 1) ** 2  # a soft lower edge (no line)
    fade = np.exp(-np.clip(above - 0.1, 0, None) * 2.2)
    top = np.clip((1 - V) / 0.2, 0, 1) ** 1.5
    alpha = rise * fade * top * strength * 0.85
    h = np.clip(above / 0.5, 0, 1)[..., None]
    color = np.where(h < 0.45, AURORA_GREEN + (TEAL - AURORA_GREEN) * (h / 0.45),
                     TEAL + (VIOLET - TEAL) * np.clip((h - 0.45) / 0.55, 0, 1))
    image = np.zeros((height, width, 4), dtype=np.float32)
    image[..., :3] = np.clip(color, 0, 1)
    image[..., 3] = np.clip(alpha, 0, 1)
    return image


def variants(name, make, seed, count):
    """count pictures that differ inside but share their left and right edges: any of them can follow any other along a
    ribbon without a seam, so the ribbon shows no repeating pattern. Saved turned a quarter to the left (a Beam lays
    the picture's height along its length; the lower edge ends up on the right)."""
    base = make(seed)
    width = base.shape[1]
    u = (np.arange(width) + 0.5) / width
    near = np.clip(np.minimum(u, 1 - u) / 0.12, 0, 1)
    window = (near * near * (3 - 2 * near))[None, :, None]  # 0 at both edges: there each variant is the base
    paths = []
    for k in range(count):
        picture = base * (1 - window) + make(seed * 100 + k + 1) * window
        path = os.path.join(common.OUT, f"{name}{k + 1}.png")
        common.save_rgba(np.ascontiguousarray(np.rot90(picture, k=1)), path)
        paths.append(path)
    return paths


# ---------- the orb of EXP (Cycles) ----------

def emission_material(name, color, strength):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (*color, 1)
    emit.inputs["Strength"].default_value = strength
    links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat, emit


def glass_material():
    """A shell that glows at its rim (fresnel) and is clear in the middle, with soft swirls of light inside."""
    mat = bpy.data.materials.new("OrbShell")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    weight = nodes.new("ShaderNodeLayerWeight")
    weight.inputs["Blend"].default_value = 0.35
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2.6
    noise.inputs["Detail"].default_value = 6
    noise.inputs["Distortion"].default_value = 1.4
    mapping = nodes.new("ShaderNodeMapping")
    coords = nodes.new("ShaderNodeTexCoord")
    links.new(coords.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[0].color = 0.35, (*TEAL * 0.6, 1)
    ramp.color_ramp.elements[1].position, ramp.color_ramp.elements[1].color = 0.75, (*GREEN, 1)
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    emit = nodes.new("ShaderNodeEmission")
    links.new(ramp.outputs["Color"], emit.inputs["Color"])
    strength = nodes.new("ShaderNodeMath")
    strength.operation = "MULTIPLY_ADD"
    strength.inputs[1].default_value = 1.6
    strength.inputs[2].default_value = 0.35
    links.new(weight.outputs["Facing"], strength.inputs[0])
    links.new(strength.outputs["Value"], emit.inputs["Strength"])
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    alpha = nodes.new("ShaderNodeMath")
    alpha.operation = "MULTIPLY_ADD"
    alpha.inputs[1].default_value = 0.75
    alpha.inputs[2].default_value = 0.22
    alpha.use_clamp = True
    links.new(weight.outputs["Facing"], alpha.inputs[0])
    links.new(alpha.outputs["Value"], mix.inputs["Fac"])
    links.new(transparent.outputs["BSDF"], mix.inputs[1])
    links.new(emit.outputs["Emission"], mix.inputs[2])
    links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat, mapping


def core_material():
    """A soft ball of light: bright in the middle, fading to clear at its edge (no hard disc)."""
    mat = bpy.data.materials.new("OrbCore")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    weight = nodes.new("ShaderNodeLayerWeight")
    weight.inputs["Blend"].default_value = 0.5
    soft = nodes.new("ShaderNodeMath")
    soft.operation = "POWER"
    links.new(weight.outputs["Facing"], soft.inputs[0])
    soft.inputs[1].default_value = 0.6
    invert = nodes.new("ShaderNodeMath")
    invert.operation = "SUBTRACT"
    invert.inputs[0].default_value = 1.0
    invert.use_clamp = True
    links.new(soft.outputs["Value"], invert.inputs[1])
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (0.8, 1.0, 0.88, 1)
    links.new(invert.outputs["Value"], emit.inputs["Strength"])
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    links.new(invert.outputs["Value"], mix.inputs["Fac"])
    links.new(transparent.outputs["BSDF"], mix.inputs[1])
    links.new(emit.outputs["Emission"], mix.inputs[2])
    links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat, emit


def build_orb():
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=96, ring_count=48)
    shell = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    shell_mat, swirl = glass_material()
    shell.data.materials.append(shell_mat)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.48, segments=64, ring_count=32)
    core = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    core_mat, core_emit = core_material()
    core.data.materials.append(core_mat)
    bpy.ops.mesh.primitive_torus_add(major_radius=1.25, minor_radius=0.035, major_segments=128, minor_segments=16)
    ring = bpy.context.active_object
    ring_mat, ring_emit = emission_material("OrbRing", tuple(VIOLET), 1.2)
    ring.data.materials.append(ring_mat)
    bpy.ops.mesh.primitive_torus_add(major_radius=1.12, minor_radius=0.022, major_segments=128, minor_segments=12)
    ring2 = bpy.context.active_object
    ring2_mat, ring2_emit = emission_material("OrbRing2", tuple(GREEN), 1.0)
    ring2.data.materials.append(ring2_mat)
    return {"shell": shell, "swirl": swirl, "core": core, "core_emit": core_emit, "ring": ring, "ring_emit": ring_emit,
            "ring2": ring2, "ring2_emit": ring2_emit}


def pose_orb(orb, t):
    pulse = 0.5 - 0.5 * math.cos(2 * math.pi * t)  # 0 -> 1 -> 0, a seamless loop
    orb["core"].scale = [1 + 0.25 * pulse] * 3
    orb["core_emit"].inputs["Color"].default_value = (0.8 + 0.2 * pulse, 1.0, 0.88 + 0.12 * pulse, 1)
    orb["swirl"].inputs["Rotation"].default_value = (0, 0, 2 * math.pi * t)
    orb["ring"].rotation_euler = (math.radians(68), math.radians(18), 2 * math.pi * t)
    orb["ring2"].rotation_euler = (math.radians(-60), math.radians(-25), -2 * math.pi * t + 1.0)
    orb["ring_emit"].inputs["Strength"].default_value = 1.0 + 0.5 * pulse
    orb["ring2_emit"].inputs["Strength"].default_value = 0.9 + 0.5 * (1 - pulse)


def add_halo(path, color, strength=0.55, radius=0.95, falloff=2.2):
    """A soft glow under the rendered picture (a rendered emission has no glow around it by itself)."""
    picture = common.read_png(path)
    size = picture.shape[0]
    halo = common.glow_image(size, color, falloff=falloff)
    x, y = common.grid_coords(size)
    r = np.sqrt(x * x + y * y) / radius
    halo[..., 3] = np.clip(1 - r, 0, 1) ** falloff * strength
    alpha = picture[..., 3:4]
    out = np.zeros_like(picture)
    out[..., 3:4] = alpha + halo[..., 3:4] * (1 - alpha)
    safe = np.maximum(out[..., 3:4], 1e-4)
    out[..., :3] = (picture[..., :3] * alpha + halo[..., :3] * halo[..., 3:4] * (1 - alpha)) / safe
    common.save_rgba(out, path)


def exp_orb():
    common.clear()
    common.cycles(samples=96)
    common.ortho_camera(3.3)
    world = bpy.data.worlds.new("Dark")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0
    bpy.context.scene.world = world
    orb = build_orb()
    path = common.render_sheet("ExpOrb", 16, 4, lambda i, t: pose_orb(orb, t))
    # the halo goes into every frame of the sheet
    sheet = common.read_png(path)
    tile = 256
    for i in range(16):
        row, column = divmod(i, 4)
        frame_path = os.path.join(common.OUT, "_tile.png")
        common.save_rgba(sheet[row * tile:(row + 1) * tile, column * tile:(column + 1) * tile], frame_path)
        add_halo(frame_path, tuple(TEAL * 0.7 + GREEN * 0.3), strength=0.5)
        sheet[row * tile:(row + 1) * tile, column * tile:(column + 1) * tile] = common.read_png(frame_path)
        os.remove(frame_path)
    common.save_rgba(sheet, path)
    # the icon: the orb a little bigger, with a band of aurora behind it
    pose_orb(orb, 0.35)
    bpy.context.scene.camera.data.ortho_scale = 3.0
    bpy.context.scene.render.resolution_x = bpy.context.scene.render.resolution_y = 512
    icon = os.path.join(common.OUT, "Icon.png")
    bpy.context.scene.render.filepath = icon
    bpy.ops.render.render(write_still=True)
    band_behind(icon)
    return path, icon


def band_behind(path):
    """The icon: a curved aurora band across the orb's back, then the orb's glow."""
    picture = common.read_png(path)
    size = picture.shape[0]
    x, y = common.grid_coords(size)
    curve = 0.12 * np.sin(x * 2.4) - 0.05
    d = y - curve
    band = np.exp(-(np.clip(d, None, 0) / 0.05) ** 2) * (d <= 0) + np.exp(-(np.clip(d, 0, None) / 0.32)) * (d > 0)
    rays = 0.6 + 0.4 * np.clip(np.sin(x * 70 + np.sin(x * 9) * 2) * 0.5 + 0.5, 0, 1) ** 2
    reach = np.clip(1 - np.abs(x) / 0.98, 0, 1) ** 0.6 * np.clip(1 - np.sqrt(x * x + y * y) / 1.0, 0, 1) ** 0.5
    band_alpha = np.clip(band * rays * reach * 1.3, 0, 1)
    h = np.clip(d / 0.45, 0, 1)[..., None]
    band_color = GREEN * (1 - h) + VIOLET * h
    band_img = np.zeros_like(picture)
    band_img[..., :3] = band_color
    band_img[..., 3] = band_alpha
    alpha = picture[..., 3:4]
    out = np.zeros_like(picture)
    out[..., 3:4] = alpha + band_img[..., 3:4] * (1 - alpha)
    safe = np.maximum(out[..., 3:4], 1e-4)
    out[..., :3] = (picture[..., :3] * alpha + band_img[..., :3] * band_img[..., 3:4] * (1 - alpha)) / safe
    common.save_rgba(out, path)
    add_halo(path, tuple(TEAL), strength=0.35, radius=0.8)


# ---------- the small textures ----------

def star_twinkle():
    """16 frames of a cold four-pointed star: it opens, shines and closes (a long thin cross and a soft halo)."""
    size, grid = 256, 4
    sheet = np.zeros((1024, 1024, 4), dtype=np.float32)
    x, y = common.grid_coords(size)
    r = np.sqrt(x * x + y * y)
    for i in range(16):
        t = i / 15
        power = math.sin(math.pi * t) ** 1.3
        reach = 0.2 + 0.75 * power
        cross = (np.exp(-np.abs(y) * 90) * np.clip(1 - np.abs(x) / reach, 0, 1) ** 3
                 + np.exp(-np.abs(x) * 90) * np.clip(1 - np.abs(y) / reach, 0, 1) ** 3)
        d1, d2 = (x + y) / math.sqrt(2), (x - y) / math.sqrt(2)
        small = (np.exp(-np.abs(d1) * 120) * np.clip(1 - np.abs(d2) / (reach * 0.35), 0, 1) ** 3
                 + np.exp(-np.abs(d2) * 120) * np.clip(1 - np.abs(d1) / (reach * 0.35), 0, 1) ** 3) * 0.5
        core = np.exp(-(r / (0.04 + 0.05 * power)) ** 2)
        halo = np.exp(-(r / (0.14 + 0.16 * power)) ** 2) * 0.3
        light = np.clip((cross + small + core + halo) * (0.25 + 0.75 * power), 0, 1)
        white = np.clip(core * 1.4 + cross * 0.5, 0, 1)
        frame = np.zeros((size, size, 4), dtype=np.float32)
        frame[..., 0] = 0.72 + 0.28 * white
        frame[..., 1] = 0.86 + 0.14 * white
        frame[..., 2] = 1.0
        frame[..., 3] = light
        row, column = divmod(i, grid)
        sheet[row * size:(row + 1) * size, column * size:(column + 1) * size] = frame
    path = os.path.join(common.OUT, "StarTwinkle.png")
    common.save_rgba(sheet, path)
    return path


def glow():
    image = common.glow_image(256, tuple(TEAL * 0.8 + GREEN * 0.2), falloff=2.2)
    path = os.path.join(common.OUT, "Glow.png")
    common.save_rgba(image, path)
    return path


def ring():
    size = 512
    x, y = common.grid_coords(size)
    r = np.sqrt(x * x + y * y)
    angle = np.arctan2(y, x)
    wobble = 0.015 * np.sin(angle * 7) + 0.01 * np.sin(angle * 13 + 1)
    band = np.exp(-((r - 0.78 - wobble) / 0.06) ** 2)
    inner = np.exp(-((r - 0.6) / 0.22) ** 2) * 0.22
    rays = np.clip(np.sin(angle * 40 + np.sin(angle * 5) * 2) * 0.5 + 0.5, 0, 1) ** 4 * np.exp(-((r - 0.74) / 0.12) ** 2) * 0.5
    white = np.clip(band * 0.55, 0, 1)
    image = np.zeros((size, size, 4), dtype=np.float32)
    h = np.clip((r - 0.55) / 0.35, 0, 1)
    for c in range(3):
        image[..., c] = (GREEN[c] * (1 - h) + TEAL[c] * h) * (1 - white) + white
    image[..., 3] = np.clip(band + inner + rays, 0, 1) * (r < 0.98)
    path = os.path.join(common.OUT, "Ring.png")
    common.save_rgba(image, path)
    return path


def previews(paths):
    """The curtains on a dusk sky, to look at."""
    sky_top, sky_low = np.array((0.05, 0.08, 0.2)), np.array((0.25, 0.35, 0.55))
    for name in ("CurtainA", "CurtainB", "Haze"):
        # the variants side by side, turned back upright (as on a ribbon: the joins must not show)
        picture = np.concatenate([np.rot90(common.read_png(path), k=-1) for path in paths[name]], axis=1)
        h, w = picture.shape[:2]
        t = np.linspace(0, 1, h)[:, None, None]
        sky = sky_top * (1 - t) + sky_low * t
        out = np.ones((h, w, 4), dtype=np.float32)
        out[..., :3] = np.clip(sky + picture[..., :3] * picture[..., 3:4], 0, 1)  # added, like LightEmission 1
        common.save_rgba(out, os.path.join(common.OUT, f"preview_{name}.png"))


def on_dark(name):
    picture = common.read_png(os.path.join(common.OUT, f"{name}.png"))
    out = np.ones_like(picture)
    dark = np.array((0.08, 0.1, 0.22))
    out[..., :3] = picture[..., :3] * picture[..., 3:4] + dark * (1 - picture[..., 3:4])
    common.save_rgba(out, os.path.join(common.OUT, f"preview_{name}.png"))


def main():
    random.seed(11)
    paths = {
        "CurtainA": variants("CurtainA", lambda seed: curtain_picture(AURORA_GREEN, np.array((0.30, 1.0, 0.50)), VIOLET,
                                                                       PINK, seed), seed=3, count=4),
        "CurtainB": variants("CurtainB", lambda seed: curtain_picture(TEAL, np.array((0.40, 1.0, 0.62)), PINK, VIOLET, seed),
                             seed=8, count=4),
        "Haze": variants("Haze", haze_picture, seed=5, count=3),
    }
    if "--curtains" in sys.argv:  # only the curtains (quick, the rest needs Cycles)
        previews(paths)
        return
    paths["StarTwinkle"] = star_twinkle()
    paths["Glow"] = glow()
    paths["Ring"] = ring()
    paths["ExpOrb"], paths["Icon"] = exp_orb()
    previews(paths)
    for name in ("ExpOrb", "Icon", "StarTwinkle", "Ring"):
        on_dark(name)
    for made in paths.values():
        for path in made if isinstance(made, list) else [made]:
            print("VFX made:", path)


main()
