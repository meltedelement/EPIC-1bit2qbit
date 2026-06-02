#pragma once
#include <chrono>
#include <cstdio>
#include <ctime>
#include <string>

#ifdef _WIN32
#  include <windows.h>
inline const char* _epic_log_path() {
    static char path[MAX_PATH];
    static bool ready = false;
    if (!ready) {
        char tmp[MAX_PATH];
        GetTempPathA(MAX_PATH, tmp);
        std::snprintf(path, sizeof(path), "%sepic-client.log", tmp);
        ready = true;
    }
    return path;
}
#endif

inline void epic_log(const std::string& msg) {
#ifdef _WIN32
    static FILE* f = std::fopen(_epic_log_path(), "a");
#else
    static FILE* f = std::fopen("/tmp/epic-client.log", "a");
#endif
    if (!f) return;
    using namespace std::chrono;
    auto now  = system_clock::now();
    auto t    = system_clock::to_time_t(now);
    auto ms   = duration_cast<milliseconds>(now.time_since_epoch()).count() % 1000;
    char ts[24];
    std::strftime(ts, sizeof(ts), "%H:%M:%S", std::localtime(&t));
    std::fprintf(f, "[%s.%03lld] %s\n", ts, static_cast<long long>(ms), msg.c_str());
    std::fflush(f);
}

// Opens a separate terminal window tailing the log file. No-op on Windows.
// Tries common terminal emulators in order; silently does nothing if none found.
inline void open_log_terminal() {
#ifndef _WIN32
    // Ensure the log file exists before tail opens it.
    if (FILE* f = std::fopen("/tmp/epic-client.log", "a")) std::fclose(f);

    struct { const char* bin; const char* args; } terms[] = {
        {"xterm",          "-title 'EPIC Logs' -e 'tail -f /tmp/epic-client.log'"},
        {"gnome-terminal", "--title 'EPIC Logs' -- bash -c 'tail -f /tmp/epic-client.log'"},
        {"alacritty",      "--title 'EPIC Logs' -e bash -c 'tail -f /tmp/epic-client.log'"},
        {"kitty",          "--title 'EPIC Logs' bash -c 'tail -f /tmp/epic-client.log'"},
        {"konsole",        "-e bash -c 'tail -f /tmp/epic-client.log'"},
        {"xfce4-terminal", "-e 'tail -f /tmp/epic-client.log'"},
    };

    for (const auto& t : terms) {
        char check[64];
        std::snprintf(check, sizeof(check), "which %s >/dev/null 2>&1", t.bin);
        if (std::system(check) == 0) {
            char cmd[256];
            std::snprintf(cmd, sizeof(cmd), "%s %s &", t.bin, t.args);
            std::system(cmd);
            return;
        }
    }
#endif
}
