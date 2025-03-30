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


GAME_NAME = "Dead Island 2"
GAME_DESCRIPTION = "Dead Island 2 (2023) by Deep Silver"

# Node Socket Types
COLOR_SOCKET_NODE = 'NodeSocketColor' #
FLOAT_SOCKET_NODE = 'NodeSocketFloat' #
VECTOR_SOCKET_NODE = 'NodeSocketVector' #
BOOL_SOCKET_NODE = 'NodeSocketBool' #

class TextureMapTypes(enum.Enum):
    """All texture map types supported by the material generator.
    """
    Diffuse = enum.auto()
    Normal = enum.auto()
    ATX = enum.auto()
    ATR = enum.auto()
    AHA = enum.auto()
    MRO = enum.auto()
    DRO = enum.auto()
    EMISSION = enum.auto()
    MSK = enum.auto()
    WEAR_MSK = enum.auto()

#: Suffixes of textures for automatic texture purpose guessing (lowercase only)
SUFFIX_MAP = {
    'd': TextureMapTypes.Diffuse,
    'n': TextureMapTypes.Normal,
    'e': TextureMapTypes.EMISSION,
    'mro': TextureMapTypes.MRO,
    'dro': TextureMapTypes.DRO,
    'bm': TextureMapTypes.MSK,
    'atx': TextureMapTypes.ATX,
    'atr': TextureMapTypes.ATR,
    'aha': TextureMapTypes.AHA,

    #: Extra Suffixes (Uppercase)
    'D': TextureMapTypes.Diffuse,
    'N': TextureMapTypes.Normal,
    'E': TextureMapTypes.EMISSION,
    'MRO': TextureMapTypes.MRO,
    'DRO': TextureMapTypes.DRO,
    'BM': TextureMapTypes.MSK,
    'ATX': TextureMapTypes.ATX,
    'ATR': TextureMapTypes.ATR,
    'AHA': TextureMapTypes.AHA,
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
                                main_shader: bpy.types.ShaderNodeTree,
                                orm_shader: bpy.types.ShaderNodeTree,
                                odmask_shader: bpy.types.ShaderNodeTree,
                                ao_mix_node: bpy.types.ShaderNodeMix,
                                bsdf_node: bpy.types.ShaderNodeBsdfPrincipled,
                                out_node: bpy.types.ShaderNodeOutputMaterial):
    # Note: we presume AHA and ATX are mutually exclusive and never appear together.
    # This is not validated.
    mat_ctx = _state_buffer[mat]
    mat_ctx.bsdf_node = bsdf_node

    ao_mix_node.location = (-100, 300)
    # ao_mix_node.inputs['B'].default_value = (0.0,0.0,0.0,1.0) # Default Black

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
    
    def create_rgb_mask_tint_group():
        group_name = "RGBMaskTintGroup"
        if group_name in bpy.data.node_groups:
            return bpy.data.node_groups[group_name]

        node_group = bpy.data.node_groups.new(group_name, 'ShaderNodeTree')

        # Inputs
        node_group.interface.new_socket(name="Image", description="Color input", in_out='INPUT', socket_type=COLOR_SOCKET_NODE)
        node_group.interface.new_socket(name="Color R", description="Red channel input", in_out='INPUT', socket_type=COLOR_SOCKET_NODE)
        node_group.interface.new_socket(name="Color G", description="Green channel input", in_out='INPUT', socket_type=COLOR_SOCKET_NODE)
        node_group.interface.new_socket(name="Color B", description="Blue channel input", in_out='INPUT', socket_type=COLOR_SOCKET_NODE)
        node_group.interface.new_socket(name="Color A", description="Alpha channel input", in_out='INPUT', socket_type=COLOR_SOCKET_NODE)
        node_group.interface.new_socket(name="Tint", in_out='INPUT', socket_type=BOOL_SOCKET_NODE)

        # Outputs
        node_group.interface.new_socket(name="Color", description="Color output", in_out='OUTPUT', socket_type=COLOR_SOCKET_NODE)
        node_group.interface.new_socket(name="R", description="Red channel output", in_out='OUTPUT', socket_type=FLOAT_SOCKET_NODE)
        node_group.interface.new_socket(name="G", description="Green channel output", in_out='OUTPUT', socket_type=FLOAT_SOCKET_NODE)
        node_group.interface.new_socket(name="B", description="Blue channel output", in_out='OUTPUT', socket_type=FLOAT_SOCKET_NODE)
        node_group.interface.new_socket(name="A", description="Alpha channel output", in_out='OUTPUT', socket_type=FLOAT_SOCKET_NODE)

        nodes = node_group.nodes
        links = node_group.links
        nodes.clear()

        input_node = nodes.new("NodeGroupInput")
        input_node.location = (-1000, 0)

        output_node = nodes.new("NodeGroupOutput")
        output_node.location = (600, 0)

        separate = nodes.new("ShaderNodeSeparateColor")
        separate.location = (-700, 0)

        # input_node.inputs['Color A'].default_value = (0.0,0.0,0.0,1.0) # Default Alpha Color
        # output_node.outputs['A'].default_value = (0.0,0.0,0.0,1.0) # Default Alpha Color

        # R Mix
        r_mix = nodes.new("ShaderNodeMixRGB")
        r_mix.blend_type = 'MULTIPLY'
        r_mix.inputs['Fac'].default_value = 1.0
        r_mix.label = 'R Mix'
        r_mix.location = (-400, 200)

        # G Mix
        g_mix = nodes.new("ShaderNodeMixRGB")
        g_mix.blend_type = 'MULTIPLY'
        g_mix.inputs['Fac'].default_value = 1.0
        g_mix.label = 'G Mix'
        g_mix.location = (-400, 0)

        # B Mix
        b_mix = nodes.new("ShaderNodeMixRGB")
        b_mix.blend_type = 'MULTIPLY'
        b_mix.inputs['Fac'].default_value = 1.0
        b_mix.label = 'B Mix'
        b_mix.location = (-400, -200)

        # Add R + G
        add_rg = nodes.new("ShaderNodeMixRGB")
        add_rg.blend_type = 'ADD'
        add_rg.inputs['Fac'].default_value = 1.0
        add_rg.label = 'Add RG'
        add_rg.location = (-100, 100)

        # Add above + B
        add_rgb = nodes.new("ShaderNodeMixRGB")
        add_rgb.blend_type = 'ADD'
        add_rgb.inputs['Fac'].default_value = 1.0
        add_rgb.label = 'Add RGB'
        add_rgb.location = (200, 0)

        # Tint switch
        switch = nodes.new("ShaderNodeMix")
        # switch.blend_type = 'MIX'
        switch.label = 'Tint Switch'
        switch.location = (400, 100)

        # Link inputs
        links.new(input_node.outputs['Image'], separate.inputs['Color'])
        links.new(input_node.outputs['Image'], switch.inputs['A'])
        # links.new(separate.outputs['Red'], r_mix.inputs['Fac'])
        # links.new(separate.outputs['Green'], g_mix.inputs['Fac'])
        # links.new(separate.outputs['Blue'], b_mix.inputs['Fac'])

        links.new(separate.outputs['Red'], r_mix.inputs['Color1'])
        links.new(separate.outputs['Green'], g_mix.inputs['Color1'])
        links.new(separate.outputs['Blue'], b_mix.inputs['Color1'])

        links.new(input_node.outputs['Color R'], r_mix.inputs['Color2'])
        links.new(input_node.outputs['Color G'], g_mix.inputs['Color2'])
        links.new(input_node.outputs['Color B'], b_mix.inputs['Color2'])

        links.new(r_mix.outputs['Color'], add_rg.inputs['Color1'])
        links.new(g_mix.outputs['Color'], add_rg.inputs['Color2'])

        links.new(add_rg.outputs['Color'], add_rgb.inputs['Color1'])
        links.new(b_mix.outputs['Color'], add_rgb.inputs['Color2'])
        links.new(add_rgb.outputs['Color'], switch.inputs['B'])
        links.new(input_node.outputs['Tint'], switch.inputs[0]) # Bool switch

        # Output final color
        links.new(switch.outputs[0], output_node.inputs['Color'])

        # Optional passthrough channels
        links.new(separate.outputs['Red'], output_node.inputs[1])
        links.new(separate.outputs['Green'], output_node.inputs[2])
        links.new(separate.outputs['Blue'], output_node.inputs[3])

        # # Alpha passthrough
        # separate_alpha = nodes.new("ShaderNodeSeparateRGBA")
        # separate_alpha.location = (-700, -300)
        # links.new(input_node.outputs['Mask Image'], separate_alpha.inputs['Image'])
        # links.new(separate_alpha.outputs['Alpha'], output_node.inputs[4])

        links.new(input_node.outputs['Color A'], output_node.inputs['A']) # Temp Connection

        return node_group

    def create_roughness_mask_group():
        group_name = "RoughnessMaskGroup"
        if group_name in bpy.data.node_groups:
            return bpy.data.node_groups[group_name]

        node_group = bpy.data.node_groups.new(group_name, 'ShaderNodeTree')

        # Inputs
        node_group.interface.new_socket(name="ORM Image", description="RGB: Roughness, Metallic, AO", in_out='INPUT', socket_type=COLOR_SOCKET_NODE)
        node_group.interface.new_socket(name="AO Scale", description="B channel multiplier", in_out='INPUT', socket_type=FLOAT_SOCKET_NODE)
        node_group.interface.new_socket(name="Roughness Scale", description="R channel multiplier", in_out='INPUT', socket_type=FLOAT_SOCKET_NODE)
        node_group.interface.new_socket(name="Metallic Scale", description="G channel multiplier", in_out='INPUT', socket_type=FLOAT_SOCKET_NODE)

        # Outputs
        node_group.interface.new_socket(name="AO", description="AO output", in_out='OUTPUT', socket_type=FLOAT_SOCKET_NODE)
        node_group.interface.new_socket(name="Roughness", description="Roughness output", in_out='OUTPUT', socket_type=FLOAT_SOCKET_NODE)
        node_group.interface.new_socket(name="Metallic", description="Metallic output", in_out='OUTPUT', socket_type=FLOAT_SOCKET_NODE)

        nodes = node_group.nodes
        links = node_group.links
        nodes.clear()

        input_node = nodes.new("NodeGroupInput")
        input_node.location = (-600, 0)

        output_node = nodes.new("NodeGroupOutput")
        output_node.location = (600, 0)

        separate = nodes.new("ShaderNodeSeparateColor")
        separate.location = (-300, 0)

        # Multipliers
        r_mult = nodes.new("ShaderNodeMath")
        r_mult.operation = 'MULTIPLY'
        r_mult.label = 'AO * Scale'
        r_mult.location = (100, 200)

        g_mult = nodes.new("ShaderNodeMath")
        g_mult.operation = 'MULTIPLY'
        g_mult.label = 'Roughness * Scale'
        g_mult.location = (100, 0)

        b_mult = nodes.new("ShaderNodeMath")
        b_mult.operation = 'MULTIPLY'
        b_mult.label = 'Metallic * Scale'
        b_mult.location = (100, -200)

        # Connect image to separate
        links.new(input_node.outputs['ORM Image'], separate.inputs['Color'])

        # R channel
        links.new(separate.outputs['Red'], r_mult.inputs[0])
        links.new(input_node.outputs['AO Scale'], r_mult.inputs[1])
        links.new(r_mult.outputs[0], output_node.inputs['AO'])

        # G channel
        links.new(separate.outputs['Green'], g_mult.inputs[0])
        links.new(input_node.outputs['Roughness Scale'], g_mult.inputs[1])
        links.new(g_mult.outputs[0], output_node.inputs['Roughness'])

        # B channel
        links.new(separate.outputs['Blue'], b_mult.inputs[0])
        links.new(input_node.outputs['Metallic Scale'], b_mult.inputs[1])
        links.new(b_mult.outputs[0], output_node.inputs['Metallic'])
        return node_group

    def create_directx_to_opengl_normal_group():
        group_name = "DirectXToOpenGLNormal"
        if group_name in bpy.data.node_groups:
            return bpy.data.node_groups[group_name]

        group = bpy.data.node_groups.new(group_name, 'ShaderNodeTree')

        # Define socket types
        BOOL_SOCKET_NODE = 'NodeSocketBool'

        # Inputs
        group.interface.new_socket(name="DirectX Normal", in_out='INPUT', socket_type=COLOR_SOCKET_NODE)
        group.interface.new_socket(name="Flip Y", in_out='INPUT', socket_type=BOOL_SOCKET_NODE)
        group.interface.new_socket(name="Strength", in_out='INPUT', socket_type=FLOAT_SOCKET_NODE)

        # Outputs
        group.interface.new_socket(name="OpenGL Normal", in_out='OUTPUT', socket_type=VECTOR_SOCKET_NODE)

        nodes = group.nodes
        links = group.links
        nodes.clear()

        input_node = nodes.new("NodeGroupInput")
        input_node.location = (-800, 0)

        output_node = nodes.new("NodeGroupOutput")
        output_node.location = (400, 0)

        separate = nodes.new("ShaderNodeSeparateColor")
        separate.location = (-600, 0)

        # Invert math node: 1 - G
        invert = nodes.new("ShaderNodeMath")
        invert.operation = 'SUBTRACT'
        invert.inputs[0].default_value = 1.0
        invert.location = (-300, 100)

        # Mix: if Flip Y is enabled, use inverted green, otherwise pass original
        mix_green = nodes.new("ShaderNodeMix")
        mix_green.data_type = 'FLOAT'
        mix_green.location = (-100, 100)

        combine = nodes.new("ShaderNodeCombineColor")
        combine.location = (100, 0)

        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.inputs[0].default_value = 1.2
        normal_map.location = (250, 0)

        # Connect DirectX input to Separate Color
        links.new(input_node.outputs['DirectX Normal'], separate.inputs['Color'])
        links.new(input_node.outputs['Strength'], normal_map.inputs[0])

        # Invert G
        links.new(separate.outputs['Green'], invert.inputs[1])
        links.new(invert.outputs[0], mix_green.inputs[2])  # Inverted G
        links.new(separate.outputs['Green'], mix_green.inputs[3])  # Original G
        links.new(input_node.outputs['Flip Y'], mix_green.inputs['Factor'])

        # Combine back
        links.new(separate.outputs['Red'], combine.inputs['Red'])
        links.new(mix_green.outputs[0], combine.inputs['Green'])
        links.new(separate.outputs['Blue'], combine.inputs['Blue'])

        # Plug into normal map node
        links.new(combine.outputs['Color'], normal_map.inputs['Color'])

        # Final output
        links.new(normal_map.outputs['Normal'], output_node.inputs['OpenGL Normal'])

        return group

    def create_mapping_group():
        group_name = "MappingGroup"
        if group_name in bpy.data.node_groups:
            return bpy.data.node_groups[group_name]

        group = bpy.data.node_groups.new(group_name, 'ShaderNodeTree')

        VECTOR_SOCKET_NODE = 'NodeSocketVector'

        # Inputs
        group.interface.new_socket(name="Scale", in_out='INPUT', socket_type=VECTOR_SOCKET_NODE)

        # Outputs
        group.interface.new_socket(name="UV0", in_out='OUTPUT', socket_type=VECTOR_SOCKET_NODE)
        group.interface.new_socket(name="UV1", in_out='OUTPUT', socket_type=VECTOR_SOCKET_NODE)
        group.interface.new_socket(name="UV2", in_out='OUTPUT', socket_type=VECTOR_SOCKET_NODE)

        nodes = group.nodes
        links = group.links
        nodes.clear()

        input_node = nodes.new("NodeGroupInput")
        input_node.location = (-800, 0)

        output_node = nodes.new("NodeGroupOutput")
        output_node.location = (400, 0)

        # Attribute Node (Custom UV Set)
        attribute = nodes.new('ShaderNodeAttribute')
        attribute.attribute_name = "EXTRAUVS0"
        attribute.location = (-600, 0)

        attribute1 = nodes.new('ShaderNodeAttribute')
        attribute1.attribute_name = "EXTRAUVS1"
        attribute1.location = (-600, -150)

        attribute2 = nodes.new('ShaderNodeAttribute')
        attribute2.attribute_name = "EXTRAUVS2"
        attribute2.location = (-600, -300)

        # Mapping Node
        mapping = nodes.new('ShaderNodeMapping')
        mapping.vector_type = 'POINT'
        mapping.location = (-200, 0)

        mapping1 = nodes.new('ShaderNodeMapping')
        mapping1.vector_type = 'POINT'
        mapping1.location = (-100, 0)

        mapping2 = nodes.new('ShaderNodeMapping')
        mapping2.vector_type = 'POINT'
        mapping2.location = (0, 0)

        # Connect nodes
        links.new(input_node.outputs['Scale'], mapping.inputs['Scale'])
        links.new(input_node.outputs['Scale'], mapping1.inputs['Scale'])
        links.new(input_node.outputs['Scale'], mapping2.inputs['Scale'])
        links.new(attribute.outputs['Vector'], mapping.inputs['Vector'])
        links.new(attribute1.outputs['Vector'], mapping1.inputs['Vector'])
        links.new(attribute2.outputs['Vector'], mapping2.inputs['Vector'])
        links.new(mapping.outputs['Vector'], output_node.inputs[0]) # UV0
        links.new(mapping1.outputs['Vector'], output_node.inputs[1]) # UV1
        links.new(mapping2.outputs['Vector'], output_node.inputs[2]) # UV2

        return group

    # remember that we processed a texture of that type
    mat_ctx.linked_maps.add(bl_tex_type)

        # Ensure the material uses nodes and clear any old nodes:
    mat.use_nodes = True

    # --- Reuse or create the custom node group ---
    # main shader
    if "MainShader" in mat.node_tree.nodes:
        main_node = mat.node_tree.nodes["MainShader"]
        print(f"'MainShader' already exists in material '{mat.name}'")
    else:
        main_node = mat.node_tree.nodes.new("ShaderNodeGroup")
        main_node.name = "MainShader"
        main_node.node_tree = main_shader  # your already available node group
        main_node.location = (-250, 0)
        main_node.node_tree.use_fake_user = True
        if main_node.node_tree.interface.items_tree:
            main_node.node_tree.interface.active_index = 0
            main_node.node_tree.interface.active = main_node.node_tree.interface.items_tree[0]
            main_node.node_tree.interface.active.default_value = (1.0, 1.0, 1.0, 1.0)
            # main_node.inputs[3].default_value = (0.735,0.735,0.735,1.0)
        print(f"Inserted 'MainShader' into material '{mat.name}'")
    
    # # ORM node group
    # if "ORMExtraShader" in mat.node_tree.nodes:
    #     orm_node = mat.node_tree.nodes["ORMExtraShader"]
    #     print(f"'ORMExtraShader' already exists in material '{mat.name}'")
    # else:
    #     orm_node = mat.node_tree.nodes.new("ShaderNodeGroup")
    #     orm_node.name = "ORMExtraShader"
    #     orm_node.node_tree = orm_shader
    #     orm_node.location = (-250, 350)
    #     orm_node.node_tree.use_fake_user = True
    #     # Default values
    #     orm_node.inputs[1].default_value = 8.0      # Multiply
    #     orm_node.inputs[2].default_value = -5.9      # Min
    #     orm_node.inputs[3].default_value = 0.3      # Max
    #     orm_node.inputs[5].default_value = 0.0      # Red Param Value
    #     orm_node.inputs[7].default_value = 0.0      # Green Param Value
    #     orm_node.inputs[9].default_value = 0.0      # Blue Param Value
    #     print(f"Inserted 'ORMExtraShader' into material '{mat.name}'")

    # OD Mask Shader node group
    if "OverlayDiffuseMask" in mat.node_tree.nodes:
        odm_node = mat.node_tree.nodes["OverlayDiffuseMask"]
        print(f"'OverlayDiffuseMask' already exists in material '{mat.name}'")
    else:
        odm_node = mat.node_tree.nodes.new("ShaderNodeGroup")
        odm_node.name = "OverlayDiffuseMask"
        odm_node.node_tree = odmask_shader
        odm_node.location = (-250, 600)
        odm_node.node_tree.use_fake_user = True
        # Default values
        odm_node.inputs[1].default_value = (0.9,0.7,0.6,1.0)      # Simple Tint
        odm_node.inputs[4].default_value = (0.735,0.735,0.735,1.0)      # Diffuse Red
        odm_node.inputs[7].default_value = (0.735,0.735,0.735,1.0)      # Diffuse Green
        odm_node.inputs[10].default_value = (0.735,0.735,0.735,1.0)     # Diffuse Blue
        print(f"Inserted 'OverlayDiffuseMask' into material '{mat.name}'")

    if "MappingGroup" in mat.node_tree.nodes:
        mapping_node = mat.node_tree.nodes["MappingGroup"]
        print(f"'Mapping' already exists in material '{mat.name}'")
    else:
        mapping_node = mat.node_tree.nodes.new("ShaderNodeGroup")
        mapping_node.name = "MappingGroup"
        mapping_node.node_tree = create_mapping_group()
        mapping_node.location = (-1500, -300)
        mapping_node.node_tree.use_fake_user = True
        print(f"Inserted 'MappingGroup' into material '{mat.name}'")

    # Link custom node groups
    mat.node_tree.links.new(main_node.outputs[0], bsdf_node.inputs[0])  # To Base Color BSDF

    main_node.inputs[0].default_value = (0.0,0.0,0.0,1.0)  # color
    main_node.inputs[1].default_value = 0.0  # AO
    main_node.inputs[2].default_value = 0.8  # Gamma Strength

    mapping_node.inputs[0].default_value[0] = 1  # X
    mapping_node.inputs[0].default_value[1] = 1  # Y
    mapping_node.inputs[0].default_value[2] = 1  # Z

    match bl_tex_type:
        case None:
            ao_mix_node.select = True
            bsdf_node.inputs[4].default_value = 0.2 # Alpha
            bsdf_node.inputs[2].default_value = 0.0 # Transmission
            bsdf_node.inputs[18].default_value = 1.0 # Transmission
        case TextureMapTypes.Diffuse:
            mat_ctx = _state_buffer[mat]
            mask_colors, vector_params = _get_vector_and_mask_colors(ast=mat_ctx.desc_ast)

            img_node.location = (-750, 150)
            img_node.image.colorspace_settings.name = 'sRGB'
            img_node.select = True
            mat.node_tree.nodes.active = img_node

            # Retrieve colors for each mask channel
            dtint = vector_params.get('diffuse colour tint', (1, 1, 1, 1))
            sss = vector_params.get('Subsurface Colour', (1, 1, 1, 1))

            tintr = mask_colors.get('tint 0 color', (dtint))
            tintg = mask_colors.get('tint 0.33 color', (sss)) # Temp Default color
            tintb = mask_colors.get('tint 0.66 color', (1, 1, 1, 1))
            tinta = mask_colors.get('tint 1.0 color', (1, 1, 1, 1))

            # Create the RGB Mask Tint group (or get it if already exists)
            tint_group = create_rgb_mask_tint_group()

            # Add node to material
            group_node = mat.node_tree.nodes.new('ShaderNodeGroup')
            group_node.node_tree = tint_group
            group_node.location = (-450, 300)

            group_node.inputs['Tint'].default_value = False

            # Connect mask texture to group input
            mat.node_tree.links.new(img_node.outputs['Color'], group_node.inputs['Image'])

            group_node.inputs['Color R'].default_value = tintr
            group_node.inputs['Color G'].default_value = tintg
            group_node.inputs['Color B'].default_value = tintb
            group_node.inputs['Color A'].default_value = tinta

            mat.node_tree.links.new(group_node.outputs['Color'], main_node.inputs[0])    # tinted output to main

            mat_ctx.msk_index += 1

        case TextureMapTypes.MRO:
            img_node.location = (-750, -150)
            img_node.image.colorspace_settings.name = 'Non-Color'
            invert_node = mat.node_tree.nodes.new('ShaderNodeInvert')
            invert_node.inputs['Fac'].default_value = 0.3
            invert_node.location = (-250, -150)

            rough_group = create_roughness_mask_group()
            group_node = mat.node_tree.nodes.new('ShaderNodeGroup')
            group_node.node_tree = rough_group
            group_node.location = (-450, -150)

            # Connect texture
            mat.node_tree.links.new(img_node.outputs['Color'], group_node.inputs['ORM Image'])

            # Optional scales
            group_node.inputs['Roughness Scale'].default_value = 1.0
            group_node.inputs['Metallic Scale'].default_value = 1.0
            group_node.inputs['AO Scale'].default_value = 1.0
            mat.node_tree.links.new(img_node.outputs['Color'], group_node.inputs['Roughness Scale'])

            # Connect to BSDF
            # Compare to ORM map
            mat.node_tree.links.new(group_node.outputs['AO'], bsdf_node.inputs['Metallic'])
            mat.node_tree.links.new(group_node.outputs['Roughness'], ao_mix_node.inputs['A'])
            mat.node_tree.links.new(group_node.outputs['Roughness'], invert_node.inputs['Color'])
            mat.node_tree.links.new(invert_node.outputs['Color'], bsdf_node.inputs['Roughness'])
            mat.node_tree.links.new(group_node.outputs['Metallic'], main_node.inputs['AO'])

        case TextureMapTypes.DRO:
            img_node.location = (-1200, -150)
            img_node.image.colorspace_settings.name = 'Non-Color'
            # invert_node = mat.node_tree.nodes.new('ShaderNodeInvert')
            # invert_node.inputs['Fac'].default_value = 0.3
            # invert_node.location = (-900, -150)

            rough_group = create_roughness_mask_group()
            group_node = mat.node_tree.nodes.new('ShaderNodeGroup')
            group_node.node_tree = rough_group
            group_node.location = (-900, -150)

            # Connect texture
            mat.node_tree.links.new(img_node.outputs['Color'], group_node.inputs['ORM Image'])
            mat.node_tree.links.new(mapping_node.outputs['UV0'], img_node.inputs['Vector'])

            # Optional scales
            group_node.inputs['Roughness Scale'].default_value = 1.0
            group_node.inputs['Metallic Scale'].default_value = 1.0
            group_node.inputs['AO Scale'].default_value = 1.0

            # Connect to BSDF
            # Compare to ORM map
            # mat.node_tree.links.new(group_node.outputs['AO'], bsdf_node.inputs['Metallic'])
            # mat.node_tree.links.new(group_node.outputs['Roughness'], ao_mix_node.inputs['A'])
            # mat.node_tree.links.new(group_node.outputs['Roughness'], invert_node.inputs['Color'])
            # mat.node_tree.links.new(invert_node.outputs['Color'], bsdf_node.inputs['Roughness'])
            # mat.node_tree.links.new(group_node.outputs['Metallic'], main_node.inputs['AO'])
 
        case TextureMapTypes.Normal:
            img_node.location = (-750, -450)
            img_node.image.colorspace_settings.name = 'Non-Color'

            normal_map_group = create_directx_to_opengl_normal_group()
            node = mat.node_tree.nodes.new("ShaderNodeGroup")
            node.node_tree = normal_map_group
            node.inputs[2].default_value = 2.0  # Normal Strength
            node.location = (-400, -450)
            mat.node_tree.links.new(img_node.outputs['Color'], node.inputs['DirectX Normal'])

            # Enable Flip Y
            node.inputs['Flip Y'].default_value = False

            # Connect to BSDF
            mat.node_tree.links.new(node.outputs['OpenGL Normal'], bsdf_node.inputs['Normal'])

            if TextureMapTypes.Normal == +1: # Check for other normal textures
                mat.node_tree.links.new(img_node.outputs['Color'], node.inputs['DirectX Normal'])
            
        case TextureMapTypes.EMISSION:
            img_node.location = (-200, -450)
            bsdf_node.inputs[28].default_value = 1.0 # Emission strength
            mat.node_tree.links.new(img_node.outputs['Color'], bsdf_node.inputs[27]) # Emission color
            
        case TextureMapTypes.ATX:
            atx_split_node = mat.node_tree.nodes.new('ShaderNodeSeparateColor')
            atx_split_node.location = (-400, -700)
            img_node.location = (-750, -800)
            img_node.image.colorspace_settings.name = 'Non-Color'
            mat.node_tree.links.new(img_node.outputs['Color'], atx_split_node.inputs['Color'])
            mat.node_tree.links.new(atx_split_node.outputs['Red'], bsdf_node.inputs['Alpha'])
            mat.node_tree.links.new(atx_split_node.outputs['Green'], bsdf_node.inputs[18]) # Transmission weight
            mat.node_tree.links.new(atx_split_node.outputs['Blue'], bsdf_node.inputs['Alpha']) # Roughness

        case TextureMapTypes.ATR:
            atr_split_node = mat.node_tree.nodes.new('ShaderNodeSeparateColor')
            atr_split_node.location = (-400, -700)
            mix_node = mat.node_tree.nodes.new('ShaderNodeMixRGB')
            mix_node.location = (-200, -700)
            img_node.location = (-750, -1000)
            img_node.image.colorspace_settings.name = 'Non-Color'
            mat.node_tree.links.new(img_node.outputs['Color'], atr_split_node.inputs['Color'])
            mat.node_tree.links.new(atr_split_node.outputs['Red'], bsdf_node.inputs['Alpha'])
            mat.node_tree.links.new(split_node.outputs['Green'], mix_node.inputs['Color1'])
            mat.node_tree.links.new(atr_split_node.outputs['Blue'], mix_node.inputs['Color2'])
            mat.node_tree.links.new(mix_node.outputs['Color'], bsdf_node.inputs['Roughness'])
            
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
        mat_ctx.bsdf_node.inputs[1].default_value = 0.0  # Metallic
        mat_ctx.bsdf_node.inputs[2].default_value = 0.1  # Roughness
        mat_ctx.bsdf_node.inputs[3].default_value = 1.5  # IOR
        mat_ctx.bsdf_node.inputs[15].default_value = 0.8   # Specular Anisotropic
        mat_ctx.bsdf_node.inputs[24].default_value = 0.1  # Sheen Weight
        mat_ctx.bsdf_node.inputs[20].default_value = 0.030  # Clearcoat roughness
        mat_ctx.bsdf_node.inputs[21].default_value = 1.5  # Clearcoat IOR

    del _state_buffer[mat]


