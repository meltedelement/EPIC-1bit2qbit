#include "ui/App.h"

App::App(AppCallbacks cbs) : cbs_{std::move(cbs)} {}

void App::run() {
    // TODO: build FTXUI component tree (login screen → chat screen)
    //       and call ftxui::ScreenInteractive::Fullscreen().Loop(renderer)
}

void App::push_message(const std::string& from, const std::string& text) {
    chat_log_.push_back(from + ": " + text);
    // TODO: post a UI refresh event
}

void App::push_status(const std::string& text) {
    status_log_.push_back(text);
}
