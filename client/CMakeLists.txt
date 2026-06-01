cmake_minimum_required(VERSION 3.21)
project(epic-client LANGUAGES CXX)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Debug CACHE STRING "Build type" FORCE)
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ── System dependencies ────────────────────────────────────────────────────────
find_package(Threads REQUIRED)

# ── Fetched dependencies ───────────────────────────────────────────────────────
include(FetchContent)

find_package(ftxui 5.0 QUIET)
find_package(nlohmann_json 3.11 QUIET)
find_package(CLI11 2.4 QUIET)

set(_fetch_deps "")

if(NOT ftxui_FOUND)
    FetchContent_Declare(ftxui
        GIT_REPOSITORY https://github.com/ArthurSonzogni/FTXUI
        GIT_TAG        v5.0.0
        GIT_SHALLOW    TRUE
    )
    list(APPEND _fetch_deps ftxui)
endif()

if(NOT nlohmann_json_FOUND)
    FetchContent_Declare(nlohmann_json
        GIT_REPOSITORY https://github.com/nlohmann/json
        GIT_TAG        v3.11.3
        GIT_SHALLOW    TRUE
    )
    list(APPEND _fetch_deps nlohmann_json)
endif()

if(NOT CLI11_FOUND)
    FetchContent_Declare(CLI11
        GIT_REPOSITORY https://github.com/CLIUtils/CLI11
        GIT_TAG        v2.4.2
        GIT_SHALLOW    TRUE
    )
    list(APPEND _fetch_deps CLI11)
endif()

if(_fetch_deps)
    FetchContent_MakeAvailable(${_fetch_deps})
endif()

# ── Target ────────────────────────────────────────────────────────────────────
set(SOURCES
    src/main.cpp
    src/client/Client.cpp
    src/crypto/CryptoProxy.cpp
    src/messaging/Message.cpp
    src/messaging/Conversation.cpp
    src/messaging/MessageStore.cpp
    src/models/User.cpp
    src/ui/App.cpp
)

add_executable(epic-client ${SOURCES})

target_include_directories(epic-client PRIVATE src)

target_link_libraries(epic-client PRIVATE
    Threads::Threads
    ftxui::screen
    ftxui::dom
    ftxui::component
    nlohmann_json::nlohmann_json
    CLI11::CLI11
)

target_compile_options(epic-client PRIVATE
    $<$<CONFIG:Debug>:-Wall;-Wextra;-Wpedantic;-g>
    $<$<CONFIG:Release>:-O2>
)
