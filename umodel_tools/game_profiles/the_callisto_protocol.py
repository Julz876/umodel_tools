"""This module implements support for Dead Island 2 game.
Known issues:
    - Blended materials are not properly supported. Currently the first texture is used.
"""

import enum
import typing as t
from typing import TypeAlias, Tuple, Dict
import dataclasses

import bpy
import lark


GAME_NAME = "The Callisto Protocol"
GAME_DESCRIPTION = "The Callisto Protocol (2022) by Striking Distance Studios and Krafton"

class TextureMapTypes(enum.Enum):
    """All texture map types supported by the material generator.
    """
    Diffuse = enum.auto()
    Normal = enum.auto()
    ATX = enum.auto()
    AHA = enum.auto()
    MRO = enum.auto()
    ORM = enum.auto()
    ORMS = enum.auto()
    SSS = enum.auto()
    MSK = enum.auto()
    M = enum.auto()
    WEAR_MSK = enum.auto()

#: Suffixes of textures for automatic texture purpose guessing (lowercase only)
SUFFIX_MAP = {
    'd': TextureMapTypes.Diffuse,
    'n': TextureMapTypes.Normal,
    'mro': TextureMapTypes.MRO,
    'bm': TextureMapTypes.MSK,
    'atx': TextureMapTypes.ATX,
    'aha': TextureMapTypes.AHA,

    #: Extra Suffixes (Uppercase)
    'D': TextureMapTypes.Diffuse,
    'N': TextureMapTypes.Normal,
    'MRO': TextureMapTypes.MRO,
    'BM': TextureMapTypes.MSK,
    'ATX': TextureMapTypes.ATX,
    'AHA': TextureMapTypes.AHA,

    "Alpha Mask Texture": TextureMapTypes.M,
    "PM_Diffuse": TextureMapTypes.Diffuse,
    "Diffuse Map": TextureMapTypes.Diffuse,
    "PM_Normals": TextureMapTypes.Normal,
    "Normal Map": TextureMapTypes.Normal,
    "PM_SpecularMasks": TextureMapTypes.ORM,
    "ORM Map": TextureMapTypes.ORM,
    "SSS Map": TextureMapTypes.SSS,

    "M": TextureMapTypes.M,
    "_M": TextureMapTypes.M,
    "D": TextureMapTypes.Diffuse,
    "_D": TextureMapTypes.Diffuse,
    "N": TextureMapTypes.Normal,
    "_N": TextureMapTypes.Normal,
    "ORM": TextureMapTypes.ORM,
    "_ORM": TextureMapTypes.ORM,
    "ORMS": TextureMapTypes.ORM,
    "_ORMS": TextureMapTypes.ORM,
    "SSS": TextureMapTypes.SSS,
    "_SSS": TextureMapTypes.SSS,
}


@dataclasses.dataclass
class MaterialContext:
    bsdf_node: t.Optional[bpy.types.ShaderNodeBsdfPrincipled | bpy.types.ShaderNodeBsdfDiffuse]
    desc_ast: lark.Tree
    use_pbr: bool
    msk_index: int = dataclasses.field(default=0)
    diffuse_connected: bool = dataclasses.field(default=False)
    linked_maps: set[TextureMapTypes.Diffuse] = dataclasses.field(default_factory=set)

_state_buffer: dict[bpy.types.Material, MaterialContext] = {}


def process_material(mat: bpy.types.Material, desc_ast: lark.Tree, use_pbr: bool):  # pylint: disable=unused-argument
    _state_buffer[mat] = MaterialContext(bsdf_node=None, desc_ast=desc_ast, use_pbr=use_pbr)


def do_process_texture(tex_type: str, tex_short_name: str) -> bool:  # pylint: disable=unused-argument
    return bool(_short_name_to_tex_type(tex_short_name))


def is_diffuse_tex_type(tex_type: str, tex_short_name: str) -> bool:  # pylint: disable=unused-argument
    return _short_name_to_tex_type(tex_short_name) == {TextureMapTypes.Diffuse, TextureMapTypes.MSK}


