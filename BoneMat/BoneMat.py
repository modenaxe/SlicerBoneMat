import os
import sys
import re
from typing import Optional
from __main__ import qt

import vtk
from vtk.util import numpy_support
import numpy as np
import json
import tempfile
import importlib
from pathlib import Path

import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    WithinRange,
)
from slicer import (
    vtkMRMLScalarVolumeNode,
    vtkMRMLModelNode
)

def ensureLocalPackage(importName, installPath=None):
    try:
        return importlib.import_module(importName)
    except ModuleNotFoundError:
        if installPath:
            slicer.util.pip_install(installPath)
        else:
            slicer.util.pip_install(f"\"{importName}\"")
        importlib.invalidate_caches()
        return importlib.import_module(importName)
    
ensureLocalPackage('meshio')

import meshio
    
def configurePyBonematImports(module_file):
    project_root = os.path.abspath(os.path.join(os.path.dirname(module_file), ".."))
    bonemat_repo_root = os.path.join(project_root, "py_bonemat_abaqus")

    if bonemat_repo_root in sys.path:
        sys.path.remove(bonemat_repo_root)
    sys.path.insert(0, bonemat_repo_root)

    if project_root in sys.path:
        sys.path.remove(project_root)
        sys.path.append(project_root)

    if "py_bonemat_abaqus" in sys.modules:
        del sys.modules["py_bonemat_abaqus"]

    importlib.invalidate_caches()
    

#
# BoneMat
#


