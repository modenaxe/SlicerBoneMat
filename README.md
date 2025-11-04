# SlicerBoneMat
extension for 3DSlicer implementing material mapping from CT

# Resources to look at

# 3DSlicer (essential!)
- website: https://www.slicer.org
- forum: https://discourse.slicer.org
- video about Slicer from Kitware: https://www.kitware.com/how-to-leverage-3d-slicer-for-medical-imaging-research-product-development/
- [slicer script editor](https://github.com/SlicerMorph/SlicerScriptEditor/tree/main)

## Basic Training (learn what Slicer can do)
- [Training website](https://training.slicer.org/)
- [PerkLab Youtube channel](https://www.youtube.com/@PerkLabResearch)

## Advance training (learn about images and how to program Slicer)
- PerkLab bootcamp: https://github.com/PerkLab/PerkLabBootcamp
- Programming tutorial for 3D Slicer: https://github.com/Slicer/SlicerProgrammingTutorial

## Integration: Slicer extensions, Python packages and tips from the developers

### SlicerSegmenter
- [SlicerSegmenMesher](https://github.com/lassoan/SlicerSegmentMesher): can convert segmentations to volumetric meshes. __NOTE__: when you import a 3D bone geometry you can choose if you want to import it as a model (surface geometry) or segmentation!

### PyBoneMat
This Python package maps material properties from a given CT scan to a given volumetric mesh.
- original version (Python 2.7) [repository](https://github.com/elisepegg/py_bonemat_abaqus)
- updated version (Python 3.x) [repository](https://github.com/modenaxe/py_bonemat_abaqus)

### Slicer forum tips on integration
- [tips on how to implement BoneMat in Slicer](https://discourse.slicer.org/t/best-way-to-map-material-properties-from-ct-scan-to-element/42181/6)
- [more tips](https://discourse.slicer.org/t/material-mapping-for-bone-from-ct-scan/32837)
- [more tips](https://discourse.slicer.org/t/quantitative-analysis-bone-mineral-density/1219)
- [how to show the modulus values in the GUI](https://discourse.slicer.org/t/how-to-display-voxel-intensities/12900)

## BoneMat (to use for verification)
- website: [LINK](https://ior-bic.github.io/software/bonemat/index.html)
- user manual and test data (for validation): [LINK](https://ior-bic.github.io/software/bonemat/downloads.html)

## MITK-GEM (to use for verification)
This software is designed for a material mapping workflow
- MITK-GEM [website](https://araex.github.io/mitk-gem-site)
- Github repository: [LINK](https://github.com/araex/mitk-gem)
- files to write outputs for Ansys and Abaqus [LINK](https://github.com/araex/mitk-gem/tree/master/Scripts)

## FEBio Studio (one of the output formats)
This is a popular open-source finite element platform that runs the FEBio solver. 
The extension must be able to produce input files for FEBio:
- binaries for FEBio Studio are available from [here](https://febio.org/)
- source code is available [here](https://github.com/febiosoftware/FEBioStudio)
