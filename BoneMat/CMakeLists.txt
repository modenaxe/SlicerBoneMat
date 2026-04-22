#-----------------------------------------------------------------------------
set(MODULE_NAME BoneMat)

#-----------------------------------------------------------------------------
set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  )

set(MODULE_PYTHON_RESOURCES
  Resources/Icons/${MODULE_NAME}.png
  Resources/Icons/${MODULE_NAME}Tutorial.png
  Resources/UI/${MODULE_NAME}.ui
  )

set(PYBONEMAT_PACKAGE_SOURCE_DIR
  ${CMAKE_CURRENT_SOURCE_DIR}/../external/py_bonemat_abaqus/py_bonemat_abaqus
  )

#-----------------------------------------------------------------------------
slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
  WITH_GENERIC_TESTS
  )

#-----------------------------------------------------------------------------
install(
  DIRECTORY ${PYBONEMAT_PACKAGE_SOURCE_DIR}/
  DESTINATION ${Slicer_INSTALL_QTSCRIPTEDMODULES_LIB_DIR}/py_bonemat_abaqus
  FILES_MATCHING PATTERN "*.py"
  )

#-----------------------------------------------------------------------------
if(BUILD_TESTING)

  # Register the unittest subclass in the main script as a ctest.
  # Note that the test will also be available at runtime.
  slicer_add_python_unittest(SCRIPT ${MODULE_NAME}.py)

  # Additional build-time testing
  add_subdirectory(Testing)
endif()