class BoneMat(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("SlicerBoneMat")  # TODO: make this more human readable by adding spaces
        # TODO: set categories (folders where the module shows up in the module selector)
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Examples")]
        self.parent.dependencies = []  # TODO: add here list of module names that this module requires
        self.parent.contributors = ["John Doe (AnyWare Corp.)"]  # TODO: replace with "Firstname Lastname (Organization)"
        # TODO: update with short description of the module and a link to online module documentation
        # _() function marks text as translatable to other languages
        self.parent.helpText = _("""
This is an example of scripted loadable module bundled in an extension.
See more information in <a href="https://github.com/organization/projectname#MyFirstModule">module documentation</a>.
""")
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = _("""
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""")

        # Additional initialization step after application startup is complete
        slicer.app.connect("startupCompleted()", registerSampleData)


#
# Register sample data sets in Sample Data module
#


def registerSampleData():
    """Add data sets to Sample Data module."""
    # It is always recommended to provide sample data for users to make it easy to try the module,
    # but if no sample data is available then this method (and associated startupCompeted signal connection) can be removed.

    import SampleData

    iconsPath = os.path.join(os.path.dirname(__file__), "Resources/Icons")

    # To ensure that the source code repository remains small (can be downloaded and installed quickly)
    # it is recommended to store data sets that are larger than a few MB in a Github release.

    # MyFirstModule1
    SampleData.SampleDataLogic.registerCustomSampleDataSource(
        # Category and sample name displayed in Sample Data module
        category="MyFirstModule",
        sampleName="MyFirstModule1",
        # Thumbnail should have size of approximately 260x280 pixels and stored in Resources/Icons folder.
        # It can be created by Screen Capture module, "Capture all views" option enabled, "Number of images" set to "Single".
        thumbnailFileName=os.path.join(iconsPath, "MyFirstModule1.png"),
        # Download URL and target file name
        uris="https://github.com/Slicer/SlicerTestingData/releases/download/SHA256/998cb522173839c78657f4bc0ea907cea09fd04e44601f17c82ea27927937b95",
        fileNames="MyFirstModule1.nrrd",
        # Checksum to ensure file integrity. Can be computed by this command:
        #  import hashlib; print(hashlib.sha256(open(filename, "rb").read()).hexdigest())
        checksums="SHA256:998cb522173839c78657f4bc0ea907cea09fd04e44601f17c82ea27927937b95",
        # This node name will be used when the data set is loaded
        nodeNames="MyFirstModule1",
    )

    # MyFirstModule2
    SampleData.SampleDataLogic.registerCustomSampleDataSource(
        # Category and sample name displayed in Sample Data module
        category="MyFirstModule",
        sampleName="MyFirstModule2",
        thumbnailFileName=os.path.join(iconsPath, "MyFirstModule2.png"),
        # Download URL and target file name
        uris="https://github.com/Slicer/SlicerTestingData/releases/download/SHA256/1a64f3f422eb3d1c9b093d1a18da354b13bcf307907c66317e2463ee530b7a97",
        fileNames="MyFirstModule2.nrrd",
        checksums="SHA256:1a64f3f422eb3d1c9b093d1a18da354b13bcf307907c66317e2463ee530b7a97",
        # This node name will be used when the data set is loaded
        nodeNames="MyFirstModule2",
    )


#
# BoneMatParameterNode
#


@parameterNodeWrapper
class BoneMatParameterNode:
    """
    The parameters needed by module.

    inputVolume - The volume to threshold.
    imageThreshold - The value at which to threshold the input volume.
    invertThreshold - If true, will invert the threshold.
    thresholdedVolume - The output volume that will contain the thresholded volume.
    invertedVolume - The output volume that will contain the inverted thresholded volume.
    """

    inputCT: vtkMRMLScalarVolumeNode
    inputVolMesh: vtkMRMLModelNode
    outputVolMesh: vtkMRMLModelNode

    valuesPreset: str
    downloadFormat: str
    ctDensitySlope: float
    ctDensityIntercept: float
    ashDensityOffset: float
    ashDensityScale: float
    apparentDensityDivisor: float
    modulusScale: float
    modulusExponent: float

#
# BoneMatWidget
#


class BoneMatWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._parameterNodeGuiTag = None

    def setup(self) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath("UI/BoneMat.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = BoneMatLogic()

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # Combo Boxes
        self.ui.presetSelector.connect("currentIndexChanged(int)", self.onPresetSelection)

        # Buttons
        self.ui.applyButton.connect("clicked(bool)", self.onApplyButton)
        self.ui.downloadVTKButton.connect("clicked(bool)", self.onDownloadVTKButton)
        self.ui.savePresetButton.connect("clicked(bool)", self.onSavePresetButton)
        self.ui.deletePresetButton.connect("clicked(bool)", self.onDeletePresetButton)

        # Checkboxes
        self.ui.phantomCalibrationCheckBox.connect("clicked(bool)", self.onPhantomCheckBox)

        # Phantom calibration table
        self.ui.phantomCalibrationTableWidget.connect("cellChanged(int,int)", self.onPhantomCellChange)

        # Adjusting the UI of the phantom calibration table
        table = self.ui.phantomCalibrationTableWidget
        
        table.horizontalHeader().setSectionResizeMode(qt.QHeaderView.Stretch)

        height = table.horizontalHeader().height
        for row in range(table.rowCount):
            height += table.rowHeight(row)
        height += table.frameWidth * 2
        table.setFixedHeight(height)

        # Phantom calibration is initially inactive
        self.ui.phantomCalibrationTableWidget.enabled = False

        # Setup download formats
        self.ui.downloadFormatSelector.addItem('VTK', '.vtk')
        self.ui.downloadFormatSelector.addItem('FEBio (.feb)', '.feb')
        self.ui.downloadFormatSelector.addItem('Abaqus (.inp)', '.inp')
        self.ui.downloadFormatSelector.addItem('Ansys (.msh)', '.msh')
        self.ui.downloadFormatSelector.setCurrentIndex(0)

        # Setup algorithm choices
        self.ui.algoSelector.addItem('HU averaging (Bonemat v1)', 'None')
        self.ui.algoSelector.addItem('HU integration (Bonemat v2)', 'HU')
        self.ui.algoSelector.addItem('E integration (Bonemat v3)', 'E')
        self.ui.algoSelector.setCurrentIndex(1)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

        self.setBoneDensityPresetValues()

    def cleanup(self) -> None:
        """Called when the application closes and the module widget is destroyed."""
        self.removeObservers()

    def enter(self) -> None:
        """Called each time the user opens this module."""
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self) -> None:
        """Called each time the user opens a different module."""
        # Do not react to parameter node changes (GUI will be updated when the user enters into the module)
        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self._parameterNodeGuiTag = None
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)

    def onSceneStartClose(self, caller, event) -> None:
        """Called just before the scene is closed."""
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event) -> None:
        """Called just after the scene is closed."""
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self) -> None:
        """Ensure parameter node exists and observed."""
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

        # TODO: Select default input nodes if nothing is selected yet to save a few clicks for the user
        # if not self._parameterNode.inputVolume:
        #     firstVolumeNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLMarkupsFiducialNode")
        #     if firstVolumeNode:
        #         self._parameterNode.inputVolume = firstVolumeNode

    def setParameterNode(self, inputParameterNode: Optional[BoneMatParameterNode]) -> None:
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """

        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)
        self._parameterNode = inputParameterNode
        if self._parameterNode:
            # Note: in the .ui file, a Qt dynamic property called "SlicerParameterName" is set on each
            # ui element that needs connection.
            self._parameterNodeGuiTag = self._parameterNode.connectGui(self.ui)
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)
            self._checkCanApply()

    def _checkCanApply(self, caller=None, event=None) -> None:
        if self._parameterNode and self._parameterNode.inputCT and self._parameterNode.inputVolMesh and self._parameterNode.outputVolMesh:
            self.ui.applyButton.toolTip = _("Commence material property assignment")
            self.ui.applyButton.enabled = True
        else:
            self.ui.applyButton.toolTip = _("Select input CT, input mesh and output mesh")
            self.ui.applyButton.enabled = False

    def setBoneDensityPresetValues(self) -> None:
        settings = qt.QSettings()
        jsonPresets = settings.value('BoneMat/BoneDensityPresets')
        presets = None
        try:
            if jsonPresets is None:
                raise Exception()
            presets = json.loads(jsonPresets)
        except:
            # no presets initialised, or object wasn't valid json
            # write a 'None' preset with 0s as the 7 values
            presets = {
                'None': {
                    'ctDensitySlope': 0,
                    'ctDensityIntercept': 0,
                    'ashDensityOffset': 0,
                    'ashDensityScale': 0,
                    'apparentDensityDivisor': 0,
                    'modulusScale': 0,
                    'modulusExponent': 0
                }
            }
            settings.setValue('BoneMat/BoneDensityPresets', json.dumps(presets))

        for name, values in presets.items():
            self.ui.presetSelector.addItem(name, values)

        index = self.ui.presetSelector.findText('Femur')
        if index == -1:
            index = self.ui.presetSelector.findText('None')
        self.ui.presetSelector.setCurrentIndex(index)

    def onPresetSelection(self) -> None:
        values = self.ui.presetSelector.currentData

        self._parameterNode.ctDensitySlope = values['ctDensitySlope']
        self._parameterNode.ctDensityIntercept = values['ctDensityIntercept']
        self._parameterNode.ashDensityOffset = values['ashDensityOffset']
        self._parameterNode.ashDensityScale = values['ashDensityScale']
        self._parameterNode.apparentDensityDivisor = values['apparentDensityDivisor']
        self._parameterNode.modulusScale = values['modulusScale']
        self._parameterNode.modulusExponent = values['modulusExponent']

    def onSavePresetButton(self) -> None:
        name = qt.QInputDialog().getText(None, 'Save', 'Save preset as: (will override an existing preset with the same name)')
        if name is None or name == '':
            return
        if name == 'None':
            message = qt.QMessageBox()
            message.setText('"None" is a reserved preset name, choose another name')
            message.exec()
            return
        
        newPresetValues = {
            'ctDensitySlope': self._parameterNode.ctDensitySlope,
            'ctDensityIntercept': self._parameterNode.ctDensityIntercept,
            'ashDensityOffset': self._parameterNode.ashDensityOffset,
            'ashDensityScale': self._parameterNode.ashDensityScale,
            'apparentDensityDivisor': self._parameterNode.apparentDensityDivisor,
            'modulusScale': self._parameterNode.modulusScale,
            'modulusExponent': self._parameterNode.modulusExponent
        }
        
        settings = qt.QSettings()
        presets = json.loads(settings.value('BoneMat/BoneDensityPresets'))
        presets[name] = newPresetValues
        settings.setValue('BoneMat/BoneDensityPresets', json.dumps(presets))

        self.ui.presetSelector.addItem(name, newPresetValues)
        index = self.ui.presetSelector.findText(name)
        self.ui.presetSelector.setCurrentIndex(index)
    
    def onDeletePresetButton(self) -> None:
        presetName = self.ui.presetSelector.currentText
        if presetName == 'None':
            message = qt.QMessageBox()
            message.setText('Cannot delete "None" preset')
            message.exec()
            return
        
        settings = qt.QSettings()
        presets = json.loads(settings.value('BoneMat/BoneDensityPresets'))
        presets.pop(presetName)
        settings.setValue('BoneMat/BoneDensityPresets', json.dumps(presets))

        currIndex = self.ui.presetSelector.findText(presetName)
        self.ui.presetSelector.removeItem(currIndex)
        noneIndex = self.ui.presetSelector.findText('None')
        self.ui.presetSelector.setCurrentIndex(noneIndex)

    def onApplyButton(self) -> None:
        """Run processing when user clicks "Apply" button."""
        with slicer.util.tryWithErrorDisplay(_("Failed to compute results."), waitCursor=True):
            # Compute output
            self.logic.process(
                self._parameterNode.inputCT,
                self._parameterNode.inputVolMesh,
                self._parameterNode.outputVolMesh,
                self.ui.algoSelector.currentData
            )

    def onDownloadVTKButton(self) -> None:
        outputModel = self._parameterNode.outputVolMesh
        if not outputModel:
            slicer.util.errorDisplay('No output model available to export')
            return
        
        format = self.ui.downloadFormatSelector.currentText
        downloadExt = self.ui.downloadFormatSelector.currentData

        if downloadExt == '.feb':
            message = qt.QMessageBox()
            message.setText('FEBio downloads coming soon!')
            message.exec()
            return
        
        filePath = qt.QFileDialog.getSaveFileName(
            slicer.util.mainWindow(),
            "Save mesh as " + format,
            slicer.app.defaultScenePath
        )

        if not filePath:
            return

        try:
            root, ext = os.path.splitext(filePath)
            if ext.lower() != downloadExt:
                filePath = root + downloadExt

            with tempfile.TemporaryDirectory(prefix='slicer_tmp_') as tmpdir:
                if format == 'VTK':
                    vtkPath = filePath
                else:
                    vtkPath = os.path.join(tmpdir, 'ugrid.vtk')

                ugridWriter = vtk.vtkUnstructuredGridWriter()
                ugridWriter.SetFileName(vtkPath)
                ugridWriter.SetInputData(outputModel.GetUnstructuredGrid())
                ugridWriter.SetFileTypeToASCII()
                ugridWriter.Write()
                
                if format != 'VTK':
                    mesh = meshio.read(vtkPath)
                    mesh.write(filePath)
            
            slicer.util.infoDisplay(f"Mesh saved to: {filePath}")
        except Exception as e:
            slicer.util.errorDisplay(f"Failed to save mesh: {e}")

    def onPhantomCheckBox(self, checked) -> None:
        if checked:
            self.ui.phantomCalibrationTableWidget.enabled = True
            self.ui.ctDensitySlopeSpinBox.enabled = False
            self.ui.ctDensityInterceptSpinBox.enabled = False
        else:
            self.ui.phantomCalibrationTableWidget.enabled = False
            self.ui.ctDensitySlopeSpinBox.enabled = True
            self.ui.ctDensityInterceptSpinBox.enabled = True

    def onPhantomCellChange(self, row, col) -> None:
        table = self.ui.phantomCalibrationTableWidget

        try:
            float(table.item(row, col).text())
        except ValueError:
            table.item(row, col).setText('')
            return
        
        cellItems = [table.item(0, 0), table.item(0, 1), table.item(1, 0), table.item(1, 1)]
        if len([x for x in cellItems if x is not None and x.text() != '']) < 4:
            return
        
        nums = [float(x.text()) for x in cellItems]
        slope = (nums[1] - nums[3]) / (nums[0] - nums[2])
        intercept = nums[1] - slope * nums[0]

        self.ui.ctDensitySlopeSpinBox.value = slope / 1000
        self.ui.ctDensityInterceptSpinBox.value = intercept / 1000

#
# BoneMatLogic
#


class BoneMatLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self) -> None:
        """Called when the logic class is instantiated. Can be used for initializing member variables."""
        ScriptedLoadableModuleLogic.__init__(self)

    def getParameterNode(self):
        return BoneMatParameterNode(super().getParameterNode())
    

    def displayOutputMesh(self, mesh):
        displayNode = mesh.GetDisplayNode()
        if not displayNode:
            displayNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLModelDisplayNode')
            mesh.SetAndObserveDisplayNodeID(displayNode.GetID())

        # colour the mesh by YoungsModulus value
        displayNode.SetScalarVisibility(True)
        displayNode.SetActiveScalar('YoungsModulus', vtk.vtkAssignAttribute.CELL_DATA)
        displayNode.SetScalarRangeFlag(displayNode.UseDataScalarRange)

        # enable and tweak the colour legend for this display
        colourNode = slicer.util.getNode('DivergingBlueRed')
        if colourNode is not None:
            displayNode.SetAndObserveColorNodeID(colourNode.GetID())

        legendNode = slicer.modules.colors.logic().AddDefaultColorLegendDisplayNode(mesh)
        legendNode.SetVisibility(True)
        legendNode.SetNumberOfLabels(3)
        legendNode.SetTitleText('Young\'s Modulus')
        legendNode.SetLabelFormat('%.0f')
        legendNode.SetSize(0.1, 0.5)

        mesh.SetDisplayVisibility(True)

    def adjustAbaqusInput(self, in_path, out_path = None) -> str:
        """
        Fixes meshio ABAQUS output to match py_bonemat_abaqus expected format
        """

        in_path = str(in_path)
        out_path = str(out_path) if out_path else in_path

        lines = Path(in_path).read_text(encoding="utf-8", errors="replace").splitlines(True)

        out_lines = []
        inserted_part = False

        heading_re = re.compile(r"^(\s*)\*HEADING\b")
        node_re    = re.compile(r"^(\s*)\*NODE\b")
        elem_re    = re.compile(r"^(\s*)\*ELEMENT\s*,\s*TYPE\s*=", re.IGNORECASE)

        # py_bonemat_abaqus is strict about capitalisation, so we need multiple fixes
        for line in lines:
            # Replace *HEADING -> *Heading
            line = heading_re.sub(r"\1*Heading", line)

            # Insert *Part,name=model on the line before the first *NODE line
            if (not inserted_part) and node_re.match(line):
                indent = node_re.match(line).group(1)
                out_lines.append(f"{indent}*Part,name=model\n")
                inserted_part = True

            # Replace *NODE -> *Node
            line = node_re.sub(r"\1*Node", line)

            # Replace *ELEMENT, TYPE= -> *Element,type=
            line = elem_re.sub(r"\1*Element,type=", line)

            out_lines.append(line)

        # Add *End Part
        if out_lines and not out_lines[-1].endswith("\n"):
            out_lines[-1] += "\n"
        out_lines.append("*End Part\n")

        Path(out_path).write_text("".join(out_lines), encoding="utf-8")
        return out_path
    
    def reorderedScalars(self, img, flipX, flipY, flipZ):
        nx, ny, nz = img.GetDimensions()
        scalars = img.GetPointData().GetScalars()

        arr = numpy_support.vtk_to_numpy(scalars)

        # VTK point ordering: i fastest, then j, then k
        vol = arr.reshape((nz, ny, nx))

        if flipX:
            vol = vol[:, :, ::-1]
        if flipY:
            vol = vol[:, ::-1, :]
        if flipZ:
            vol = vol[::-1, :, :]

        arr2 = np.ascontiguousarray(vol.reshape(-1))

        vtk_arr = numpy_support.numpy_to_vtk(
            num_array=arr2,
            deep=True,
            array_type=scalars.GetDataType()
        )
        vtk_arr.SetName(scalars.GetName())

        return vtk_arr
    
    def writeVolumeAsRectilinearGrid(self, volNode, outPath):
        """
        Writes a Slicer vtkMRMLScalarVolumeNode as a legacy VTK RECTILINEAR_GRID ASCII file
        with explicit X_COORDINATES / Y_COORDINATES / Z_COORDINATES and POINT_DATA scalars,
        as required by py_bonemat_abaqus.
        Assumes the volume axes are not obliquely rotated.
        """
        img = volNode.GetImageData()
        if img is None:
            raise ValueError("Volume node has no image data")

        nx, ny, nz = img.GetDimensions()

        ijkToRas = vtk.vtkMatrix4x4()
        volNode.GetIJKToRASMatrix(ijkToRas)

        def ras_of(i, j, k):
            v = [i, j, k, 1.0]
            out = [0.0, 0.0, 0.0, 1.0]
            ijkToRas.MultiplyPoint(v, out)
            return out[0], out[1], out[2]

        # Build coordinate arrays in ascending order
        xs = np.array([ras_of(i, 0, 0)[0] for i in range(nx)], dtype=np.float64)
        ys = np.array([ras_of(0, j, 0)[1] for j in range(ny)], dtype=np.float64)
        zs = np.array([ras_of(0, 0, k)[2] for k in range(nz)], dtype=np.float64)
        
        flipX = False
        flipY = False
        flipZ = False
        if xs[0] > xs[-1]:
            xs = xs[::-1]
            flipX = True
        if ys[0] > ys[-1]:
            ys = ys[::-1]
            flipY = True
        if zs[0] > zs[-1]:
            zs = zs[::-1]
            flipZ = True

        rg = vtk.vtkRectilinearGrid()
        rg.SetDimensions(nx, ny, nz)

        xArr = vtk.vtkDoubleArray()
        xArr.SetName("X_COORDINATES")
        xArr.SetNumberOfTuples(nx)
        for i, v in enumerate(xs):
            xArr.SetValue(i, float(v))

        yArr = vtk.vtkDoubleArray()
        yArr.SetName("Y_COORDINATES")
        yArr.SetNumberOfTuples(ny)
        for j, v in enumerate(ys):
            yArr.SetValue(j, float(v))

        zArr = vtk.vtkDoubleArray()
        zArr.SetName("Z_COORDINATES")
        zArr.SetNumberOfTuples(nz)
        for k, v in enumerate(zs):
            zArr.SetValue(k, float(v))

        rg.SetXCoordinates(xArr)
        rg.SetYCoordinates(yArr)
        rg.SetZCoordinates(zArr)

        # Copy scalars from image data to rectilinear grid point data
        scalars = img.GetPointData().GetScalars()
        if scalars is None:
            raise ValueError("CT image data has no point scalars")
        if scalars.GetNumberOfTuples() != nx * ny * nz:
            raise ValueError("Scalar tuple count does not match volume dimensions")

        newScalars = self.reorderedScalars(img, flipX, flipY, flipZ)

        rg.GetPointData().SetScalars(newScalars)

        # Write legacy rectilinear grid
        w = vtk.vtkRectilinearGridWriter()
        w.SetFileName(outPath)
        w.SetInputData(rg)
        w.SetFileTypeToASCII()
        w.Write()

        # Add cell data field to file to satisfy py_bonemat_abaqus requirements
        path = Path(outPath)
        lines = path.read_text(encoding="utf-8").splitlines(True)
        nCells = (nx - 1) * (ny - 1) * (nz - 1)
        # Find POINT_DATA line and insert CELL_DATA before it
        for i, line in enumerate(lines):
            if line.strip().startswith("POINT_DATA"):
                lines.insert(i, f"CELL_DATA {nCells}\n")
                break

        path.write_text("".join(lines), encoding="utf-8")
        

    def process(self, inputCT, inputMesh, outputMesh, algorithm):
        """
        Assign material properties to output volumetric mesh from input CT data
        """
        if not inputMesh.GetUnstructuredGrid():
            slicer.util.errorDisplay('Input mesh must be volumetric, not a surface')
            return
        
        configurePyBonematImports(__file__)

        from py_bonemat_abaqus.run import run as pyBonematAbaqusRun

        with tempfile.TemporaryDirectory(prefix='slicer_tmp_') as tmpdir:
            ctPath = os.path.join(tmpdir, 'ct.vtk')
            paramsPath = os.path.join(tmpdir, 'params.txt')
            meshPath = os.path.join(tmpdir, 'mesh.vtk')
            abaqusMeshPath = os.path.join(tmpdir, 'abaqus_mesh.inp')
            mappedAbaqusMeshPath = os.path.join(tmpdir, 'abaqus_meshMAT.inp')
            mappedMeshPath = os.path.join(tmpdir, 'mapped_mesh.vtk')

            ugridWriter = vtk.vtkUnstructuredGridWriter()
            ugridWriter.SetFileName(meshPath)
            ugridWriter.SetInputData(inputMesh.GetUnstructuredGrid())
            ugridWriter.SetFileTypeToASCII()
            ugridWriter.Write()

            preAbaqusMesh = meshio.read(meshPath)
            preAbaqusMesh.write(abaqusMeshPath)

            self.adjustAbaqusInput(abaqusMeshPath)

            self.writeVolumeAsRectilinearGrid(inputCT, ctPath)

            paraNode = self.getParameterNode()
            with open(paramsPath, 'w') as params:
                params.writelines([
                    'integration = ' + algorithm + '\n',
                    'gapValue = 1\n',
                    'groupingDensity = max\n',
                    'intSteps = 4\n',
                    'rhoQCTa = ' + str(paraNode.ctDensityIntercept) + '\n',
                    'rhoQCTb = ' + str(paraNode.ctDensitySlope) + '\n',
                    'calibrationCorrect = True\n',
                    'numCTparam = single\n',
                    'rhoAsha1 = ' + str(paraNode.ashDensityOffset / (paraNode.ashDensityScale * paraNode.apparentDensityDivisor)) + '\n',
                    'rhoAshb1 =' + str(1 / (paraNode.ashDensityScale * paraNode.apparentDensityDivisor)) + '\n',
                    'numEparam = single\n',
                    'Ea1 = 0\n',
                    'Eb1 = ' + str(paraNode.modulusScale) + '\n',
                    'Ec1 = ' + str(paraNode.modulusExponent) + '\n',
                    'minVal = 0\n', # TODO: make this customisable
                    'poisson = 0.35'
                ])

            pyBonematAbaqusRun(paramsPath, ctPath, abaqusMeshPath)

            mappedAbaqusMesh = meshio.read(mappedAbaqusMeshPath)
            mappedAbaqusMesh.write(mappedMeshPath)

            # read lines to manually assign modulus values
            with open(mappedAbaqusMeshPath, 'r') as f:
                lines = f.readlines()

            ugridReader = vtk.vtkUnstructuredGridReader()
            ugridReader.SetFileName(mappedMeshPath)
            ugridReader.Update()
            ugrid = ugridReader.GetOutput()

        numCells = ugrid.GetNumberOfCells()
        moduli = vtk.vtkDoubleArray()
        moduli.SetName('YoungsModulus')
        moduli.SetNumberOfComponents(1)
        moduli.SetNumberOfTuples(numCells)

        modLookup = []
        i = 0
        while i < len(lines):
            if not lines[i].startswith('*Material'):
                i += 1
                continue

            modLine = lines[i+2]
            mod = float(modLine.strip().split(',')[0])
            if np.isnan(mod):
                mod = 15000
            modLookup.append(mod)
            i += 3

        modulusValues = [0] * numCells
        i = 0
        while i < len(lines):
            if not lines[i].startswith('*Elset'):
                i += 1
                continue

            j = i + 1
            while not lines[j].startswith('*'):
                j += 1
            
            elementLines = lines[i+1:j]
            elemIds = []
            for line in elementLines:
                elemIds.extend(int(x)-1 for x in line.replace("\n", ",").split(",") if x.strip())

            lookup = int(lines[i].strip().split('_')[-1]) - 1
            mod = modLookup[lookup]
            for id in elemIds:
                modulusValues[id] = mod

            i = j

        for cellId in range(numCells):
            moduli.SetValue(cellId, modulusValues[cellId])

        cellData = ugrid.GetCellData()
        if cellData.GetAbstractArray('YoungsModulus') is not None:
            cellData.RemoveArray('YoungsModulus')
        
        cellData.AddArray(moduli)
        cellData.SetScalars(moduli)

        outputMesh.SetAndObserveMesh(ugrid)

        self.displayOutputMesh(outputMesh)

        print('done')


#
# BoneMatTest
#


class BoneMatTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """Do whatever is needed to reset the state - typically a scene clear will be enough."""
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here."""
        self.setUp()
        self.test_MyFirstModule1()

    def test_MyFirstModule1(self):
        """Ideally you should have several levels of tests.  At the lowest level
        tests should exercise the functionality of the logic with different inputs
        (both valid and invalid).  At higher levels your tests should emulate the
        way the user would interact with your code and confirm that it still works
        the way you intended.
        One of the most important features of the tests is that it should alert other
        developers when their changes will have an impact on the behavior of your
        module.  For example, if a developer removes a feature that you depend on,
        your test should break so they know that the feature is needed.
        """

        self.delayDisplay("Starting the test")

        # Get/create input data

        import SampleData

        registerSampleData()
        inputVolume = SampleData.downloadSample("MyFirstModule1")
        self.delayDisplay("Loaded test data set")

        inputScalarRange = inputVolume.GetImageData().GetScalarRange()
        self.assertEqual(inputScalarRange[0], 0)
        self.assertEqual(inputScalarRange[1], 695)

        outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
        threshold = 100

        # Test the module logic

        logic = BoneMatLogic()

        # Test algorithm with non-inverted threshold
        logic.process(inputVolume, outputVolume, threshold, True)
        outputScalarRange = outputVolume.GetImageData().GetScalarRange()
        self.assertEqual(outputScalarRange[0], inputScalarRange[0])
        self.assertEqual(outputScalarRange[1], threshold)

        # Test algorithm with inverted threshold
        logic.process(inputVolume, outputVolume, threshold, False)
        outputScalarRange = outputVolume.GetImageData().GetScalarRange()
        self.assertEqual(outputScalarRange[0], inputScalarRange[0])
        self.assertEqual(outputScalarRange[1], inputScalarRange[1])

        self.delayDisplay("Test passed")