def handle_material_texture_pbr(mat: bpy.types.Material,
                                tex_type: str,  # pylint: disable=unused-argument
                                tex_short_name: str,
                                img_node: bpy.types.ShaderNodeTexImage,
                                ao_mix_node: bpy.types.ShaderNodeMix,
                                bsdf_node: bpy.types.ShaderNodeBsdfPrincipled,
                                out_node: bpy.types.ShaderNodeOutputMaterial):
    # Note: we presume AHA and ATX are mutually exclusive and never appear together.
    # This is not validated.
    mat_ctx = _state_buffer[mat]
    mat_ctx.bsdf_node = bsdf_node

    # Set the location of nodes in the node editor
    ao_node = mat.node_tree.nodes.new('ShaderNodeAmbientOcclusion')
    ao_node.location = (-400, 100)
    mix_node = mat.node_tree.nodes.new('ShaderNodeMixRGB')
    mix_node.location = (-200, 50)
    ao_mix_node.location = (-200, 300)
    bsdf_node.location = (100, 20)
    out_node.location = (600, 0)

    bl_tex_type = _short_name_to_tex_type(tex_short_name)

    # do not connect the same texture twice
    if bl_tex_type in mat_ctx.linked_maps:
        return

    def create_mix_node(mat, loc_x, loc_y, color, default_value):
            # Using ShaderNodeMixRGB instead of ShaderNodeMix
            mix_node = mat.node_tree.nodes.new('ShaderNodeMixRGB')
            mix_node.location = (loc_x, loc_y)
            # mix_node.data_type = 'RGBA'
            # mix_node.blend_type = 'MIX'

            # Extract only the RGB values, discarding the alpha
            #rgb_color = color[:3] if color is not None else default_value[:3]

            # Ensure the color is a 4-tuple (RGBA) by appending 1.0 as alpha if necessary
            rgba_color = color if len(color) == 4 else (color[0], color[1], color[2], 1.0)

            # Assign the RGB values to the inputs[2] of the Mix node
            mix_node.inputs[2].default_value = rgba_color

            return mix_node
    
    # remember that we processed a texture of that type
    mat_ctx.linked_maps.add(bl_tex_type)

    match bl_tex_type:
        case TextureMapTypes.Diffuse:
            img_node.location = (-750, 150)
            img_node.image.colorspace_settings.name = 'sRGB'
            mat.node_tree.links.new(img_node.outputs['Color'], ao_node.inputs['Color'])
            mat.node_tree.links.new(img_node.outputs['Color'], mix_node.inputs[1])
            mat.node_tree.links.new(ao_node.outputs['Color'], mix_node.inputs[2])
            mat.node_tree.links.new(mix_node.outputs['Color'], bsdf_node.inputs['Base Color'])
            
            img_node.select = True
            mat.node_tree.nodes.active = img_node
            mat_ctx.diffuse_connected = True
            
        case TextureMapTypes.Normal:
            normal_map_node = mat.node_tree.nodes.new('ShaderNodeNormalMap')
            normal_map_node.location = (-400, -500)
            img_node.location = (-750, -500)
            img_node.image.colorspace_settings.name = 'Non-Color'
            mat.node_tree.links.new(img_node.outputs['Color'], normal_map_node.inputs['Color'])
            normal_map_node.inputs[0].default_value = 2
            mat.node_tree.links.new(normal_map_node.outputs['Normal'], bsdf_node.inputs['Normal'])
            mat.node_tree.links.new(normal_map_node.outputs['Normal'], ao_node.inputs['Normal'])
            
        case TextureMapTypes.ATX:
            atx_split_node = mat.node_tree.nodes.new('ShaderNodeSeparateColor')
            atx_split_node.location = (-400, -700)
            img_node.location = (-750, -800)
            img_node.image.colorspace_settings.name = 'Non-Color'
            mat.node_tree.links.new(img_node.outputs['Color'], atx_split_node.inputs['Color'])
            mat.node_tree.links.new(atx_split_node.outputs['Red'], bsdf_node.inputs['Alpha'])
            
        case TextureMapTypes.AHA:
            # Split Channels
            aha_split_node = mat.node_tree.nodes.new('ShaderNodeSeparateColor')
            aha_split_node.location = (-400, -900)

            # height component
            displacement_node = mat.node_tree.nodes.new('ShaderNodeDisplacement')
            displacement_node.location = (400, -500)
            img_node.location = (-750, -1100)
            img_node.image.colorspace_settings.name = 'Non-Color'
            mat.node_tree.links.new(displacement_node.outputs['Displacement'], out_node.inputs['Displacement'])
            mat.node_tree.links.new(img_node.outputs['Color'], aha_split_node.inputs['Color'])
            mat.node_tree.links.new(aha_split_node.outputs['Green'], displacement_node.inputs['Height'])
            displacement_node.inputs[2].default_value = 0.1

        case TextureMapTypes.ORM:
            mix_node.blend_type = 'MULTIPLY'
            mro_split = mat.node_tree.nodes.new('ShaderNodeSeparateColor')
            mro_split.location = (-400, -300)
            invert_node = mat.node_tree.nodes.new('ShaderNodeInvert')
            invert_node.location = (-200, -350)
            invert2_node = mat.node_tree.nodes.new('ShaderNodeInvert')
            invert2_node.location = (-200, -200)
            img_node.location = (-750, -150)
            img_node.image.colorspace_settings.name = 'Non-Color'
            mat.node_tree.links.new(img_node.outputs['Color'], mro_split.inputs['Color'])
            mat.node_tree.links.new(mro_split.outputs['Red'], invert2_node.inputs[0])
            mat.node_tree.links.new(mro_split.outputs['Red'], invert2_node.inputs[1])
            mat.node_tree.links.new(invert2_node.outputs['Color'], bsdf_node.inputs['Metallic'])
            mat.node_tree.links.new(mro_split.outputs['Green'], bsdf_node.inputs['Roughness'])
            mat.node_tree.links.new(mro_split.outputs['Green'], invert_node.inputs['Color'])
            mat.node_tree.links.new(invert_node.outputs['Color'], bsdf_node.inputs[13])
            mat.node_tree.links.new(mro_split.outputs['Blue'], mix_node.inputs[0])

        case TextureMapTypes.WEAR_MSK:
            mat_ctx.msk_index += 1

        case TextureMapTypes.MSK:
            mat_ctx = _state_buffer[mat]
            mask_colors = _get_mask_colors(ast=mat_ctx.desc_ast)

            img_node.location = (-900, 200)
            img_node.image.colorspace_settings.name = 'Non-Color'

            # Retrieve colors for each mask channel
            color1 = mask_colors.get(f'color {mat_ctx.msk_index + 1}', (0, 0, 1, 1))
            color2 = mask_colors.get(f'color {mat_ctx.msk_index + 2}', (0, 1, 0, 1))
            color3 = mask_colors.get(f'color {mat_ctx.msk_index + 3}', (1, 0, 0, 1))
            color4 = mask_colors.get(f'plastic base colour', (0.067708, 0.066298, 0.066298, 1))

            # Separate the color channels
            msk_split = mat.node_tree.nodes.new('ShaderNodeSeparateColor')
            msk_split.location = (-700, -200)

            # Create mix nodes for each color
            b_mix = create_mix_node(mat, -500, -200, color1, (0, 0, 1, 1))
            g_mix = create_mix_node(mat, -300, -200, color2, (0, 1, 0, 1))
            r_mix = create_mix_node(mat, -100, -200, color3, (1, 0, 0, 1))
            plastic_mix = create_mix_node(mat, 100, -200, color4, (0.067708, 0.066298, 0.066298, 1))

            # Connect nodes
            mat.node_tree.links.new(img_node.outputs['Color'], msk_split.inputs['Color'])
            mat.node_tree.links.new(msk_split.outputs['Red'], r_mix.inputs[0])
            mat.node_tree.links.new(msk_split.outputs['Green'], g_mix.inputs[0])
            mat.node_tree.links.new(msk_split.outputs['Blue'], b_mix.inputs[0])

            # Connect the mix nodes together
            mat.node_tree.links.new(b_mix.outputs['Color'], g_mix.inputs[1])
            mat.node_tree.links.new(g_mix.outputs['Color'], r_mix.inputs[1])
            mat.node_tree.links.new(r_mix.outputs['Color'], plastic_mix.inputs[1])

            # Connect the final result to the BSDF node
            if not mat_ctx.diffuse_connected:
                mat.node_tree.links.new(plastic_mix.outputs['Color'], bsdf_node.inputs[0])
                mat.node_tree.links.new(img_node.outputs['Alpha'], bsdf_node.inputs['Alpha'])
                img_node.select = True
                mat.node_tree.nodes.active = img_node
                img_node.location = (-950, -250)
                img_node.image.colorspace_settings.name = 'Non-Color'

            mat_ctx.msk_index += 1

            print(f"mask_colors: {mask_colors}")
            print(f"color1: {color1}, color2: {color2}, color3: {color3}, color4: {color4}")


