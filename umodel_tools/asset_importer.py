import typing as t
import io
import os
import traceback
import shutil
import contextlib

from .third_party.io_import_scene_unreal_psa_psk_280 import pskimport  # pylint: disable=import-error
import bpy

from . import enums
from . import utils
from . import asset_db
from . import props_txt_parser
from . import game_profiles

from bpy.props import BoolProperty, StringProperty, EnumProperty


# --- Constants for Nodes, Sockets, and Node Groups ---
ALPHA_MODE_CHANNEL = 'CHANNEL_PACKED'
NODE_FRAME = 'NodeFrame'

# Nodes Shaders
BSDF_DIFFUSE_NODE = 'ShaderNodeBsdfDiffuse'
BSDF_EMISSION_NODE = 'ShaderNodeEmission'
BSDF_GLOSSY_NODE = 'ShaderNodeBsdfGlossy'
PRINCIPLED_SHADER_NODE = 'ShaderNodeBsdfPrincipled'
BSDF_TRANSPARENT_NODE = 'ShaderNodeBsdfTransparent'
BSDF_GLASS_NODE = 'ShaderNodeBsdfGlass'
SHADER_ADD_NODE = 'ShaderNodeAddShader'
SHADER_MIX_NODE = 'ShaderNodeMixShader'

# Nodes Color
RGB_MIX_NODE = 'ShaderNodeMix' #
INVERT_NODE = 'ShaderNodeInvert' #

# Nodes Input
TEXTURE_IMAGE_NODE = 'ShaderNodeTexImage'
ENVIRONMENT_IMAGE_NODE = 'ShaderNodeTexEnvironment'
COORD_NODE = 'ShaderNodeTexCoord'

# Nodes Outputs
OUTPUT_NODE = 'ShaderNodeOutputMaterial'

# Nodes Vector
MAPPING_NODE = 'ShaderNodeMapping'
NORMAL_MAP_NODE = 'ShaderNodeNormalMap' #

# Nodes Convert
SHADER_NODE_MATH = 'ShaderNodeMath' #
SHADER_NODE_CLAMP = 'ShaderNodeClamp' #
RGB_TO_BW_NODE = 'ShaderNodeRGBToBW'
SHADER_NODE_SEPARATE_COLOR = 'ShaderNodeSeparateColor' #
SHADER_NODE_COMBINE_COLOR = 'ShaderNodeCombineColor' #

# Node Groups
NODE_GROUP = 'ShaderNodeGroup' #
NODE_GROUP_INPUT = 'NodeGroupInput' #
NODE_GROUP_OUTPUT = 'NodeGroupOutput' #
SHADER_NODE_TREE = 'ShaderNodeTree' #


# Node Socket Types
COLOR_SOCKET_NODE = 'NodeSocketColor' #
FLOAT_SOCKET_NODE = 'NodeSocketFloat' #
VECTOR_SOCKET_NODE = 'NodeSocketVector' #
BOOL_SOCKET_NODE = 'NodeSocketBool' #


# Node Custom Groups
INVERT_CHANNEL_NODE = 'Invert Channel'
MIX_NORMAL_NODE = 'Normal Mix'
NORMAL_MASK_NODE = 'Normal Mask'

MAIN_SHADER_NODE = "MainShader" #
ORM_EXTRA_SHADER_NODE = "ORMExtraShader" #
ODMASK_SHADER_NODE = "OverlayDiffuseMask" #