# Non-interface functions below
def _short_name_to_tex_type(tex_short_name: str) -> t.Optional[TextureMapTypes]:
    """Convert short texture name to a recognized texture map type if possible.

    :return: TextureMapType or None.
    """
    return SUFFIX_MAP.get(tex_short_name.lower().split('_')[-1])


Color: t.TypeAlias = tuple[float, float, float, float]

def _get_vector_and_mask_colors(ast: lark.Tree) -> tuple[Dict[str, Color], Dict[str, Color]]:
    """Separates VectorParameterValues into indexed mask colors and named parameters.

    Returns:
        mask_colors: 'color 1', 'color 2', etc.
        named_params: 'Simple Tint', 'Water Color', etc.
    """
    mask_colors = {}
    named_params = {}

    for child in ast.children:
        if child.data != 'definition':
            continue
        def_name, array_qual, value = child.children

        if def_name != 'VectorParameterValues':
            continue
        if array_qual is None or value.data != 'structured_block':
            continue

        for tex_param_def in value.children:
            _, _, tex_param = tex_param_def.children
            param_info, param_val, _ = tex_param.children  # ParameterInfo, ParameterValue, ParameterName

            # Default vector (0,0,0,1)
            color = {'r': 0.0, 'g': 0.0, 'b': 0.0, 'a': 1.0}

            if param_val.children[2].data != 'structured_block':
                continue

            color_vec = param_val.children[2]

            # Extract color
            for channel_def in color_vec.children:
                channel_name, _, channel = channel_def.children
                cname = channel_name.lower()
                if cname in {'r', 'g', 'b', 'a'}:
                    color[cname] = float(channel.children[0].value)

            # Extract name from ParameterInfo
            name_tree = param_info.children[2].children[0].children[2]
            param_name = name_tree.children[0].value.strip().lower()

            # Split between mask colors and named ones
            if param_name.startswith("color "):
                mask_colors[param_name] = (color['r'], color['g'], color['b'], color['a'])
            else:
                named_params[param_name] = (color['r'], color['g'], color['b'], color['a'])

    return mask_colors, named_params