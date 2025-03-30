"""This module implements support for Atomic Heart game.
Known issues:
    - Blended materials are not properly supported. Currently the first texture is used.
"""

import enum
import typing as t
from typing import TypeAlias, Tuple, Dict
import dataclasses

import bpy
import lark


GAME_NAME = "Atomic Heart"
GAME_DESCRIPTION = "Atomic Heart (2023) by Mundfish, Focus Entertainment"

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

# --- Texture Map Types and Suffix Mapping ---
class TextureMapTypes(enum.Enum):
    """All texture map types supported by the material generator."""
    DIFFUSE = enum.auto()
    BASECOLOR = enum.auto()
    MicroDiffuse = enum.auto()
    Normal = enum.auto()
    MicroNormal = enum.auto()
    ORM = enum.auto()
    MRA = enum.auto()
    TOEH = enum.auto()
    NOISE = enum.auto()
    HEIGHT = enum.auto()
    ALPHA = enum.auto()
    MASK = enum.auto()
    MICROMASK = enum.auto()
    RGB_TINT = enum.auto()
    DIRT = enum.auto()


# Suffix mapping (lowercase and uppercase)
SUFFIX_MAP = {
    'a': TextureMapTypes.DIRT,
    'A': TextureMapTypes.DIRT,

    'd': TextureMapTypes.DIFFUSE,
    'D': TextureMapTypes.DIFFUSE,
    'diffuse': TextureMapTypes.DIFFUSE,
    'Diffuse': TextureMapTypes.DIFFUSE,

    'bc': TextureMapTypes.BASECOLOR,
    'BC': TextureMapTypes.BASECOLOR,
    'albedo': TextureMapTypes.BASECOLOR,
    'albedo': TextureMapTypes.BASECOLOR,
    'plastic': TextureMapTypes.BASECOLOR,
    'Plastic': TextureMapTypes.BASECOLOR,

    'n': TextureMapTypes.Normal,
    'N': TextureMapTypes.Normal,
    'normal': TextureMapTypes.Normal,
    'Normal': TextureMapTypes.Normal,

    'orm': TextureMapTypes.ORM,
    'orm1': TextureMapTypes.ORM,
    'ORM': TextureMapTypes.ORM,
    'ORM1': TextureMapTypes.ORM,
    'mra': TextureMapTypes.MRA,
    'mra1': TextureMapTypes.MRA,
    'MRA': TextureMapTypes.MRA,
    'MRA1': TextureMapTypes.MRA,

    'toe': TextureMapTypes.TOEH,
    'TOE': TextureMapTypes.TOEH,
    'toeh': TextureMapTypes.TOEH,
    'TOEH': TextureMapTypes.TOEH,
    'glass_dirt': TextureMapTypes.TOEH,
    'Glass_Dirt': TextureMapTypes.TOEH,
    '2': TextureMapTypes.TOEH, # Overlay_2

    'mask': TextureMapTypes.MASK,
    'Mask': TextureMapTypes.MASK,
    'opacity': TextureMapTypes.MASK,
    'Opacity': TextureMapTypes.MASK,

    'roughness': TextureMapTypes.NOISE,
    'Roughness': TextureMapTypes.NOISE,
    'r': TextureMapTypes.NOISE,
    'R': TextureMapTypes.NOISE,

    'm': TextureMapTypes.MICROMASK,
    'M': TextureMapTypes.MICROMASK,

    'BaseColor3': TextureMapTypes.DIFFUSE,
    'Normal3': TextureMapTypes.Normal,

    
}

@dataclasses.dataclass
class MaterialContext:
    bsdf_node: t.Optional[bpy.types.ShaderNodeBsdfPrincipled | bpy.types.ShaderNodeBsdfDiffuse]
    desc_ast: lark.Tree
    use_pbr: bool
    msk_index: int = dataclasses.field(default=0)
    diffuse_connected: bool = dataclasses.field(default=False)
    linked_maps: set[TextureMapTypes.DIFFUSE] = dataclasses.field(default_factory=set)

_state_buffer: dict[bpy.types.Material, MaterialContext] = {}

def process_material(mat: bpy.types.Material, desc_ast: lark.Tree, use_pbr: bool):  # pylint: disable=unused-argument
    _state_buffer[mat] = MaterialContext(bsdf_node=None, desc_ast=desc_ast, use_pbr=use_pbr)