class AssetImporter:
    """Implements functionality of asset import from UModel output.
       Intended to be inherited a bpy.types.Operator subclass.
    """

    link_to_scene: BoolProperty(name="Link",
        description="Link created asset into the current scene. Experimental", default=False
    )

    append_to_scene: BoolProperty(name="Append",
        description="Append created asset into the current scene. Experimental", default=True
    )

    overwrite: BoolProperty(name="Overwrite AssetLibrary",
        description="Overwrite existing assets within assets directory. Experimental", default=False
    )

    load_pbr_maps: BoolProperty(name="Load PBR textures",
        description="Load normal maps, specular, roughness, etc into materials. Experimental", default=True
    )

    import_backface_culling: BoolProperty(name="Use backface culling",
        description="If this setting is checked, material settings for backface culling will be kept, "
                    "otherwise backface culling is always off",
        default=False
    )

    texture_format: EnumProperty(
        name="Texture format",
        description="Format of textures expected to be in the UModel export directory.",
        items=[
            ('.png', '.png', '', 0),
            ('.dds', '.dds', '', 1),
            ('.tga', '.tga', '', 2)
        ],
        default='.dds'
    )

    mesh_format: EnumProperty(
        name="Mesh format",
        description="Format of mesh exported from Umdoel / Fmodel,\n expected to be in the export directory.",
        items=[
            ('.psk', '.psk', '', 0),
            ('.uemodel', '.uemodel', '', 1)
        ],
        default='.psk'
    )

    _unrecognized_texture_types: set[str] = set()

    _has_warnings: bool = False

    def _op_message(self, msg_type: t.Literal['INFO'] | t.Literal['ERROR'] | t.Literal['WARNING'], msg: str):
        """Print operator message and return the associated status-code.

        :param msg_type: Type of message.
        :param msg: Message text.
        :raises NotImplementedError: Raise when an incorrect ``type`` is passed.
        :return: Blender operator error code.
        """
        self.report(type={msg_type, }, message=msg)  # pylint: disable=no-member
        match msg_type:
            case 'INFO':
                return {'FINISHED'}
            case 'ERROR':
                return {'CANCELLED'}
            case 'WARNING':
                return {'FINISHED'}
            case _:
                raise NotImplementedError()

    def _warn_print(self, *args: t.Any) -> None:
        """Print a message and mark that an operation had warnings.
        :param args: Arguments to internal print() call.
        """
        self._has_warnings = True
        print(*args)

    def _print_unrecognized_textures(self) -> None:
        """Print all unrecognized texture map names found. Useful for adding support for new games.
        """
        if utils.preferences.get_addon_preferences().verbose:
            print("Unrecognized texture types found:")
            print(self._unrecognized_texture_types)
            self._unrecognized_texture_types.clear()


    def _load_asset(self,
                    context: bpy.types.Context,
                    asset_dir: str,
                    asset_path: str,
                    umodel_export_dir: str,
                    game_profile: str,
                    load: bool = True,
                    db: t.Optional[asset_db.AssetDB] = None
                    ) -> bpy.types.Object | None:
        """Loads the asset from library dir, or adds it to library and loads it.

        :param context: Current Blender context.
        :param asset_dir: Asset library directory.
        :param asset_path: Asset path in game format.
        :param umodel_export_dir: UModel output directory.
        :param game_profile: Game profile to import.
        :param load: If False, the asset will be imported to the library, but no the current scene.
        :param db: Asset database to operate on. If given, no saving is performed, else the function handles
        everything by itself.
        :return: Object reference or None (if object was not found or failed loading due to filesystem errors).
        :raises NotImplementedError: Raised when requested game profile is not implemented or available.
        """
        asset_path_abs_no_ext = os.path.join(asset_dir, os.path.splitext(asset_path)[0])
        asset_path_abs = asset_path_abs_no_ext + '.blend'

        try:
            if self.overwrite or not os.path.isfile(asset_path_abs):

                if self.overwrite and os.path.isfile(asset_path_abs):
                    print(f"[Overwrite] Removing existing asset: {asset_path_abs}")
                    os.remove(asset_path_abs) # Remove current asset if overwrite enable.

                self._import_asset_to_library(context=context, asset_library_dir=asset_dir, asset_path=asset_path,
                                              umodel_export_dir=umodel_export_dir, db=db, game_profile=game_profile)

            if load:
                if (linked_data := utils.linked_libraries_search(asset_path_abs, bpy.types.Object)):
                    return linked_data

                with utils.redirect_cstdout():
                    with bpy.data.libraries.load(asset_path_abs, link=True) as (data_from, data_to):
                        data_to.objects = list(data_from.objects)
                        assert len(data_to.objects) == 1

                    return data_to.objects[0]
                
            # if load:
            #     # Instead of checking for already linked asset, we append the asset.
            #     with utils.redirect_cstdout():
            #         # Use link=False to append rather than link.
            #         with bpy.data.libraries.load(asset_path_abs, link=False) as (data_from, data_to):
            #             data_to.objects = list(data_from.objects)
            #             assert len(data_to.objects) == 1
            #     appended_obj = data_to.objects[0]
            #     # Make sure the appended object is added to the current collection.
            #     if appended_obj.name not in context.scene.objects:
            #         context.collection.objects.link(appended_obj)
            #     return appended_obj

            return None

        except (RuntimeError, FileNotFoundError):
            traceback.print_exc()
            return None
        
    def _load_asset_appended(self,
                         context: bpy.types.Context,
                         asset_dir: str,
                         asset_path: str,
                         umodel_export_dir: str,
                         game_profile: str,
                         db: t.Optional[asset_db.AssetDB] = None
                         ) -> bpy.types.Object | None:
        """
        Loads the asset from the asset library by appending it (making it fully local),
        rather than linking it as an external reference.
        """
        asset_path_abs_no_ext = os.path.join(asset_dir, os.path.splitext(asset_path)[0])
        asset_path_abs = asset_path_abs_no_ext + '.blend'

        try:
            if self.overwrite or not os.path.isfile(asset_path_abs):

                if self.overwrite and os.path.isfile(asset_path_abs):
                    print(f"[Overwrite] Removing existing asset: {asset_path_abs}")
                    os.remove(asset_path_abs) # Remove current asset if overwrite enable.

                self._import_asset_to_library(context=context, asset_library_dir=asset_dir, asset_path=asset_path,
                                            umodel_export_dir=umodel_export_dir, db=db, game_profile=game_profile)

            with utils.redirect_cstdout():
                # Use link=False to append instead of linking.
                with bpy.data.libraries.load(asset_path_abs, link=False) as (data_from, data_to):
                    data_to.objects = list(data_from.objects)
                    assert len(data_to.objects) == 1
                appended_obj = data_to.objects[0]
            
            # Ensure the appended object is added to the current collection.
            if appended_obj.name not in context.scene.objects:
                context.collection.objects.link(appended_obj)
            return appended_obj

        except (RuntimeError, FileNotFoundError):
            traceback.print_exc()
            return None
        
    def _load_asset_linked(self,
                       context: bpy.types.Context,
                       asset_dir: str,
                       asset_path: str,
                       umodel_export_dir: str,
                       game_profile: str,
                       db: t.Optional[asset_db.AssetDB] = None
                       ) -> bpy.types.Object | None:
        """
        Loads the asset from the asset library by linking it (as an external reference)
        and then ensures the linked asset is added to the current scene.
        """
        asset_path_abs_no_ext = os.path.join(asset_dir, os.path.splitext(asset_path)[0])
        asset_path_abs = asset_path_abs_no_ext + '.blend'

        try:
            if self.overwrite or not os.path.isfile(asset_path_abs):

                if self.overwrite and os.path.isfile(asset_path_abs):
                    print(f"[Overwrite] Removing existing asset: {asset_path_abs}")
                    os.remove(asset_path_abs) # Remove current asset if overwrite enable.

                self._import_asset_to_library(context=context,
                                            asset_library_dir=asset_dir,
                                            asset_path=asset_path,
                                            umodel_export_dir=umodel_export_dir,
                                            db=db,
                                            game_profile=game_profile)

            # Try to find the already linked asset.
            linked_obj = utils.linked_libraries_search(asset_path_abs, bpy.types.Object)
            if linked_obj is None:
                with utils.redirect_cstdout():
                    # Use link=True to link the asset from the external .blend.
                    with bpy.data.libraries.load(asset_path_abs, link=True) as (data_from, data_to):
                        data_to.objects = list(data_from.objects)
                        assert len(data_to.objects) == 1
                    linked_obj = data_to.objects[0]

            # Ensure the linked object is added to the current scene's collection.
            if linked_obj.name not in context.collection.objects:
                context.collection.objects.link(linked_obj)

            return linked_obj

        except (RuntimeError, FileNotFoundError):
            traceback.print_exc()
            return None


    def _import_image_to_library(self,
                                 tex_path: str,
                                 tex_lib_path: str,
                                 tex_umodel_path: str,
                                 db: asset_db.AssetDB):
        """Import image texture to asset library from UModel output.

        :param tex_path: Path to texture in game format.````
        :param tex_lib_path: Path to texture in the library dir (absolute).
        :param tex_umodel_path: Path to texture in the UModel output dir (absolute).
        """
        # copy file to library dir
        os.makedirs(os.path.dirname(tex_lib_path), exist_ok=True)
        shutil.copyfile(tex_umodel_path, tex_lib_path)

        img = bpy.data.images.load(filepath=tex_lib_path)
        img.asset_mark()
        img.asset_data.catalog_id = db.uid_for_entry(os.path.dirname(tex_path))
        # img.asset_generate_preview()

        tex_lib_blend_path = os.path.splitext(tex_lib_path)[0] + '.blend'

        # write texture library
        bpy.data.libraries.write(tex_lib_blend_path, {img, }, fake_user=True, compress=True)

        # remove original datablock
        bpy.data.images.remove(img, do_unlink=True)

    def _import_material_to_library(self,
                                    material_name: str,
                                    material_path_local: str,
                                    db: asset_db.AssetDB,
                                    umodel_export_dir: str,
                                    asset_library_dir: str,
                                    game_profile: str
                                    ) -> None:
        """Import material to asset library from UModel output.

        :param material_name: Short name of material.
        :param material_path_local: Path to material properties (.props.txt) in game format.
        :param db: Blender AssetDB.
        :param umodel_export_dir: UModel export directory.
        :param asset_library_dir: Asset library directory.
        :param game_profile: Game profile to use.
        :raises RuntimeError: Raised when material properties (.props.txt) file was not found or failed to open.
        :raises NotImplementedError: Raised when requested game profile is not implemented or available.
        """
        game_profile_impl = game_profiles.GAME_HANDLERS.get(game_profile)

        if game_profile_impl is None:
            raise NotImplementedError(f"Requested game profile {game_profile} is not implemented/available.")

        material_path_local_no_ext = os.path.splitext(os.path.splitext(material_path_local)[0])[0]  # remove .props.txt

        if not os.path.isfile(os.path.join(umodel_export_dir, material_path_local)):
            # Try finding it in all extracted folders
            possible_matches = []
            for root, _, files in os.walk(umodel_export_dir):
                for f in files:
                    if f.lower() == os.path.basename(material_path_local).lower():
                        possible_matches.append(os.path.join(root, f))

            if len(possible_matches) == 1:
                material_path_local = os.path.relpath(possible_matches[0], umodel_export_dir)
                print(f"[Fallback] Using found material path: {material_path_local}")
            elif len(possible_matches) > 1:
                print(f"[Warning] Multiple .props.txt matches found for {material_name}:")
                for match in possible_matches:
                    print("    ", match)
                material_path_local = os.path.relpath(possible_matches[0], umodel_export_dir)
                print(f"[Fallback] Using first match: {material_path_local}")
            else:
                raise FileNotFoundError(f"Could not find material: {material_path_local}")

        # load texture infos, may throw OSError if file is not found.
        # pylint: disable=unpacking-non-sequence
        desc_ast, texture_infos, base_prop_overrides, vec_infos = props_txt_parser.parse_props_txt(os.path.join(umodel_export_dir,
                                                                                        material_path_local),
                                                                                        mode='MATERIAL')
        
        print(f"Vector params found: {vec_infos}") # Debug vector param values
        print(f"Override params found: {base_prop_overrides}") # Debug override values

        new_mat = bpy.data.materials.new(material_name)
        new_mat.asset_mark()
        new_mat.asset_data.catalog_id = db.uid_for_entry(material_path_local_no_ext)
        new_mat.use_nodes = True
        new_mat.node_tree.links.clear()
        new_mat.node_tree.nodes.clear()
        game_profile_impl.process_material(mat=new_mat, desc_ast=desc_ast, use_pbr=self.load_pbr_maps)

        out = new_mat.node_tree.nodes.new('ShaderNodeOutputMaterial')

        if self.load_pbr_maps:
            special_blend_mode = None

            # set various material parameters
            if base_prop_overrides is not None:

                if (blend_mode := base_prop_overrides.get('BlendMode')) is not None:
                    match blend_mode:
                        case 'BLEND_Opaque (0)':
                            pass
                        case 'BLEND_Masked (1)':
                            new_mat.blend_method = 'CLIP'
                        case 'BLEND_Translucent (2)':
                            new_mat.blend_method = 'BLEND'
                        case 'BLEND_Additive (3)':
                            special_blend_mode = enums.SpecialBlendingMode.Add
                            new_mat.blend_method = 'BLEND'
                        case 'BLEND_Modulate (4)':
                            special_blend_mode = enums.SpecialBlendingMode.Mod
                            new_mat.blend_method = 'BLEND'
                        case _:
                            self._warn_print(f"Warning: Unknown blending mode \'{blend_mode}\' found on importing "
                                             f"material \"{material_name}\".")

                if self.import_backface_culling and (two_sided := base_prop_overrides.get('TwoSided')) is not None:
                    new_mat.use_backface_culling = not two_sided

                if (alpha_threshold := base_prop_overrides.get('OpacityMaskClipValue')) is not None:
                    new_mat.alpha_threshold = alpha_threshold

            elif self.import_backface_culling:
                new_mat.use_backface_culling = True

            # create basic shader nodes and set their default values
            bsdf = new_mat.node_tree.nodes.new('ShaderNodeBsdfPrincipled')

            ao_mix = new_mat.node_tree.nodes.new('ShaderNodeMix')
            ao_mix.data_type = 'RGBA'
            ao_mix.blend_type = 'MULTIPLY'
            ao_mix.inputs[6].default_value = (1, 1, 1, 1)
            ao_mix.inputs[7].default_value = (1, 1, 1, 1)
            new_mat.node_tree.links.new(ao_mix.outputs[2], bsdf.inputs['Base Color'])

            # --- Custom Node Group Creation ---
            def create_main_node_group():
                node_group = bpy.data.node_groups.new(MAIN_SHADER_NODE, SHADER_NODE_TREE)

                # Create interface sockets
                node_group.interface.new_socket(name="Diffuse Texture",description="Color map texture",in_out='INPUT',socket_type=COLOR_SOCKET_NODE)
                node_group.interface.new_socket(name="AO",description="Packed textures with value in different channel, R-Occlusion, G-Roughness, B-Metallic",in_out='INPUT',socket_type=FLOAT_SOCKET_NODE)
                node_group.interface.new_socket(name="Gamma Strength",description="Gamma Strength",in_out='INPUT',socket_type=FLOAT_SOCKET_NODE)

                node_group.interface.new_socket(
                    name="Diffuse + AO",
                    description="Output Diffuse and Ambient Occlusion multiplied.",
                    in_out='OUTPUT',
                    socket_type=COLOR_SOCKET_NODE
                )

                # Create node group input and output nodes
                group_input_node = node_group.nodes.new(NODE_GROUP_INPUT)
                group_input_node.location = (-900, 0)

                group_output_node = node_group.nodes.new(NODE_GROUP_OUTPUT)
                group_output_node.location = (300, 0)

                gamma = node_group.nodes.new("ShaderNodeGamma")
                gamma.inputs[1].default_value = 0.8      # Factor
                gamma.location = (-650, 0)

                # Mix node
                mix_node = node_group.nodes.new(RGB_MIX_NODE)
                mix_node.data_type = 'RGBA'
                mix_node.blend_type = 'MULTIPLY'
                mix_node.inputs[0].default_value = 0.5      # Factor
                mix_node.inputs[6].default_value = (0.0,0.0,0.0,1.0)      # A - Color
                mix_node.location = (-450, 0)

                node_group.links.new(group_input_node.outputs[0],  gamma.inputs[0])                        # Diffuse to Gamma
                node_group.links.new(gamma.outputs[0], mix_node.inputs[6])                                  # Gamma to mix

                node_group.links.new(group_input_node.outputs[1], mix_node.inputs[7])                     # Occlusion to mix
                node_group.links.new(group_input_node.outputs[2], gamma.inputs[1])                          # Gamma strength

                node_group.links.new(mix_node.outputs['Result'], group_output_node.inputs[0])               # mix output

                print(f"Node group '{MAIN_SHADER_NODE}' created successfully.")

                node_group.use_fake_user = True
                return node_group

            def get_or_create_main_node_group():
                if MAIN_SHADER_NODE in bpy.data.node_groups:
                    return bpy.data.node_groups[MAIN_SHADER_NODE]
                else:
                    return create_main_node_group()

            def create_orm_extra_node_group():
                node_group = bpy.data.node_groups.new(ORM_EXTRA_SHADER_NODE, SHADER_NODE_TREE)

                # Create interface sockets
                node_group.interface.new_socket(
                    name="ORM Input",
                    description="Packed texture map",
                    in_out='INPUT',
                    socket_type=FLOAT_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Multiply",
                    description="Multiply ORM factor",
                    in_out='INPUT',
                    socket_type=FLOAT_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Min",
                    description="Min value",
                    in_out='INPUT',
                    socket_type=FLOAT_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Max",
                    description="Max value",
                    in_out='INPUT',
                    socket_type=FLOAT_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Red Chann Input",
                    description="ORM-Red channel",
                    in_out='INPUT',
                    socket_type=FLOAT_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Red Param Value",
                    description="ORM-Red channel Parameter value",
                    in_out='INPUT',
                    socket_type=FLOAT_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Green Chann Input",
                    description="ORM-Green channel",
                    in_out='INPUT',
                    socket_type=FLOAT_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Green Param Value",
                    description="ORM-Green channel Parameter value",
                    in_out='INPUT',
                    socket_type=FLOAT_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Blue Chann Input",
                    description="ORM-Blue channel",
                    in_out='INPUT',
                    socket_type=FLOAT_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Blue Param Value",
                    description="ORM-Blue channel Parameter value",
                    in_out='INPUT',
                    socket_type=FLOAT_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="ORM Output",
                    description="ORM overlay output",
                    in_out='OUTPUT',
                    socket_type=FLOAT_SOCKET_NODE
                )

                # Create node group input and output nodes
                group_input_node = node_group.nodes.new(NODE_GROUP_INPUT)
                group_input_node.location = (-800, 0)

                group_output_node = node_group.nodes.new(NODE_GROUP_OUTPUT)
                group_output_node.location = (300, 0)

                # Math node
                math_node = node_group.nodes.new(SHADER_NODE_MATH)
                math_node.inputs[0].default_value = 0.5  # Mix Factor
                math_node.operation = 'MULTIPLY'
                math_node.location = (-600, 0)

                # Math node
                clamp_node = node_group.nodes.new(SHADER_NODE_CLAMP)
                clamp_node.inputs[0].default_value = 0.5  # Mix Factor
                clamp_node.location = (-500, -100)

                # Mix node
                mix_node = node_group.nodes.new(RGB_MIX_NODE)
                mix_node.inputs[0].default_value = 0.5  # Mix Factor
                mix_node.location = (-400, -200)

                mix_node1 = node_group.nodes.new(RGB_MIX_NODE)
                mix_node1.inputs[0].default_value = 0.5  # Mix Factor
                mix_node1.location = (-300, -300)

                mix_node2 = node_group.nodes.new(RGB_MIX_NODE)
                mix_node2.inputs[0].default_value = 0.5  # Mix Factor
                mix_node2.location = (-200, -400)

                # Link nodes
                node_group.links.new(group_input_node.outputs[0], math_node.inputs[0])
                node_group.links.new(group_input_node.outputs[1], math_node.inputs[1])

                node_group.links.new(math_node.outputs[0], clamp_node.inputs[0])            # Math to clamp
                node_group.links.new(group_input_node.outputs[2], clamp_node.inputs[1])
                node_group.links.new(group_input_node.outputs[3], clamp_node.inputs[2])

                node_group.links.new(clamp_node.outputs[0], mix_node.inputs[2])             # Clamp to mix
                node_group.links.new(group_input_node.outputs[4], mix_node.inputs[0])
                node_group.links.new(group_input_node.outputs[5], mix_node.inputs[3])

                node_group.links.new(mix_node.outputs[0], mix_node1.inputs[2])              # Mix to mix1
                node_group.links.new(group_input_node.outputs[6], mix_node1.inputs[0])
                node_group.links.new(group_input_node.outputs[7], mix_node1.inputs[3])

                node_group.links.new(mix_node1.outputs[0], mix_node2.inputs[2])             # Mix1 to mix2
                node_group.links.new(group_input_node.outputs[8], mix_node2.inputs[0])
                node_group.links.new(group_input_node.outputs[9], mix_node2.inputs[3])

                node_group.links.new(mix_node2.outputs[0], group_output_node.inputs[0])     # Output

                print(f"Node group '{ORM_EXTRA_SHADER_NODE}' created successfully.")

                node_group.use_fake_user = True
                return node_group

            def get_or_create_orm_extra_node_group():
                if ORM_EXTRA_SHADER_NODE in bpy.data.node_groups:
                    return bpy.data.node_groups[ORM_EXTRA_SHADER_NODE]
                else:
                    return create_orm_extra_node_group()
            
            def create_od_mask_node_group():
                node_group = bpy.data.node_groups.new(ODMASK_SHADER_NODE, SHADER_NODE_TREE)

                # Create interface sockets
                node_group.interface.new_socket(
                    name="Diffuse Input",
                    description="Color map",
                    in_out='INPUT',
                    socket_type=COLOR_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Simple Tint",
                    description="Tint mask, texture map.",
                    in_out='INPUT',
                    socket_type=COLOR_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Red Chann Input",
                    description="Dirt map, Red Channel.",
                    in_out='INPUT',
                    socket_type=FLOAT_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Mask Value 1",
                    description="Get multiplied by the Red Channel.",
                    in_out='INPUT',
                    socket_type=FLOAT_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Diffuse Color (Red Channel)",
                    description="Diffuse texture map - Red Channel.",
                    in_out='INPUT',
                    socket_type=COLOR_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Green Chann Input",
                    description="Dirt map, Green Channel.",
                    in_out='INPUT',
                    socket_type=FLOAT_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Mask Value 2",
                    description="Get multiplied by the Green Channel.",
                    in_out='INPUT',
                    socket_type=FLOAT_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Diffuse Color (Green Channel)",
                    description="Diffuse texture map - Green Channel.",
                    in_out='INPUT',
                    socket_type=COLOR_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Blue Chann Input",
                    description="Dirt map, Blue Channel.",
                    in_out='INPUT',
                    socket_type=FLOAT_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Mask Value 3",
                    description="Get multiplied by the Blue Channel.",
                    in_out='INPUT',
                    socket_type=FLOAT_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Diffuse Color (Blue Channel)",
                    description="Diffuse texture map - Blue Channel.",
                    in_out='INPUT',
                    socket_type=COLOR_SOCKET_NODE
                )
                node_group.interface.new_socket(
                    name="Diffuse Out",
                    description="Dirt Map and Simple Tint overlayed output.",
                    in_out='OUTPUT',
                    socket_type=COLOR_SOCKET_NODE
                )

                # Create node group input and output nodes
                group_input_node = node_group.nodes.new(NODE_GROUP_INPUT)
                group_input_node.location = (-900, 0)

                group_output_node = node_group.nodes.new(NODE_GROUP_OUTPUT)
                group_output_node.location = (300, 0)

                # Mix node #1
                mix_node = node_group.nodes.new(RGB_MIX_NODE)
                mix_node.inputs[0].default_value = 0.5  # Mix Factor
                mix_node.data_type = 'RGBA'
                mix_node.blend_type = 'MULTIPLY'
                mix_node.inputs[0].default_value = 1.0      # Factor
                mix_node.location = (-750, 0)

                # Mix node #2
                mix_node2 = node_group.nodes.new(RGB_MIX_NODE)
                mix_node2.inputs[0].default_value = 0.5  # Mix Factor
                mix_node2.data_type = 'RGBA'
                mix_node2.blend_type = 'MULTIPLY'
                mix_node2.inputs[0].default_value = 1.0      # Factor
                mix_node2.location = (-600, 0)

                # Mix node #3
                mix_node3 = node_group.nodes.new(RGB_MIX_NODE)
                mix_node3.inputs[0].default_value = 0.5  # Mix Factor
                mix_node3.data_type = 'RGBA'
                mix_node3.blend_type = 'OVERLAY'
                mix_node3.inputs[0].default_value = 1.0      # Factor
                mix_node3.location = (-450, 0)

                # Mix node #4
                mix_node4 = node_group.nodes.new(RGB_MIX_NODE)
                mix_node4.inputs[0].default_value = 0.5  # Mix Factor
                mix_node4.data_type = 'RGBA'
                mix_node4.blend_type = 'MULTIPLY'
                mix_node4.inputs[0].default_value = 1.0      # Factor
                mix_node4.inputs[7].default_value = (0.735,0.735,0.735,1.0)      # A - Color
                mix_node4.location = (-700, -200)

                # Mix node #5
                mix_node5 = node_group.nodes.new(RGB_MIX_NODE)
                mix_node5.inputs[0].default_value = 0.5  # Mix Factor
                mix_node5.data_type = 'RGBA'
                mix_node5.blend_type = 'MULTIPLY'
                mix_node5.inputs[0].default_value = 1.0      # Factor
                mix_node5.inputs[7].default_value = (0.735,0.735,0.735,1.0)      # A - Color
                mix_node5.location = (-600, -200)

                # Mix node #6
                mix_node6 = node_group.nodes.new(RGB_MIX_NODE)
                mix_node6.inputs[0].default_value = 0.5  # Mix Factor
                mix_node6.data_type = 'RGBA'
                mix_node6.blend_type = 'MULTIPLY'
                mix_node6.inputs[0].default_value = 1.0      # Factor
                mix_node6.inputs[7].default_value = (0.735,0.735,0.735,1.0)      # A - Color
                mix_node6.location = (-450, -200)

                # Mix node #7
                mix_node7 = node_group.nodes.new(RGB_MIX_NODE)
                mix_node7.inputs[0].default_value = 0.5  # Mix Factor
                mix_node7.data_type = 'RGBA'
                mix_node7.blend_type = 'OVERLAY'
                mix_node7.inputs[0].default_value = 1.0      # Factor
                mix_node7.location = (-300, -100)

                # Link nodes
                node_group.links.new(group_input_node.outputs[0], mix_node.inputs[6])                       # Simple Tint
                node_group.links.new(group_input_node.outputs[1], mix_node.inputs[7])

                node_group.links.new(group_input_node.outputs[4], mix_node2.inputs[7])
                node_group.links.new(group_input_node.outputs[7], mix_node3.inputs[7])
                node_group.links.new(group_input_node.outputs[10], mix_node7.inputs[7])

                node_group.links.new(group_input_node.outputs[2], mix_node4.inputs[7])
                node_group.links.new(group_input_node.outputs[3], mix_node4.inputs[0])

                node_group.links.new(group_input_node.outputs[5], mix_node5.inputs[7])
                node_group.links.new(group_input_node.outputs[6], mix_node5.inputs[0])

                node_group.links.new(group_input_node.outputs[8], mix_node6.inputs[7])
                node_group.links.new(group_input_node.outputs[9], mix_node6.inputs[0])

                node_group.links.new(mix_node.outputs['Result'], mix_node2.inputs[6])
                node_group.links.new(mix_node2.outputs['Result'], mix_node3.inputs[6])
                node_group.links.new(mix_node3.outputs['Result'], mix_node7.inputs[6])

                node_group.links.new(mix_node4.outputs['Result'], mix_node2.inputs[0])
                node_group.links.new(mix_node5.outputs['Result'], mix_node3.inputs[0])
                node_group.links.new(mix_node6.outputs['Result'], mix_node7.inputs[0])

                node_group.links.new(mix_node7.outputs['Result'], group_output_node.inputs[0])                 # Diffuse output

                print(f"Node group '{ODMASK_SHADER_NODE}' created successfully.")

                node_group.use_fake_user = True
                return node_group

            def get_or_create_od_mask_node_group():
                if ODMASK_SHADER_NODE in bpy.data.node_groups:
                    return bpy.data.node_groups[ODMASK_SHADER_NODE]
                else:
                    return create_od_mask_node_group()

            # in order to simulate some blending modes special node logic is required
            match special_blend_mode:
                case None:
                    new_mat.node_tree.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
                case enums.SpecialBlendingMode.Add:
                    # mainshader = get_or_create_main_node_group() # Testing

                    transparent_bsdf = new_mat.node_tree.nodes.new('ShaderNodeBsdfTransparent')
                    add_shader = new_mat.node_tree.nodes.new('ShaderNodeAddShader')

                    # new_mat.node_tree.links.new(img_node.outputs[0], transparent_bsdf.inpputs['Color']) # Testing

                    new_mat.node_tree.links.new(bsdf.outputs['BSDF'], add_shader.inputs[0])
                    new_mat.node_tree.links.new(transparent_bsdf.outputs['BSDF'], add_shader.inputs[1])
                    new_mat.node_tree.links.new(add_shader.outputs[0], out.inputs['Surface'])

                case enums.SpecialBlendingMode.Mod:
                    shader_to_rgb = new_mat.node_tree.nodes.new('ShaderNodeShaderToRGB')
                    transparent_bsdf = new_mat.node_tree.nodes.new('ShaderNodeBsdfTransparent')
                    new_mat.node_tree.links.new(bsdf.outputs['BSDF'], shader_to_rgb.inputs[0])
                    new_mat.node_tree.links.new(shader_to_rgb.outputs['Color'], transparent_bsdf.inputs['Color'])
                    new_mat.node_tree.links.new(transparent_bsdf.outputs['BSDF'], out.inputs['Surface'])
        else:
            bsdf = new_mat.node_tree.nodes.new('ShaderNodeBsdfDiffuse')
            new_mat.node_tree.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

        for tex_type, tex_path_and_name in texture_infos.items():
            tex_path_no_ext, tex_short_name = os.path.splitext(tex_path_and_name)

            # skip non-diffuse textures if we do not import PBR
            if not self.load_pbr_maps and not game_profile_impl.is_diffuse_tex_type(tex_type, tex_short_name):
                continue

            # normalize path from config
            tex_path_no_ext = os.path.normpath(tex_path_no_ext)

            # remove leading separator
            tex_path_no_ext = tex_path_no_ext[1:] if tex_path_no_ext.startswith(os.sep) else tex_path_no_ext

            tex_path = tex_path_no_ext + self.texture_format
            tex_path_abs = os.path.join(umodel_export_dir, tex_path)

            tex_lib_path = os.path.join(asset_library_dir, tex_path)
            tex_lib_blend_path = os.path.splitext(tex_lib_path)[0] + '.blend'

            # check if texture is not already in the library
            if not os.path.isfile(tex_lib_blend_path):
                if os.path.isfile(tex_path_abs):
                    self._import_image_to_library(tex_path=tex_path,
                                                  tex_lib_path=tex_lib_path,
                                                  tex_umodel_path=tex_path_abs,
                                                  db=db)
                else:
                    self._warn_print(f"Warning: Material \"{material_name}\" referenced texture \"{tex_path}\" "
                                     ", but it does not exist in the UModel export path.")
                    continue

            if (img := utils.linked_libraries_search(tex_lib_blend_path, bpy.types.Image)) is None:
                # load datablock from the library
                with utils.redirect_cstdout():
                    with bpy.data.libraries.load(filepath=tex_lib_blend_path, link=True) as (data_from, data_to):
                        # we assume there is exactly one texture we have just written there
                        data_to.images = [data_from.images[0]]

                    img = data_to.images[0]

            img_node = new_mat.node_tree.nodes.new('ShaderNodeTexImage')
            img_node.image = img

            if self.load_pbr_maps:
                game_profile_impl.handle_material_texture_pbr(mat=new_mat,
                                                              tex_type=tex_type,
                                                              tex_short_name=tex_short_name,
                                                              img_node=img_node,
                                                              main_shader=get_or_create_main_node_group(),
                                                              orm_shader=get_or_create_orm_extra_node_group(),
                                                              odmask_shader=get_or_create_od_mask_node_group(),
                                                              ao_mix_node=ao_mix,
                                                              bsdf_node=bsdf,
                                                              out_node=out)
            # just simply connect the diffuse map to the shader node, if we do not go the PBR route
            else:
                game_profile_impl.handle_material_texture_simple(mat=new_mat,
                                                                 tex_type=tex_type,
                                                                 tex_short_name=tex_short_name,
                                                                 img_node=img_node,
                                                                 bsdf_node=bsdf)

        # new_mat.asset_generate_preview()
        game_profile_impl.end_process_material(new_mat)

        material_lib_path = os.path.join(asset_library_dir, material_path_local_no_ext) + '.blend'
        os.makedirs(os.path.dirname(material_lib_path), exist_ok=True)
        bpy.data.libraries.write(filepath=material_lib_path, datablocks={new_mat, }, fake_user=True)
        # bpy.data.materials.remove(new_mat, do_unlink=True)

    def _import_asset_to_library(self,
                                 context: bpy.types.Context,
                                 asset_library_dir: str,
                                 asset_path: str,
                                 umodel_export_dir: str,
                                 game_profile: str,
                                 db: t.Optional[asset_db.AssetDB] = None
                                 ) -> None:
        """Import asset (mesh) to an assset library from UModel output.

        :param context: Current Blender context.
        :param asset_library_dir: Directory to store the asset, and its dependencies in.
        :param asset_path: Path to the asset in game format.
        :param umodel_export_dir: UModel/Fmodel output directory to source .psk/.uemodel files from.
        :param game_profile: Game profile to import.
        :param db: Asset database to operate on. If given, no saving is performed, else the function handles
        everything by itself.
        :raises OSError: Raised when an asset was not found in the UModel output dir or failed opening.
        :raises FileNotFounderror: Raised when an asset was not found in the directory.
        :raises RuntimeError: Raised when an asset failed importing due to unknown .psk/.pskx importer issue.
        :raises NotImplementedError: Raised when requested game profile is not implemented or available.
        """

        has_external_db = db is not None
        if db is None:
            db = asset_db.AssetDB(asset_library_dir)

        asset_local_dir = os.path.dirname(asset_path)
        catalog_uid = db.uid_for_entry(asset_local_dir) if asset_local_dir else None
        asset_absolute_dir = os.path.join(asset_library_dir, asset_local_dir)
        asset_path_local_noext = os.path.splitext(asset_path)[0]

        os.makedirs(asset_absolute_dir, exist_ok=True)

        asset_psk_path_noext = os.path.join(umodel_export_dir, asset_path_local_noext)
        asset_uemodel_path_noext = os.path.join(umodel_export_dir, asset_path_local_noext) # UEFormat --

        # Import psk/pskx files
        if self.mesh_format == '.psk':
            pskx_path = asset_psk_path_noext + '.pskx'
            psk_path = asset_psk_path_noext + '.psk'

            found_path = None
            animated = False

            # Check original paths first
            if os.path.isfile(pskx_path):
                found_path = pskx_path
                animated = False
            elif os.path.isfile(psk_path):
                found_path = psk_path
                animated = True
            else:
                # Try fallback paths
                if 'Content' in pskx_path or 'Content' in psk_path:
                    fallback_pskx = pskx_path.replace('Content', 'Game')
                    fallback_psk = psk_path.replace('Content', 'Game')

                    if os.path.isfile(fallback_pskx):
                        found_path = fallback_pskx
                        animated = False
                        utils.verbose_print(f"[Fallback] Using .pskx: {fallback_pskx}")
                    elif os.path.isfile(fallback_psk):
                        found_path = fallback_psk
                        animated = True
                        utils.verbose_print(f"[Fallback] Using .psk: {fallback_psk}")
                    else:
                        raise FileNotFoundError(
                            f"Error: Asset not found in any path:\n"
                            f"- {pskx_path}\n- {psk_path}\n- {fallback_pskx}\n- {fallback_psk}"
                        )
                else:
                    raise FileNotFoundError(
                        f"Error: Asset not found:\n- {pskx_path}\n- {psk_path}"
                    )

            # Import found mesh
            utils.verbose_print(f"Importing \"{found_path}\"")
            with contextlib.redirect_stdout(io.StringIO()):
                if not pskimport(filepath=found_path, context=context, bImportbone=False):
                    raise RuntimeError(f"Error: Failed importing asset {found_path}")

        # Import .uemodel files
        elif self.mesh_format == '.uemodel':
            if os.path.isfile(uemodel_path := asset_uemodel_path_noext + self.mesh_format):
                utils.verbose_print(f"Importing \"{uemodel_path}\"")
                full_path = r"E:\Game_Dumps\Atomic Heart\Game\Meshes\FamaleCorpc_NotLifted_08_Idle_Static.uemodel" # example import, need proper implementation.
                directory = os.path.dirname(full_path)  # "E:\Game_Dumps\Atomic Heart\Game\Meshes"
                filename = os.path.basename(full_path)  # "FamaleCorpc_NotLifted_08_Idle_Static.uemodel"
                result = bpy.ops.uf.import_uemodel(
                    'EXEC_DEFAULT',
                    directory=directory,
                    files=[{"name": filename}]
                )
                print(result)
                if 'FINISHED' not in result:
                    print("Import failed:", result)
                animated = True
            else:
                raise FileNotFoundError(f"Error: Failed importing asset: {asset_uemodel_path_noext} was not found ({self.mesh_format}).")

        obj = context.object

        # mark object as asset
        obj.asset_mark()
        obj.asset_data.catalog_id = catalog_uid

        # handle materials
        new_materials = []

        # # - read material descriptor file and identify associated materials
        try:
            # pylint: disable=unpacking-non-sequence
            _, mat_descriptors_paths = props_txt_parser.parse_props_txt(asset_psk_path_noext + '.props.txt',
                                                                        mode='MESH')
        except OSError:
            self._warn_print(f"Warning: Loading material descriptor {asset_psk_path_noext + '.props.txt'} failed. "
                             "Materials will not be avaialble for the imported object.")
        else:
            # attempt to obtain materials manually if descriptor is not available
            mat_desc_order_map = {mat.name: None for mat in obj.data.materials}

            if animated and not mat_descriptors_paths:
                if os.path.isdir(mat_dir := os.path.join(os.path.dirname(psk_path), 'Materials')):
                    for root, _, files in os.walk(mat_dir):
                        for file in files:
                            if not file.endswith('.props.txt'):
                                continue

                            file_abs = os.path.splitext(os.path.splitext(os.path.join(root, file))[0])[0]
                            mat_name = os.path.basename(file_abs)

                            if mat_name not in mat_desc_order_map:
                                self._warn_print(f"Warning: Found extra material {mat_name} in the Materials dir. "
                                                 "It won't be imported.")
                                continue

                            mat_desc_order_map[mat_name] = f"{os.path.relpath(file_abs, umodel_export_dir)}.{mat_name}"

                    if any(mat_desc is None for mat_desc in mat_desc_order_map.values()):
                        print(f"Warning: Material count mismatch for asset \"{obj.name}\".")
                        mesh = obj.data

                        bpy.data.objects.remove(obj, do_unlink=True)
                        bpy.data.meshes.remove(mesh, do_unlink=True)

                        old_materials = list(mesh.materials)

                        # perform cleanup before raising
                        for mat in old_materials:
                            try:
                                bpy.data.materials.remove(mat, do_unlink=True)
                                print("removed old materials")
                            except ReferenceError:  # TODO: figure out why?
                                pass

                        raise FileNotFoundError()

                    mat_descriptors_paths = list(mat_desc_order_map.values())

            # replace materials
            old_materials = list(obj.data.materials)

            # initialize each material and populate it with data
            for mat_desc_path in mat_descriptors_paths:
                material_path_local_no_ext, material_name = os.path.splitext(mat_desc_path)
                material_name = material_name[1:]  # removing the .

                # normalize path from config
                material_path_local_no_ext = os.path.normpath(material_path_local_no_ext)

                # remove leading separator
                material_path_local_no_ext = material_path_local_no_ext[1:] \
                    if material_path_local_no_ext.startswith(os.sep) else material_path_local_no_ext

                material_path_local = material_path_local_no_ext + '.props.txt'
                material_lib_path = os.path.join(asset_library_dir, material_path_local_no_ext) + '.blend'

                try:
                    # add material to asset library if does not exist
                    if not os.path.isfile(material_lib_path):
                        self._import_material_to_library(material_name=material_name,
                                                         material_path_local=material_path_local,
                                                         db=db,
                                                         umodel_export_dir=umodel_export_dir,
                                                         asset_library_dir=asset_library_dir,
                                                         game_profile=game_profile)

                    if (new_mat := utils.linked_libraries_search(material_lib_path, bpy.types.Material)) is None:
                        # load material from the library
                        with utils.redirect_cstdout():
                            with bpy.data.libraries.load(filepath=material_lib_path, link=True) as (data_from, data_to):
                                # we presume there is exactly one material in the library, no validation performed
                                data_to.materials = [data_from.materials[0]]

                            new_mat = data_to.materials[0]
                            print("Only using one material from library, even though multiple might be present")

                except FileNotFoundError as e:
                    new_mat = bpy.data.materials.new(f"{material_name}_Placeholder")
                    self._warn_print(f"Warning: Material \"{material_name}\" failed to load, placeholder used instead. "
                                     f"({e}).")

                except OSError:
                    new_mat = bpy.data.materials.new(f"{material_name}_Placeholder")
                    self._warn_print(f"Warning: Material \"{material_name}\" failed to load, placeholder used instead.")

                new_materials.append((new_mat, material_name))

            for mat, mat_name in new_materials:
                if mat_name in obj.data.materials:
                    obj.data.materials[obj.data.materials.find(mat_name)] = mat
                else:
                    obj.data.materials.append(mat)

            # # remove original materials
            # for mat in old_materials:
            #     try:
            #         bpy.data.materials.remove(mat, do_unlink=True)
            #         print("removed old materials = 2")
            #     except ReferenceError:  # TODO: figure out why?
            #         pass

        # obj.asset_generate_preview()

        asset_abs_lib_path = os.path.join(asset_library_dir, asset_path_local_noext) + '.blend'
        os.makedirs(os.path.dirname(asset_abs_lib_path), exist_ok=True)

        if self.overwrite and os.path.isfile(asset_abs_lib_path):
            print(f"[Overwrite] Removing existing library asset: {asset_abs_lib_path}")
            os.remove(asset_abs_lib_path)

        bpy.data.libraries.write(asset_abs_lib_path, {obj, }, fake_user=True)

        # cleanup
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh, do_unlink=True)

        for mat, _ in new_materials:
            # Only remove if we're not linking/attaching assets to the scene.
            if not (self.link_to_scene or self.append_to_scene):
                try:
                    bpy.data.materials.remove(mat, do_unlink=True)
                    print("removed new materials")
                except ReferenceError:
                    pass

        if not has_external_db:
            db.save_db()
