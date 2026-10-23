cmake_minimum_required(VERSION 3.17)

project(FanControl VERSION 1.2.0 LANGUAGES C)

# C standard
set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

# Security Hardening & Strict Warnings
add_compile_options(
  -Wall -Wextra -Wpedantic
  -Wformat=2 -Wformat-security
  -fstack-protector-strong
  -D_FORTIFY_SOURCE=2
)
add_link_options(
  -Wl,-z,relro,-z,now
)

# Main CLI executable
add_executable(fan-control src/main.c)
target_link_libraries(fan-control PRIVATE m)
set_target_properties(fan-control PROPERTIES
  POSITION_INDEPENDENT_CODE ON
)

# Shared library for GUI / ctypes
add_library(fan-ec SHARED src/ec_lib.c)
target_link_libraries(fan-ec PRIVATE m)
set_target_properties(fan-ec PROPERTIES
  POSITION_INDEPENDENT_CODE ON
)

# Install rules
include(GNUInstallDirs)

install(
  TARGETS fan-control fan-ec
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
  PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE
              GROUP_READ GROUP_EXECUTE
              WORLD_READ WORLD_EXECUTE
)

# Install GUI executable (native Python script using system PyQt)
install(
  PROGRAMS fan_gui.py
  DESTINATION ${CMAKE_INSTALL_BINDIR}
  RENAME fan-gui
  PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE
              GROUP_READ GROUP_EXECUTE
              WORLD_READ WORLD_EXECUTE
)

# Desktop launcher entry
install(
  FILES fan-control.desktop
  DESTINATION ${CMAKE_INSTALL_DATADIR}/applications
)

# Hicolor application icons
install(
  DIRECTORY assets/icons/hicolor/
  DESTINATION ${CMAKE_INSTALL_DATADIR}/icons/hicolor
)

# CPack Packaging Configuration
set(CPACK_PACKAGE_NAME "fan-control")
set(CPACK_PACKAGE_VENDOR "Fan Control Project")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "Hardware EC Fan Control Utility and Native Desktop GUI")
set(CPACK_PACKAGE_VERSION "1.2.0")
set(CPACK_PACKAGE_VERSION_MAJOR "1")
set(CPACK_PACKAGE_VERSION_MINOR "2")
set(CPACK_PACKAGE_VERSION_PATCH "0")
set(CPACK_PACKAGE_CONTACT "Fan Control Maintainers <maintainers@fan-control.local>")
set(CPACK_PACKAGE_FILE_NAME "${CPACK_PACKAGE_NAME}_${CPACK_PACKAGE_VERSION}_amd64")

# Debian Package (.deb) settings
set(CPACK_DEBIAN_PACKAGE_SECTION "utils")
set(CPACK_DEBIAN_PACKAGE_PRIORITY "optional")
set(CPACK_DEBIAN_PACKAGE_DEPENDS "python3, python3-pyqt6 | python3-pyqt5, libcap2-bin, policykit-1 | polkitd")
set(CPACK_DEBIAN_PACKAGE_SHLIBDEPS OFF)
set(CPACK_DEBIAN_PACKAGE_CONTROL_EXTRA 
    "${CMAKE_CURRENT_SOURCE_DIR}/packaging/postinst;${CMAKE_CURRENT_SOURCE_DIR}/packaging/postrm")

# RPM Package (.rpm) settings
set(CPACK_RPM_PACKAGE_GROUP "Applications/System")
set(CPACK_RPM_PACKAGE_LICENSE "GPLv3")
set(CPACK_RPM_PACKAGE_AUTOREQPROV "no")
set(CPACK_RPM_PACKAGE_REQUIRES "python3, python3-qt6, libcap")
set(CPACK_RPM_POST_INSTALL_SCRIPT_FILE "${CMAKE_CURRENT_SOURCE_DIR}/packaging/postinst")
set(CPACK_RPM_POST_UNINSTALL_SCRIPT_FILE "${CMAKE_CURRENT_SOURCE_DIR}/packaging/postrm")

set(CPACK_GENERATOR "DEB;RPM;TGZ")

include(CPack)