def do_process_texture(tex_type: str, tex_short_name: str) -> bool:  # pylint: disable=unused-argument
    return bool(_short_name_to_tex_type(tex_short_name))

def is_diffuse_tex_type(tex_type: str, tex_short_name: str) -> bool:  # pylint: disable=unused-argument
    return _short_name_to_tex_type(tex_short_name) == {TextureMapTypes.DIFFUSE, TextureMapTypes.MASK}

def handle_material_texture_pbr(mat: bpy.types.Material,
                                tex_type: str,  # unused here
                                tex_short_name: str,
                                img_node: bpy.types.ShaderNodeTexImage,
                                main_shader: bpy.types.ShaderNodeTree,
                                orm_shader: bpy.types.ShaderNodeTree,
                                odmask_shader: bpy.types.ShaderNodeTree,
                                ao_mix_node: bpy.types.ShaderNodeAmbientOcclusion,
                                bsdf_node: bpy.types.ShaderNodeBsdfPrincipled,
                                out_node: bpy.types.ShaderNodeOutputMaterial):
    # This is not validated.
    mat_ctx = _state_buffer[mat]
    mat_ctx.bsdf_node = bsdf_node

    main_group = main_shader
    orm_group = orm_shader
    odm_group = odmask_shader

    bsdf_node.location = (100, 20)
    out_node.location = (600, 0)
    ao_mix_node.location = (-100, -200)
    ao_mix_node.inputs['B'].default_value = (0.0,0.0,0.0,1.0) # Default Black

    # Determine the texture type to process:
    bl_tex_type = _short_name_to_tex_type(tex_short_name)
    # Avoid processing the same texture type twice
    if bl_tex_type in mat_ctx.linked_maps:
        return
    
    def create_mix_node(mat, loc_x, loc_y, color, default_value, blend_type='MIX'):
            mix_node = mat.node_tree.nodes.new('ShaderNodeMixRGB')
            mix_node.location = (loc_x, loc_y)

            mix_node.data_type = 'RGBA'
            mix_node.blend_type = blend_type

            # Extract only the RGB values, discarding the alpha
            rgb_color = color[:3] if color is not None else default_value[:3]

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

    # Mark texture as processed
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
    
    # ORM node group
    if "ORMExtraShader" in mat.node_tree.nodes:
        orm_node = mat.node_tree.nodes["ORMExtraShader"]
        print(f"'ORMExtraShader' already exists in material '{mat.name}'")
    else:
        orm_node = mat.node_tree.nodes.new("ShaderNodeGroup")
        orm_node.name = "ORMExtraShader"
        orm_node.node_tree = orm_shader
        orm_node.location = (-250, 350)
        orm_node.node_tree.use_fake_user = True
        # Default values
        orm_node.inputs[1].default_value = 8.0      # Multiply
        orm_node.inputs[2].default_value = -5.9      # Min
        orm_node.inputs[3].default_value = 0.3      # Max
        orm_node.inputs[5].default_value = 0.0      # Red Param Value
        orm_node.inputs[7].default_value = 0.0      # Green Param Value
        orm_node.inputs[9].default_value = 0.0      # Blue Param Value
        print(f"Inserted 'ORMExtraShader' into material '{mat.name}'")

    # OD Mask Shader node group
    if "OverlayDiffuseMask" in mat.node_tree.nodes:
        odm_node = mat.node_tree.nodes["OverlayDiffuseMask"]
        print(f"'OverlayDiffuseMask' already exists in material '{mat.name}'")
    else:
        odm_node = mat.node_tree.nodes.new("ShaderNodeGroup")
        odm_node.name = "OverlayDiffuseMask"
        odm_node.node_tree = odmask_shader
        odm_node.location = (-480, 200)
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
    mat.node_tree.links.new(ao_mix_node.outputs['Result'], bsdf_node.inputs[2])   # Mix to Roughness
    mat.node_tree.links.new(orm_node.outputs[0], ao_mix_node.inputs[0])   # ORM Shader to Mix
    mat.node_tree.links.new(odm_node.outputs[0], main_node.inputs[0])   # To Diffuse Texture mainshader
    mat.node_tree.links.new(main_node.outputs[0], bsdf_node.inputs[0])  # To Base Color BSDF

    main_node.inputs[0].default_value = (0.0,0.0,0.0,1.0)  # color
    main_node.inputs[1].default_value = (0.0,0.0,0.0,1.0)  # AO
    main_node.inputs[2].default_value = 0.8  # Gamma Strength

    mapping_node.inputs[0].default_value[0] = 1  # X
    mapping_node.inputs[0].default_value[1] = 1  # Y
    mapping_node.inputs[0].default_value[2] = 1  # Z

    # Process the current texture:
    match bl_tex_type:
        case TextureMapTypes.DIFFUSE:
            mat_ctx = _state_buffer[mat]
            mask_colors, vector_params = _get_vector_and_mask_colors(ast=mat_ctx.desc_ast)

            # Retrieve colors for each mask channel
            simpletint = vector_params.get('simple tint', (1, 1, 1, 1))
            watercolor = vector_params.get('water color', (0, 0, 0, 1))
            
            odcolor_red = vector_params.get('overlay diffuse color (red channel)', (1, 1, 1, 1))
            odcolor_green = vector_params.get('overlay diffuse color (green channel)', (1, 1, 1, 1))
            odcolor_blue = vector_params.get('overlay diffuse color (blue channel)', (1, 1, 1, 1))

            tint3 = mask_colors.get('tint 0 color', (simpletint)) or mask_colors.get('tint 0.0 color (Main Layer)', (simpletint))
            tint2 = mask_colors.get('tint 0.33 color', (odcolor_red)) or mask_colors.get('tint 0.33 color (Main Layer)', (odcolor_red))
            tint1 = mask_colors.get('tint 0.66 color', (odcolor_green)) or mask_colors.get('tint 0.66 color (Main Layer)', (odcolor_green))
            tint0 = mask_colors.get('tint 1.0 color', (odcolor_blue)) or mask_colors.get('tint 1.0 color (Main Layer)', (odcolor_blue))

            # Create the RGB Mask Tint group (or get it if already exists)
            tint_group = create_rgb_mask_tint_group()

            # Add node to material
            group_node = mat.node_tree.nodes.new('ShaderNodeGroup')
            group_node.node_tree = tint_group
            group_node.location = (-750, 400)

            group_node.inputs['Tint'].default_value = True

            # Connect mask texture to group input
            mat.node_tree.links.new(img_node.outputs['Color'], group_node.inputs['Image'])

            group_node.inputs['Color R'].default_value = tint3
            group_node.inputs['Color G'].default_value = tint2
            group_node.inputs['Color B'].default_value = tint1
            group_node.inputs['Color A'].default_value = tint0

            # Connect final tinted color to ODM node
            if not mat_ctx.diffuse_connected:
                mat.node_tree.links.new(img_node.outputs['Color'], odm_node.inputs[0])      # color
                mat.node_tree.links.new(group_node.outputs['Color'], odm_node.inputs[1])    # tinted output
                odm_node.inputs[1].default_value = simpletint                               # Simple tint
                odm_node.inputs[4].default_value = odcolor_red                              # Red overlay
                odm_node.inputs[7].default_value = odcolor_green                            # Green overlay
                odm_node.inputs[10].default_value = odcolor_blue                            # Blue overlay
                mat.node_tree.links.new(group_node.outputs['R'], odm_node.inputs[3])
                mat.node_tree.links.new(group_node.outputs['G'], odm_node.inputs[6])
                mat.node_tree.links.new(group_node.outputs['B'], odm_node.inputs[9])
                # mat.node_tree.links.new(group_node.outputs['Simple Tint'], odm_node.inputs[1]) 
                # Optional alpha
                # mat.node_tree.links.new(group_node.outputs['A'], bsdf_node.inputs['Alpha'])

                img_node.select = True
                mat.node_tree.nodes.active = img_node
                img_node.location = (-1050, 150)

            mat_ctx.msk_index += 1
        # case TextureMapTypes.DIRT:
        #     mat_ctx = _state_buffer[mat]
        #     mask_colors, vector_params = _get_vector_and_mask_colors(ast=mat_ctx.desc_ast)

        #     img_node.image.colorspace_settings.name = 'Non-Color'

        #     # Retrieve colors for each mask channel
        #     tint3 = mask_colors.get('tint 0 color}', (0, 0, 0, 1)) or mask_colors.get('tint 0.0 color (Main Layer)}', (0, 0, 0, 1))
        #     tint2 = mask_colors.get('tint 0.33 color}', (0, 0, 0, 1)) or mask_colors.get('tint 0.33 color (Main Layer)}', (0, 0, 0, 1))
        #     tint1 = mask_colors.get('tint 0.66 color}', (0, 0, 0, 1)) or mask_colors.get('tint 0.66 color (Main Layer)}', (0, 0, 0, 1))
        #     tint0 = mask_colors.get('tint 1.0 color}', (0, 0, 0, 1)) or mask_colors.get('tint 1.0 color (Main Layer)}', (0, 0, 0, 1))

        #     simpletint = vector_params.get('simple tint', (0, 0, 0, 1))
        #     watercolor = vector_params.get('water color', (0, 0, 0, 1))
            
        #     odcolor_red = vector_params.get('overlay diffuse color (red channel)', (0, 0, 0, 1))
        #     odcolor_green = vector_params.get('overlay diffuse color (green channel)', (0, 0, 0, 1))
        #     odcolor_blue = vector_params.get('overlay diffuse color (blue channel)', (0, 0, 0, 1))

        #     # Create the RGB Mask Tint group (or get it if already exists)
        #     tint_group = create_rgb_mask_tint_group()

        #     # Add node to material
        #     group_node = mat.node_tree.nodes.new('ShaderNodeGroup')
        #     group_node.node_tree = tint_group
        #     group_node.location = (-750, 300)

        #     # Connect mask texture to group input
        #     mat.node_tree.links.new(img_node.outputs['Color'], group_node.inputs['Image'])

        #     group_node.inputs['Color R'].default_value = tint0
        #     group_node.inputs['Color G'].default_value = tint1
        #     group_node.inputs['Color B'].default_value = tint2
        #     group_node.inputs['Color A'].default_value = tint3

        #     # Connect final tinted color to ODM node
        #     if not mat_ctx.diffuse_connected:
        #         mat.node_tree.links.new(img_node.outputs['Color'], odm_node.inputs[0])      # color
        #         mat.node_tree.links.new(group_node.outputs['Color'], odm_node.inputs[1])    # tinted output
        #         odm_node.inputs[1].default_value = simpletint                               # Simple tint
        #         odm_node.inputs[2].default_value = odcolor_red                              # Red overlay
        #         odm_node.inputs[5].default_value = odcolor_green                            # Green overlay
        #         odm_node.inputs[8].default_value = odcolor_blue                             # Blue overlay
        #         mat.node_tree.links.new(group_node.outputs['R'], odm_node.inputs[4])
        #         mat.node_tree.links.new(group_node.outputs['G'], odm_node.inputs[7])
        #         mat.node_tree.links.new(group_node.outputs['B'], odm_node.inputs[10])
        #         # mat.node_tree.links.new(group_node.outputs['Simple Tint'], odm_node.inputs[1]) 
        #         # Optional alpha
        #         # mat.node_tree.links.new(group_node.outputs['A'], bsdf_node.inputs['Alpha'])

        #         img_node.select = True
        #         mat.node_tree.nodes.active = img_node
        #         img_node.location = (-1050, 250)

        #     mat_ctx.msk_index += 1
        case TextureMapTypes.BASECOLOR:
            mat_ctx = _state_buffer[mat]
            mask_colors, vector_params = _get_vector_and_mask_colors(ast=mat_ctx.desc_ast)

            img_node.location = (-750, 150)
            img_node.image.colorspace_settings.name = 'sRGB'

            # Retrieve colors for each mask channel
            tintfl = vector_params.get('tint (fl)', (1, 1, 1, 1))
            simpletint = vector_params.get('simple tint', (tintfl))
            watercolor = vector_params.get('water color', (simpletint))
            
            odcolor_red = vector_params.get('overlay diffuse color (red channel)', (1, 1, 1, 1))
            odcolor_green = vector_params.get('overlay diffuse color (green channel)', (1, 1, 1, 1))
            odcolor_blue = vector_params.get('overlay diffuse color (blue channel)', (1, 1, 1, 1))

            tint3 = mask_colors.get('tint 0 color', (simpletint)) or mask_colors.get('tint 0.0 color (Main Layer)', (simpletint))
            tint2 = mask_colors.get('tint 0.33 color', (odcolor_red)) or mask_colors.get('tint 0.33 color (Main Layer)', (odcolor_red))
            tint1 = mask_colors.get('tint 0.66 color', (odcolor_green)) or mask_colors.get('tint 0.66 color (Main Layer)', (odcolor_green))
            tint0 = mask_colors.get('tint 1.0 color', (odcolor_blue)) or mask_colors.get('tint 1.0 color (Main Layer)', (odcolor_blue))

            # Create the RGB Mask Tint group (or get it if already exists)
            tint_group = create_rgb_mask_tint_group()

            # Add node to material
            group_node = mat.node_tree.nodes.new('ShaderNodeGroup')
            group_node.node_tree = tint_group
            group_node.location = (-750, 400)

            # Connect mask texture to group input
            mat.node_tree.links.new(img_node.outputs['Color'], group_node.inputs['Image'])

            group_node.inputs['Color R'].default_value = tint3
            group_node.inputs['Color G'].default_value = tint2
            group_node.inputs['Color B'].default_value = tint1
            group_node.inputs['Color A'].default_value = tint0

            mat.node_tree.links.new(mapping_node.outputs['UV1'], img_node.inputs[0])

            # Connect final tinted color to ODM node
            if not mat_ctx.diffuse_connected:
                mat.node_tree.links.new(img_node.outputs['Color'], odm_node.inputs[0])      # color
                mat.node_tree.links.new(group_node.outputs['Color'], odm_node.inputs[1])    # tinted output
                odm_node.inputs[1].default_value = simpletint                               # Simple tint
                odm_node.inputs[4].default_value = odcolor_red                              # Red overlay
                odm_node.inputs[7].default_value = odcolor_green                            # Green overlay
                odm_node.inputs[10].default_value = odcolor_blue                            # Blue overlay
                mat.node_tree.links.new(group_node.outputs['R'], odm_node.inputs[3])
                mat.node_tree.links.new(group_node.outputs['G'], odm_node.inputs[6])
                mat.node_tree.links.new(group_node.outputs['B'], odm_node.inputs[9])
        case TextureMapTypes.ORM:
            img_node.location = (-750, -150)
            img_node.image.colorspace_settings.name = 'Non-Color'

            rough_group = create_roughness_mask_group()

            group_node = mat.node_tree.nodes.new('ShaderNodeGroup')
            group_node.node_tree = rough_group
            group_node.location = (-450, -150)

            # Connect texture
            mat.node_tree.links.new(img_node.outputs['Color'], group_node.inputs['ORM Image'])
            mat.node_tree.links.new(img_node.outputs['Color'], group_node.inputs[2])
            mat.node_tree.links.new(img_node.outputs['Color'], orm_node.inputs[0])

            # Optional scales
            group_node.inputs['Roughness Scale'].default_value = 1.0
            group_node.inputs['Metallic Scale'].default_value = 1.0
            group_node.inputs['AO Scale'].default_value = 1.0

            # Connect to BSDF
            mat.node_tree.links.new(group_node.outputs['AO'], main_node.inputs['AO'])
            mat.node_tree.links.new(group_node.outputs['Metallic'], bsdf_node.inputs['Metallic'])
            mat.node_tree.links.new(group_node.outputs['Roughness'], ao_mix_node.inputs['A'])   # Roughness Mask to Mix
        case TextureMapTypes.MRA:
            img_node.location = (-750, -150)
            img_node.image.colorspace_settings.name = 'Non-Color'

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

            # Connect to BSDF
            # Compare to ORM map
            mat.node_tree.links.new(group_node.outputs['AO'], bsdf_node.inputs['Metallic'])
            mat.node_tree.links.new(group_node.outputs['Roughness'], bsdf_node.inputs['Roughness'])
            mat.node_tree.links.new(group_node.outputs['Metallic'], main_node.inputs['AO'])
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
        case TextureMapTypes.MASK:
            img_node.location = (-750, -750)
            img_node.image.colorspace_settings.name = 'Non-Color'

            # Create the RGB Mask Tint group
            tint_group = create_rgb_mask_tint_group()

            # Add node to material
            group_node = mat.node_tree.nodes.new('ShaderNodeGroup')
            group_node.node_tree = tint_group
            group_node.location = (-500, -750)

            # Connect mask texture to group input
            mat.node_tree.links.new(img_node.outputs['Color'], group_node.inputs['Image'])

            # mat.node_tree.links.new(img_node.outputs['Color'], main_node.inputs[6])
            # mat.node_tree.links.new(mapping.outputs['Vector'], img_node.inputs[0])
        case TextureMapTypes.TOEH:
            img_node.location = (-750, -750)
            img_node.image.colorspace_settings.name = 'Non-Color'
            toeh_split_node = mat.node_tree.nodes.new(SHADER_NODE_SEPARATE_COLOR)
            toeh_split_node.location = (-450, -750)
            displacement_node = mat.node_tree.nodes.new('ShaderNodeDisplacement')
            displacement_node.inputs[1].default_value = 0.0 # Midlevel
            displacement_node.inputs[2].default_value = 0.2 # Scale
            displacement_node.location = (-250, -750)
            mat.node_tree.links.new(img_node.outputs['Color'], toeh_split_node.inputs['Color'])
            mat.node_tree.links.new(toeh_split_node.outputs['Red'], ao_mix_node.inputs['B'])   # Roughness Mask to Mix
            # if tex_short_name == 'toeh' or tex_short_name == 'toe': # so overlay_2 dont apply opacity
            mat.node_tree.links.new(toeh_split_node.outputs['Green'], bsdf_node.inputs['Alpha'])
            mat.node_tree.links.new(toeh_split_node.outputs['Blue'], displacement_node.inputs['Height']) # Displacement
            mat.node_tree.links.new(displacement_node.outputs['Displacement'], out_node.inputs['Displacement'])
        case TextureMapTypes.DIRT:
            img_node.location = (-1350, 200)
            img_node.image.colorspace_settings.name = 'Non-Color'
            dirt_split_node = mat.node_tree.nodes.new(SHADER_NODE_SEPARATE_COLOR)
            dirt_split_node.location = (-1250, 350)
            mat.node_tree.links.new(img_node.outputs['Color'], dirt_split_node.inputs['Color'])
            # mat.node_tree.links.new(img_node.outputs['Color'], odm_node.inputs[0])
            mat.node_tree.links.new(dirt_split_node.outputs['Red'], orm_node.inputs[4])
            mat.node_tree.links.new(dirt_split_node.outputs['Green'], orm_node.inputs[6])
            mat.node_tree.links.new(dirt_split_node.outputs['Blue'], orm_node.inputs[8])
            mat.node_tree.links.new(mapping_node.outputs['UV0'], img_node.inputs[0])
        case TextureMapTypes.NOISE:
            img_node.location = (-1050, 0)
            img_node.image.colorspace_settings.name = 'Non-Color'
            noise_split_node = mat.node_tree.nodes.new(SHADER_NODE_SEPARATE_COLOR)
            noise_split_node.location = (-1050, 200)
            mat.node_tree.links.new(img_node.outputs['Color'], noise_split_node.inputs['Color'])
            mat.node_tree.links.new(noise_split_node.outputs['Red'], orm_node.inputs[4])
            mat.node_tree.links.new(noise_split_node.outputs['Green'], orm_node.inputs[6])
            mat.node_tree.links.new(noise_split_node.outputs['Green'], ao_mix_node.inputs['A'])   # Roughness Mask to Mix
            mat.node_tree.links.new(noise_split_node.outputs['Blue'], orm_node.inputs[8])
            mat.node_tree.links.new(mapping_node.outputs['UV1'], img_node.inputs[0])
        case TextureMapTypes.MICROMASK:
            img_node.location = (-1050, -350)
            img_node.image.colorspace_settings.name = 'Non-Color'
            mat.node_tree.links.new(img_node.outputs['Color'], main_node.inputs[1]) # to AO, Testing
            mat.node_tree.links.new(mapping_node.outputs['UV1'], img_node.inputs[0])

        # case TextureMapTypes.RGB_TINT:
        #     mat_ctx.msk_index += 1

def handle_material_texture_simple(mat: bpy.types.Material,
                                   tex_type: str,  # pylint: disable=unused-argument
                                   tex_short_name: str,  # pylint: disable=unused-argument
                                   img_node: bpy.types.ShaderNodeTexImage,
                                   bsdf_node: bpy.types.ShaderNodeBsdfDiffuse):
    _state_buffer[mat].bsdf_node = bsdf_node

    # Do NOT clear the node tree here. Instead, just link the texture.
    mat.node_tree.links.new(img_node.outputs['Color'], bsdf_node.inputs['Color'])
    img_node.select = True
    mat.node_tree.nodes.active = img_node
    print("Linked image color to BSDF color")

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

    # del _state_buffer[mat]

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

def _clamp_color(c: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        return tuple(min(1.0, max(0.0, ch)) for ch in c)

def get_color(mask_colors, key: str, fallback: Color) -> Color:
    return _clamp_color(mask_colors.get(key, mask_colors.get(key.replace("color", "colour"), fallback)))

