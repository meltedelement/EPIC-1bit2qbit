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
