
import typing as t
import bpy

from . import PACKAGE_NAME
from . import game_profiles

from bpy.props import BoolProperty, StringProperty, EnumProperty, CollectionProperty, IntProperty


def get_addon_preferences() -> 'UMODELTOOLS_AP_addon_preferences':
    """Returns this addon's preferences.

    :return: Addon preferences.
    """
    return bpy.context.preferences.addons[PACKAGE_NAME].preferences


class UMODELTOOLS_PG_game_profile(bpy.types.PropertyGroup):
    """Game profile settings
    """

    name: StringProperty(
        name="Name",
        description="Name of the profile"
    )

    game: EnumProperty(
        name="Game",
        description="Game of this profile",
        items=game_profiles.SUPPORTED_GAMES,
        default=0
    )

    umodel_export_dir: StringProperty(
        name="UModel Export Directory",
        description="Path to the UModel export directory with game assets",
        subtype='DIR_PATH'
    )

    asset_dir: StringProperty(
        name="Asset Directory",
        description="Path to the directory where the assets for current project are stored",
        subtype='DIR_PATH'
    )


class UMODELTOOLS_UL_game_profiles(bpy.types.UIList):
    """UIlist for displaying game profiles."""

    def draw_item(self,
                  _context: bpy.types.Context,
                  layout: bpy.types.UILayout,
                  _prefs: 'UMODELTOOLS_AP_addon_preferences',
                  game_profile: UMODELTOOLS_PG_game_profile,
                  icon: str,
                  _active_prefs: 'UMODELTOOLS_AP_addon_preferences',
                  _active_propname: str,
                  _index: int,
                  _flt_flag: int):
        layout.prop(game_profile, "name", text="", emboss=False, icon_value=icon)


class UMODELTOOLS_OT_actions(bpy.types.Operator):
    """Move items up and down, add and remove"""

    bl_idname = "umodel_tools.list_action"
    bl_label = "List Actions"
    bl_description = "Move items up and down, add and remove"
    bl_options = {'REGISTER', 'INTERNAL', 'UNDO'}

    action: EnumProperty(
        items=(
            ('UP', "Up", ""),
            ('DOWN', "Down", ""),
            ('REMOVE', "Remove", ""),
            ('ADD', "Add", "")
        )
    )

    def invoke(self, _context: bpy.types.Context, _event: bpy.types.Event) -> set[str]:
        addon_prefs = get_addon_preferences()
        idx = addon_prefs.active_profile_index

        try:
            addon_prefs.profiles[idx]
        except IndexError:
            pass
        else:
            if self.action == 'DOWN' and idx < len(addon_prefs.profiles) - 1:
                addon_prefs.profiles.move(idx, idx + 1)
                addon_prefs.active_profile_index += 1

            elif self.action == 'UP' and idx >= 1:
                addon_prefs.profiles.move(idx, idx - 1)
                addon_prefs.active_profile_index -= 1

            elif self.action == 'REMOVE':
                addon_prefs.profiles.remove(idx)
                if addon_prefs.active_profile_index != 0:
                    addon_prefs.active_profile_index -= 1

        if self.action == 'ADD':
            profile = addon_prefs.profiles.add()
            profile.name = "New Profile"
            addon_prefs.active_profile_index = len(addon_prefs.profiles) - 1

        return {"FINISHED"}


class UMODELTOOLS_AP_addon_preferences(bpy.types.AddonPreferences):
    """Implements preferences storage for the addon.
    """

    bl_idname = PACKAGE_NAME

    profiles: CollectionProperty(
        name="Profiles",
        description="Saved game profiles",
        type=UMODELTOOLS_PG_game_profile
    )

    active_profile_index: IntProperty(
        default=0
    )

    display_cur_profile: BoolProperty(
        name="Display current profile",
        description="Display current profile on top of Blender's window",
        default=True
    )

    verbose: BoolProperty(
        name="Verbose import",
        description="Print detailed logging information on import",
        default=False
    )

    debug: BoolProperty(
        name="Debug",
        description="Enables debugging output, intended for developers only",
        default=False
    )

    def get_active_profile(self) -> t.Optional[UMODELTOOLS_PG_game_profile]:
        try:
            return self.profiles[self.active_profile_index]
        except IndexError:
            return None

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        layout.prop(self, "display_cur_profile")
        layout.prop(self, "verbose")

        if context.preferences.view.show_developer_ui:
            layout.prop(self, "debug")

        layout.label(text="Game profiles:")
        row = layout.row()
        row.template_list("UMODELTOOLS_UL_game_profiles", "", self, "profiles", self, "active_profile_index")

        col = row.column(align=True)
        col.operator(UMODELTOOLS_OT_actions.bl_idname, icon='ADD', text="").action = 'ADD'
        col.operator(UMODELTOOLS_OT_actions.bl_idname, icon='REMOVE', text="").action = 'REMOVE'

        col.separator()
        col.operator(UMODELTOOLS_OT_actions.bl_idname, icon='TRIA_UP', text="").action = 'UP'
        col.operator(UMODELTOOLS_OT_actions.bl_idname, icon='TRIA_DOWN', text="").action = 'DOWN'

        try:
            game_profile = self.profiles[self.active_profile_index]
        except IndexError:
            pass
        else:
            layout.separator()
            layout.label(text="Profile settings:")

            layout.prop(game_profile, "game")
            layout.prop(game_profile, "umodel_export_dir")
            layout.prop(game_profile, "asset_dir")


class UMODELTOOLS_PT_scene_panel(bpy.types.Panel):
    """Scene properties panel that references add-on preferences.
    """
    bl_label = "Umodel Tools Settings"
    bl_idname = "UMODELTOOLS_PT_scene_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'scene'

    def draw(self, context):
        # Retrieve the add-on preferences using the package name as the identifier.
        addon_prefs = context.preferences.addons[PACKAGE_NAME].preferences
        layout = self.layout

        # Mimic header and display options
        layout.label(text="Display Options", icon='SCENE_DATA')
        layout.prop(addon_prefs, "display_cur_profile")
        layout.prop(addon_prefs, "verbose")
        if context.preferences.view.show_developer_ui:
            layout.prop(addon_prefs, "debug")

        layout.separator()

        # Mimic the game profiles list layout
        layout.label(text="Game Profiles", icon='FILE_FOLDER')
        row = layout.row()
        row.template_list("UMODELTOOLS_UL_game_profiles", "",
                          addon_prefs, "profiles",
                          addon_prefs, "active_profile_index")

        col = row.column(align=True)
        col.operator(UMODELTOOLS_OT_actions.bl_idname, icon='ADD', text="").action = 'ADD'
        col.operator(UMODELTOOLS_OT_actions.bl_idname, icon='REMOVE', text="").action = 'REMOVE'
        col.separator()
        col.operator(UMODELTOOLS_OT_actions.bl_idname, icon='TRIA_UP', text="").action = 'UP'
        col.operator(UMODELTOOLS_OT_actions.bl_idname, icon='TRIA_DOWN', text="").action = 'DOWN'

        # Display additional settings for the active profile
        try:
            game_profile = addon_prefs.profiles[addon_prefs.active_profile_index]
        except IndexError:
            pass
        else:
            layout.separator()
            layout.label(text="Profile Settings", icon='PREFERENCES')
            layout.prop(game_profile, "game")
            layout.prop(game_profile, "umodel_export_dir")
            layout.prop(game_profile, "asset_dir")
            layout.separator()

