cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(SlicerBoneMat)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/modenaxe/SlicerBoneMat.git")
set(EXTENSION_CATEGORY "Surface Models")
set(EXTENSION_CONTRIBUTORS "Maxwell Hogan (University of New South Wales), Luca Modenese (University of New South Wales)")
set(EXTENSION_DESCRIPTION "A 3D Slicer implementation of the BoneMat workflow for generating finite element meshes from CT data with automated material property mapping based on voxel intensities.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/modenaxe/SlicerBoneMat/main/SlicerBoneMat.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/modenaxe/SlicerBoneMat/main/Screenshot01.png")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(BoneMat)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
