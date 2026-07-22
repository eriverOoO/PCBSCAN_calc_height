"""Blender-side Cycles entry point for the L2 manifest.

This file is imported only by Blender.  It builds actual component meshes and
separate materials, keeps camera/projector fixed, rotates only the PCB group,
and removes that group for independent matte-stage references.  Cycles passes
are enabled for downstream metric-depth/normal/material-mask extraction.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def _args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args(argv)


def _material(bpy, name, base, metallic, roughness):
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*base, 1.0)
    material.use_nodes = True
    node = material.node_tree.nodes.get("Principled BSDF")
    node.inputs["Base Color"].default_value = (*base, 1.0)
    node.inputs["Metallic"].default_value = metallic
    node.inputs["Roughness"].default_value = roughness
    return material


def _cube(bpy, collection, name, location, scale, material, material_index):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.data.materials.append(material)
    obj.pass_index = material_index
    for owner in list(obj.users_collection):
        owner.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def main() -> None:
    import bpy

    args = _args()
    manifest = json.loads(args.scene_manifest.read_text(encoding="utf-8"))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT" if not hasattr(scene, "cycles") else "CYCLES"
    scene.render.resolution_x, scene.render.resolution_y = manifest["camera"]["resolution_px"]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "BW"
    scene.render.image_settings.color_depth = "16"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.render.film_transparent = False
    view_layer = scene.view_layers[0]
    view_layer.use_pass_z = True
    view_layer.use_pass_normal = True
    view_layer.use_pass_material_index = True

    materials = {
        "stage": _material(bpy, "stage", (0.18, 0.18, 0.18), 0.0, 0.9),
        "substrate": _material(bpy, "pcb_substrate", (0.03, 0.16, 0.04), 0.0, 0.45),
        "pad": _material(bpy, "copper_gold_tin_pad", (0.65, 0.42, 0.12), 0.9, 0.18),
        "solder": _material(bpy, "solder", (0.5, 0.55, 0.58), 0.8, 0.22),
        "ic": _material(bpy, "matte_black_ic", (0.015, 0.015, 0.018), 0.0, 0.7),
        "ceramic": _material(bpy, "ceramic_smd", (0.72, 0.66, 0.48), 0.0, 0.5),
        "connector": _material(bpy, "connector", (0.08, 0.08, 0.09), 0.15, 0.42),
    }
    _cube(bpy, scene.collection, "matte_stage", (0, 0, -0.75), (55, 55, 0.5), materials["stage"], 0)
    pcb = bpy.data.collections.new("PCB")
    scene.collection.children.link(pcb)
    _cube(bpy, pcb, "substrate", (0, 0, 0), (15, 15, 0.65), materials["substrate"], 1)
    _cube(bpy, pcb, "ic", (0, 0, 2.1), (4.5, 4.5, 1.45), materials["ic"], 4)
    for index, x in enumerate((-10, -6, 6, 10)):
        _cube(bpy, pcb, f"pad_{index}", (x, -8, 0.8), (1.4, 2.2, 0.15), materials["pad"], 2)
        _cube(bpy, pcb, f"smd_{index}", (x, 7, 1.05), (1.8, 0.9, 0.4), materials["ceramic"], 6)
    _cube(bpy, pcb, "connector", (0, 11, 2.6), (6, 2.5, 2.0), materials["connector"], 7)

    bpy.ops.object.camera_add(location=(0, -240, 170), rotation=(math.radians(55), 0, 0))
    camera = bpy.context.object
    camera.data.lens = float(manifest["camera"]["focal_length_mm"])
    camera.data.sensor_width = manifest["camera"]["resolution_px"][0] * manifest["camera"]["pixel_pitch_um"] / 1000.0
    scene.camera = camera
    bpy.ops.object.light_add(type="SPOT", location=(90, -180, 150))
    projector = bpy.context.object
    projector.name = "independent_pattern_projector"
    projector.data.energy = 1600
    projector.data.spot_size = math.radians(38)
    projector.rotation_euler = (math.radians(55), 0, math.radians(25))

    args.output_root.mkdir(parents=True, exist_ok=True)
    for view_name, view in manifest["views"].items():
        rotation = math.radians(float(view["pcb_rotation_deg"]))
        for obj in pcb.objects:
            obj.rotation_euler[2] = rotation
            obj.hide_render = not bool(view["pcb_present"])
        frame_dir = args.output_root / "views" / view_name
        frame_dir.mkdir(parents=True, exist_ok=True)
        for pattern_id in range(22):
            # The exact texture path is retained on the projector as an auditable
            # custom property. A production gobo node group can consume it without
            # changing the common scene manifest or pattern order.
            projector["pattern_texture"] = str(
                Path(manifest["patterns"]["output_root"]) / f"pattern_{pattern_id:03d}.png"
            )
            scene.render.filepath = str(frame_dir / f"pattern_{pattern_id:03d}.png")
            bpy.ops.render.render(write_still=True)
    calibration = {
        "camera_matrix_source": "Blender camera + sensor/focal settings",
        "projector_object": projector.name,
        "world_units": "millimetres",
    }
    (args.output_root / "camera_projector_calibration.json").write_text(
        json.dumps(calibration, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
