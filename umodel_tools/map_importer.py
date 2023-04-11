import json
import math
import os
import typing as t

import mathutils as mu
import bpy
import tqdm

from . import asset_db
from . import asset_importer
from . import utils


def split_object_path(object_path):
    # For some reason ObjectPaths end with a period and a digit.
    # This is kind of a sucky way to split that out.

    path_parts = object_path.split(".")

    if len(path_parts) > 1:
        # Usually works, but will fail If the path contains multiple periods.
        return path_parts[0]

    # Nothing to do
    return object_path


class InstanceTransform:
    pos: tuple[float, float, float]
    rot_euler: tuple[float, float, float]
    scale: tuple[float, float, float]

    def __init__(self,
                 pos: tuple[float, float, float] = (0.0, 0.0, 0.0),
                 rot_euler: tuple[float, float, float] = (0.0, 0.0, 0.0),
                 scale: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> None:
        self.pos = pos
        self.rot_euler = rot_euler
        self.scale = scale

    @property
    def matrix_4x4(self) -> mu.Matrix:
        return mu.Matrix.LocRotScale(mu.Vector(self.pos),
                                     mu.Euler(self.rot_euler, 'XYZ'),
                                     mu.Vector(self.scale))


class StaticMesh:
    static_mesh_types = [
        'StaticMeshComponent',
        'InstancedStaticMeshComponent',
        'HierarchicalInstancedStaticMeshComponent'
    ]

    entity_name: str = ""
    asset_path: str = ""
    transform: InstanceTransform
    instance_transforms: list[InstanceTransform]

    # these are just properties to help with debugging
    no_entity: bool = False
    no_mesh: bool = False
    no_path: bool = False
    no_per_instance_data: bool = False
    base_shape: bool = False
    is_instanced: bool = False
    not_rendered: bool = False
    invisible: bool = False
    bad_creation_method: bool = False

    def __init__(self, json_entity: t.Any, entity_type: str) -> None:
        self.entity_name = json_entity.get("Outer", 'Error')
        self.instance_transforms = []

        if not (props := json_entity.get("Properties", None)):
            self.no_entity = True
            return

        if not props.get("StaticMesh", None):
            self.no_mesh = True
            return

        if not (object_path := props.get("StaticMesh").get("ObjectPath", None)) or object_path == '':
            self.no_path = True
            return

        if 'BasicShapes' in object_path:
            # What is a BasicShape? Do we need these?
            self.base_shape = True
            return

        if (render_in_main_pass := props.get("bRenderInMainPass", None)) is not None and not render_in_main_pass:
            self.not_rendered = True
            return

        if (is_visbile := props.get("bVisible", None)) is not None and not is_visbile:
            self.invisible = True

        if ((creation_method := props.get("CreationMethod", None)) is not None
           and creation_method == "EComponentCreationMethod::UserConstructionScript"):
            self.bad_creation_method = True

        objpath = split_object_path(object_path)

        self.asset_path = os.path.normpath(objpath + ".uasset")
        self.asset_path = self.asset_path[1:] if self.asset_path.startswith(os.sep) else self.asset_path

        match entity_type:
            case 'StaticMeshComponent':
                trs = InstanceTransform()

                if (pos := props.get("RelativeLocation", None)) is not None:
                    trs.pos = (pos.get("X") / 100, pos.get("Y") / -100, pos.get("Z") / 100)

                if (rot := props.get("RelativeRotation", None)) is not None:
                    trs.rot_euler = (math.radians(rot.get("Roll")),
                                     math.radians(rot.get("Pitch") * -1),
                                     math.radians(rot.get("Yaw") * -1))

                if (scale := props.get("RelativeScale3D", None)) is not None:
                    trs.scale = (scale.get("X", 1), scale.get("Y", 1), scale.get("Z", 1))

                self.transform = trs

            case 'InstancedStaticMeshComponent' | 'HierarchicalInstancedStaticMeshComponent':
                self.is_instanced = True

                if (instances := json_entity.get("PerInstanceSMData", None)) is None:
                    self.no_per_instance_data = True
                    return

                trs = InstanceTransform()

                if (pos := props.get("RelativeLocation", None)) is not None:
                    trs.pos = (pos.get("X") / 100, pos.get("Y") / -100, pos.get("Z") / 100)

                if (rot := props.get("RelativeRotation", None)) is not None:
                    trs.rot_euler = (math.radians(rot.get("Roll")),
                                     math.radians(rot.get("Pitch") * -1),
                                     math.radians(rot.get("Yaw") * -1))

                if (scale := props.get("RelativeScale3D", None)) is not None:
                    trs.scale = (scale.get("X", 1), scale.get("Y", 1), scale.get("Z", 1))

                self.transform = trs

                for instance in instances:
                    trs = InstanceTransform()

                    if (trs_data := instance.get("TransformData", None)) is not None:
                        if (pos := trs_data.get("Translation", None)) is not None:
                            trs.pos = (pos.get("X") / 100, pos.get("Y") / -100, pos.get("Z") / 100)

                        if (rot := trs_data.get("Rotation", None)) is not None:
                            rot_quat = mu.Quaternion((rot.get("W"), rot.get("X"), rot.get("Y"), rot.get("Z")))
                            quat_to_euler: mu.Euler = rot_quat.to_euler()  # pylint: disable=no-value-for-parameter
                            trs.rot_euler = (-quat_to_euler.x, quat_to_euler.y, -quat_to_euler.z)

                        if (scale := trs_data.get("Scale3D", None)) is not None:
                            trs.scale = (scale.get("X", 1), scale.get("Y", 1), scale.get("Z", 1))

                    self.instance_transforms.append(trs)

    @property
    def invalid(self) -> bool:
        return (self.no_path or self.no_entity or self.base_shape or self.no_mesh or self.no_per_instance_data
                or self.not_rendered or self.invisible or self.bad_creation_method)

    def link_object_instance(self,
                             obj: bpy.types.Object,
                             collection: bpy.types.Collection) -> list[bpy.types.Object]:
        if self.invalid:
            print(f'Refusing to import {self.entity_name} due to failed checks.')
            return []

        objects = []
        trs = self.transform

        if self.is_instanced:
            for instance_trs in self.instance_transforms:
                mat_world = trs.matrix_4x4 @ instance_trs.matrix_4x4
                new_obj = bpy.data.objects.new(obj.name, object_data=obj.data)
                new_obj.rotation_mode = 'XYZ'
                new_obj.matrix_world = mat_world
                collection.objects.link(new_obj)
                objects.append(new_obj)

        else:
            new_obj = bpy.data.objects.new(obj.name, object_data=obj.data)
            new_obj.scale = (trs.scale[0], trs.scale[1], trs.scale[2])
            new_obj.location = (trs.pos[0], trs.pos[1], trs.pos[2])
            new_obj.rotation_mode = 'XYZ'
            new_obj.rotation_euler = mu.Euler((trs.rot_euler[0], trs.rot_euler[1], trs.rot_euler[2]), 'XYZ')
            collection.objects.link(new_obj)
            objects.append(new_obj)

        return objects


class GameLight:
    light_types = [
        'SpotLightComponent',
        # 'AnimatedLightComponent',
        'PointLightComponent'
    ]

    type: str = ""

    entity_name: str = ""
    pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rot: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)

    no_entity = False

    color_temp_table_r = [
        [2.52432244e+03, -1.06185848e-03, 3.11067539e+00],
        [3.37763626e+03, -4.34581697e-04, 1.64843306e+00],
        [4.10671449e+03, -8.61949938e-05, 6.41423749e-01],
        [4.66849800e+03, 2.85655028e-05, 1.29075375e-01],
        [4.60124770e+03, 2.89727618e-05, 1.48001316e-01],
        [3.78765709e+03, 9.36026367e-06, 3.98995841e-01],
    ]

    color_temp_table_g = [
        [-7.50343014e+02, 3.15679613e-04, 4.73464526e-01],
        [-1.00402363e+03, 1.29189794e-04, 9.08181524e-01],
        [-1.22075471e+03, 2.56245413e-05, 1.20753416e+00],
        [-1.42546105e+03, -4.01730887e-05, 1.44002695e+00],
        [-1.18134453e+03, -2.18913373e-05, 1.30656109e+00],
        [-5.00279505e+02, -4.59745390e-06, 1.09090465e+00],
    ]

    color_temp_table_b = [
        [0.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0],
        [-2.02524603e-11, 1.79435860e-07, -2.60561875e-04, -1.41761141e-02],
        [-2.22463426e-13, -1.55078698e-08, 3.81675160e-04, -7.30646033e-01],
        [6.72595954e-13, -2.73059993e-08, 4.24068546e-04, -7.52204323e-01],
    ]

    @staticmethod
    def temp_to_color(temp: float) -> tuple[float, float, float]:
        """Convert kelvin temperature to lamp color

        :param temp: Temperature in Kelvin.
        :return: Color.
        """
        if temp >= 12000.0:
            return (0.826270103, 0.994478524, 1.56626022)
        if temp < 965.0:
            return (4.70366907, 0.0, 0.0)

        i = 0
        if temp >= 6365.0:
            i = 5
        elif temp >= 3315.0:
            i = 4
        elif temp >= 1902.0:
            i = 3
        elif temp >= 1449.0:
            i = 2
        elif temp >= 1167.0:
            i = 1
        else:
            i = 0

        r = GameLight.color_temp_table_r[i]
        g = GameLight.color_temp_table_g[i]
        b = GameLight.color_temp_table_b[i]

        temp_inv = 1 / temp
        return (r[0] * temp_inv + r[1] * temp + r[2],
                g[0] * temp_inv + g[1] * temp + g[2],
                ((b[0] * temp + b[1]) * temp + b[2]) * temp + b[3])

    @property
    def invalid(self) -> bool:
        return self.no_entity

    def __init__(self, json_entity) -> None:
        self.entity_name = json_entity.get("Outer", 'Error')
        self.type = json_entity.get("Type", None)

        if not self.type:
            self.no_entity = True
            return None

        props = json_entity.get("Properties", None)
        if not props:
            print(f"Invalid Entity {self.entity_name}. Lacking properties.")
            self.no_entity = True
            return None

        if props.get("RelativeLocation", False):
            pos = props.get("RelativeLocation")
            self.pos = [pos.get("X") / 100, pos.get("Y") / -100, pos.get("Z") / 100]

        if (rot := props.get("RelativeRotation", None)) is not None:
            self.rot = (rot.get("Roll"),
                        rot.get("Pitch"),
                        rot.get("Yaw") * -1)

        if props.get("RelativeScale3D", False):
            scale = props.get("RelativeScale3D")
            self.scale = [scale.get("X", 1), scale.get("Y", 1), scale.get("Z", 1)]

        if (temp := props.get("Temperature", None)) is not None:
            self.color = self.temp_to_color(temp)

        # TODO: expand this method with more properties for the specific light types
        # Problem: I don't know how values for UE lights map to Blender's light types.

        return None

    def import_light(self, collection) -> bool:
        if self.no_entity:
            print(f"Refusing to import {self.entity_name} due to failed checks.")
            return False

        match self.type:
            case 'SpotLightComponent':
                light_data = bpy.data.lights.new(name=self.entity_name, type='SPOT')
            case 'PointLightComponent':
                light_data = bpy.data.lights.new(name=self.entity_name, type='POINT')

        light_obj = bpy.data.objects.new(name=self.entity_name, object_data=light_data)
        light_obj.scale = (self.scale[0], self.scale[1], self.scale[2])
        light_obj.location = (self.pos[0], self.pos[1], self.pos[2])
        light_obj.rotation_mode = 'XYZ'
        light_obj.rotation_euler = mu.Euler((math.radians(self.rot[0]),
                                             math.radians(self.rot[1]),
                                             math.radians(self.rot[2])),
                                            'XYZ')
        light_data.color = self.color
        collection.objects.link(light_obj)
        bpy.context.scene.collection.objects.link(light_obj)

        return True


