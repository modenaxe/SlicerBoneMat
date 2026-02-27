import os
import math
from typing import Optional

import vtk
import numpy as np
import json

from __main__ import qt

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

        # Adjusting the UI of the phantom calibration table
        table = self.ui.phantomCalibrationTableWidget
        
        table.horizontalHeader().setSectionResizeMode(qt.QHeaderView.Stretch)

        height = table.horizontalHeader().height
        for row in range(table.rowCount):
            height += table.rowHeight(row)
        height += table.frameWidth * 2
        table.setFixedHeight(height)

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
            self.logic.process(self._parameterNode.inputCT, self._parameterNode.inputVolMesh, self._parameterNode.outputVolMesh)

    def onDownloadVTKButton(self) -> None:
        outputModel = self._parameterNode.outputVolMesh
        if not outputModel:
            slicer.util.errorDisplay('No output model available to export')
            return
        
        filePath = qt.QFileDialog.getSaveFileName(
            slicer.util.mainWindow(),
            "Save mesh as VTK",
            slicer.app.defaultScenePath,
            "VTK files (*.vtk)"
        )

        if not filePath:
            return

        try:
            root, ext = os.path.splitext(filePath)
            if ext.lower() != ".vtk":
                filePath = root + ".vtk"
            ok = slicer.util.saveNode(outputModel, filePath)
            if not ok:
                raise RuntimeError(f"Failed to save model to {filePath}")
            
            slicer.util.infoDisplay(f"Mesh saved to: {filePath}")
        except Exception as e:
            slicer.util.errorDisplay(f"Failed to save mesh: {e}")


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
    
    def getModArray(self, huVals):
        paraNode = self.getParameterNode()
        
        ctDensity = paraNode.ctDensitySlope * huVals + paraNode.ctDensityIntercept
        ashDensity = (ctDensity + paraNode.ashDensityOffset) / paraNode.ashDensityScale
        appDensity = ashDensity / paraNode.apparentDensityDivisor
        modVals = paraNode.modulusScale * (appDensity ** paraNode.modulusExponent)
        return modVals
    
    def computeYoungsModulus(self, CT, ugrid):
        locator = vtk.vtkStaticCellLocator()
        locator.SetDataSet(ugrid)
        locator.BuildLocator()

        imageData = CT.GetImageData()
        iMin, iMax, jMin, jMax, kMin, kMax = imageData.GetExtent()

        ijkToRas = vtk.vtkMatrix4x4()
        CT.GetIJKToRASMatrix(ijkToRas)

        numCells = ugrid.GetNumberOfCells()
        sumE = np.zeros(numCells, dtype=float)
        countE = np.zeros(numCells, dtype=int)

        ctArray = slicer.util.arrayFromVolume(CT).astype(np.float32)
        modArray = self.getModArray(ctArray)

        pcoords = [0.0, 0.0, 0.0]
        weights = [0.0] * ugrid.GetMaxCellSize()

        # loop through all the voxels, find the cell that contains each voxel,
        # convert from HU to Young's modulus for each voxel and add it to the
        # sum of contained voxel moduli for each cell
        genericCell = vtk.vtkGenericCell()
        for k in range(kMin, kMax + 1):
            for j in range(jMin, jMax + 1):
                for i in range(iMin, iMax + 1):
                    ijk = [i, j, k, 1.0]
                    ras = [0.0, 0.0, 0.0, 0.0]
                    ijkToRas.MultiplyPoint(ijk, ras)
                    x, y, z = ras[0], ras[1], ras[2]

                    cellId = locator.FindCell([x, y, z], 1e-6, genericCell, pcoords, weights)
                    if cellId < 0:
                        continue

                    sumE[cellId] += modArray[k, j, i]
                    countE[cellId] += 1

        rasToIjk = vtk.vtkMatrix4x4()
        CT.GetRASToIJKMatrix(rasToIjk)

        # for the cells which contain no voxels, we instead use the 8 voxel centroids
        # that surround the cell
        for cellId in range(numCells):
            if countE[cellId] > 0:
                continue

            cell = ugrid.GetCell(cellId)
            bounds = [0] * 6
            cell.GetBounds(bounds)

            centroidRAS = (
                0.5 * (bounds[0] + bounds[1]),
                0.5 * (bounds[2] + bounds[3]),
                0.5 * (bounds[4] + bounds[5])
            )
            ijk = [0.0, 0.0, 0.0, 0.0]
            ras = [centroidRAS[0], centroidRAS[1], centroidRAS[2], 1.0]

            rasToIjk.MultiplyPoint(ras, ijk)
            i, j, k = ijk[0], ijk[1], ijk[2]

            nz, ny, nx = ctArray.shape  # [k, j, i]

            def clamp(v, lo, hi):
                return max(lo, min(hi, v))

            i0 = clamp(math.floor(i), 0, nx - 1)
            i1 = clamp(math.ceil(i),  0, nx - 1)
            j0 = clamp(math.floor(j), 0, ny - 1)
            j1 = clamp(math.ceil(j),  0, ny - 1)
            k0 = clamp(math.floor(k), 0, nz - 1)
            k1 = clamp(math.ceil(k),  0, nz - 1)

            mod1 = modArray[k0, j0, i0]
            mod2 = modArray[k0, j0, i1]
            mod3 = modArray[k0, j1, i0]
            mod4 = modArray[k0, j1, i1]
            mod5 = modArray[k1, j0, i0]
            mod6 = modArray[k1, j0, i1]
            mod7 = modArray[k1, j1, i0]
            mod8 = modArray[k1, j1, i1]
            modVals = [mod1, mod2, mod3, mod4, mod5, mod6, mod7, mod8]

            sumE[cellId] += sum(modVals)
            countE[cellId] += 8

        avgE = np.zeros(numCells, dtype=float)
        avgE = sumE / countE
        return avgE
    
    def assignMaterialProperties(self, CT, ugrid):
        numCells = ugrid.GetNumberOfCells()
        
        moduli = vtk.vtkDoubleArray()
        moduli.SetName('YoungsModulus')
        moduli.SetNumberOfComponents(1)
        moduli.SetNumberOfTuples(numCells)

        print('about to compute modulus')
        modulusValues = self.computeYoungsModulus(CT, ugrid)
        # modulusValues = np.full(numCells, 5)
        # paraNode = self.getParameterNode()
        # print(paraNode.ctDensitySlope)
        # print(paraNode.ctDensityIntercept)
        # print(paraNode.ashDensityOffset)
        # print(paraNode.ashDensityScale)
        # print(paraNode.apparentDensityDivisor)
        # print(paraNode.modulusScale)
        # print(paraNode.modulusExponent)
        print('computed moduli')
        for cellId in range(numCells):
            moduli.SetValue(cellId, modulusValues[cellId])

        cellData = ugrid.GetCellData()
        if cellData.GetAbstractArray('YoungsModulus') is not None:
            cellData.RemoveArray('YoungsModulus')
        
        cellData.AddArray(moduli)
        cellData.SetScalars(moduli)

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

    def process(self, inputCT, inputMesh, outputMesh):
        """
        Assign material properties to output volumetric mesh from input CT data
        """

        if not inputMesh.GetUnstructuredGrid():
            slicer.util.errorDisplay('Input mesh must be volumetric, not a surface')
            return
        
        gridCopy = vtk.vtkUnstructuredGrid()
        gridCopy.DeepCopy(inputMesh.GetUnstructuredGrid())
        outputMesh.SetAndObserveMesh(gridCopy)

        self.assignMaterialProperties(inputCT, outputMesh.GetUnstructuredGrid())

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