def handle_material_texture_simple(mat: bpy.types.Material,
                                   tex_type: str,  # pylint: disable=unused-argument
                                   tex_short_name: str,  # pylint: disable=unused-argument
                                   img_node: bpy.types.ShaderNodeTexImage,
                                   bsdf_node: bpy.types.ShaderNodeBsdfDiffuse):
    _state_buffer[mat].bsdf_node = bsdf_node

    mat.node_tree.links.new(img_node.outputs['Color'], bsdf_node.inputs['Color'])
    img_node.select = True
    mat.node_tree.nodes.active = img_node

def end_process_material(mat: bpy.types.Material):
    mat_ctx = _state_buffer[mat]

    if mat_ctx.use_pbr and mat_ctx.bsdf_node is not None:
        # set defaults
        mat_ctx.bsdf_node.inputs[3].default_value = 1.4  # IOR
        mat_ctx.bsdf_node.inputs[1].default_value = 0.3  # Metallic
        mat_ctx.bsdf_node.inputs[12].default_value = 1.0   # Specular IOR Level
        mat_ctx.bsdf_node.inputs[2].default_value = 0.1  # Roughness
        mat_ctx.bsdf_node.inputs[23].default_value = 0.1  # Sheen Weight
        mat_ctx.bsdf_node.inputs[19].default_value = 0.030  # Clearcoat roughness
        mat_ctx.bsdf_node.inputs[20].default_value = 1.4  # Clearcoat IOR

    del _state_buffer[mat]