class MapImporter(asset_importer.AssetImporter):
    """Imports Unreal Engine map (FModel .json output). Assets are imported from UModel output directory.
    """

    @staticmethod
    def _library_reload():
        for lib in bpy.data.libraries:
            lib.reload()

    def _import_map(self,
                    context: bpy.types.Context,
                    map_path: str,
                    umodel_export_dir: str,
                    asset_dir: str,
                    game_profile: str,
                    db: t.Optional[asset_db.AssetDB] = None) -> bool:
        """Imports map placements to the current scene.

        :param map_path: Path to FModel .json output representing a .umap file.
        :param umodel_export_dir: UModel output directory.
        :param asset_dir: Asset library directory.
        :param game_profile: Current game profile.
        :param db: Asset database.
        :return: True if succesful, else False.
        """

        if not os.path.exists(map_path):
            print(f"Error: File {map_path} not found. Skipping.")
            return False

        json_filename = os.path.basename(map_path)
        import_collection = bpy.data.collections.new(json_filename)

        bpy.context.scene.collection.children.link(import_collection)

        with open(map_path, mode='r', encoding='utf-8') as file:
            json_object = json.load(file)

            # handle the different entity types (mehses, lights, etc)
            with utils.std_out_err_redirect_tqdm() as orig_stdout:
                for entity in tqdm.tqdm(json_object,
                                        desc=f"Importing map \"{os.path.splitext(os.path.basename(map_path))[0]}\"",
                                        file=orig_stdout,
                                        dynamic_ncols=True,
                                        ascii=True):
                    if not entity.get('Type', None):
                        continue

                    entity_type = entity.get('Type')

                    # static meshes
                    if entity_type in StaticMesh.static_mesh_types:
                        static_mesh = StaticMesh(entity, entity_type)

                        if static_mesh.invalid:
                            utils.verbose_print(f"Info: Skipping instance of {static_mesh.entity_name}. "
                                                "Invalid property.")
                            continue

                        if (obj := self._load_asset(
                            context=context,
                            asset_dir=asset_dir,
                            asset_path=static_mesh.asset_path,
                            umodel_export_dir=umodel_export_dir,
                            load=True,
                            db=db,
                            game_profile=game_profile
                        )) is None:
                            self._warn_print(f"Warning: Skipping instance of {static_mesh.entity_name} due to import "
                                             "failure.")
                            continue

                        static_mesh.link_object_instance(obj, import_collection)

                    # lights
                    elif entity_type in GameLight.light_types:
                        light = GameLight(entity)

                        if light.invalid:
                            utils.verbose_print(f"Info: Skipping instance of {static_mesh.entity_name}. "
                                                "Invalid property.")
                            continue

                        light.import_light(import_collection)

        # TODO: required due to unknown reason, blender bug? Otherwise, some meshes have None materials.
        bpy.app.timers.register(self._library_reload, first_interval=0.010)

        return True
