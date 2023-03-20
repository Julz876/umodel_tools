# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import os
import sys
import traceback

import bpy

import faulthandler

faulthandler.enable()

# include custom lib vendoring dir
parent_dir = os.path.abspath(os.path.dirname(__file__))
vendor_dir = os.path.join(parent_dir, 'third_party')

sys.path.append(vendor_dir)

from . import auto_load  # nopep8

bl_info = {
    "name": "UModel Tools",
    "author": "Skarn",
    "version": (1, 0),
    "blender": (3, 40, 0),
    "description": "Reverse engineer Unreal Engine scenes in Blender.",
    "category": "Import-Export"
}

PACKAGE_NAME = __package__


def register():
    auto_load.init()

    try:
        auto_load.register()
    except Exception:
        traceback.print_exc()


def unregister():
    try:
        auto_load.unregister()
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    register()