# Non-interface functions below

def _short_name_to_tex_type(tex_short_name: str) -> t.Optional[TextureMapTypes]:
    """Convert short texture name to a recognized texture map type if possible.

    :return: TextureMapType or None.
    """
    return SUFFIX_MAP.get(tex_short_name.lower().split('_')[-1])


Color: t.TypeAlias = tuple[float, float, float, float]

def _get_mask_colors(ast: lark.Tree) -> Dict[str, Color]:
    """Get MSK colors from texture parameters.

    :param ast: .props.txt AST
    :return: dictionary mapping color names to values.
    """
    colors = {}

    for child in ast.children:
        assert child.data == 'definition'
        def_name, array_qual, value = child.children

        match def_name:
            case 'VectorParameterValues':
                assert array_qual is not None
                assert value.data == 'structured_block'

                for tex_param_def in value.children:
                    _, _, tex_param = tex_param_def.children
                    param_info, param_val, _ = tex_param.children  # ParameterInfo, ParameterValue, ParameterName
                    _, _, color_vec = param_val.children

                    color_name = param_info.children[2].children[0].children[2].children[0].value.strip()

                    # Ignore unused materials
                    if color_vec.data != 'structured_block':
                        continue

                    color = {
                        'r': 0.0,
                        'g': 0.0,
                        'b': 0.0,
                        'a': 1.0
                    }

                    not_a_color = False
                    for channel_def in color_vec.children:
                        channel_name, _, channel = channel_def.children
                        channel_name = channel_name.lower()

                        if channel_name not in {'r', 'g', 'b', 'a'}:
                            not_a_color = True
                            continue

                        color[channel_name] = float(channel.children[0].value)

                    if not_a_color:
                        continue

                    colors[color_name.lower()] = (color['r'], color['g'], color['b'], color['a'])

    return colors