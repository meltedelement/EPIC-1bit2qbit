#include "ui/App.h"

#include <chrono>
#include <ctime>
#include <utility>

#include <ftxui/component/component.hpp>
#include <ftxui/component/event.hpp>
#include <ftxui/component/screen_interactive.hpp>
#include <ftxui/dom/elements.hpp>

using namespace ftxui;

namespace {

std::string format_time(int64_t ms) {
    std::time_t t = static_cast<std::time_t>(ms / 1000);
    const std::tm* tp = std::localtime(&t);
    char buf[6];
    std::strftime(buf, sizeof(buf), "%H:%M", tp);
    return {buf};
}

int64_t now_ms() {
    using namespace std::chrono;
    return duration_cast<milliseconds>(system_clock::now().time_since_epoch()).count();
}

}  // namespace

App::App(AppCallbacks cbs) : cbs_{std::move(cbs)} {}

void App::push_status(std::string msg) { status_msg_ = std::move(msg); }

void App::advance_to_chat(std::string username) {
    local_username_ = std::move(username);
    screen_ = 1;
}

void App::seed_placeholder_data() {
    local_username_    = "alice";
    const int64_t base = now_ms() - 3'600'000;

    {
        Conversation conv{"bob"};
        conv.add_message({.id=1, .peer="bob", .recipient="alice",   .timestamp_ms=base,            .body="Hey, are you there?"});
        conv.add_message({.id=2, .peer="bob", .recipient="bob",     .timestamp_ms=base+60'000,     .body="Yeah, what's up?"});
        conv.add_message({.id=3, .peer="bob", .recipient="alice",   .timestamp_ms=base+120'000,    .body="Did you see the lecture notes?"});
        conversations_.push_back(std::move(conv));
    }
    {
        Conversation conv{"charlie"};
        conv.add_message({.id=4, .peer="charlie", .recipient="alice",   .timestamp_ms=base+1'800'000, .body="Project meeting at 3pm"});
        conv.add_message({.id=5, .peer="charlie", .recipient="charlie", .timestamp_ms=base+1'860'000, .body="Sure, I'll be there"});
        conversations_.push_back(std::move(conv));
    }
    {
        Conversation conv{"diana"};
        conv.add_message({.id=6, .peer="diana", .recipient="diana", .timestamp_ms=base+3'000'000, .body="I'll send the files over"});
        conversations_.push_back(std::move(conv));
    }
}

void App::run() {
    // Only seed placeholder data when running without a real Client wired up.
    if (!cbs_.on_login)
        seed_placeholder_data();

    auto screen = ScreenInteractive::Fullscreen();

    // ── Login ─────────────────────────────────────────────────────────────────
    InputOption pin_opt;
    pin_opt.password = true;

    auto username_input = Input(&login_username_, "username");
    auto pin_input      = Input(&login_pin_,      "PIN", pin_opt);

    auto login_btn = Button(" Login ", [&] {
        if (login_username_.empty() || login_pin_.empty()) return;
        if (cbs_.on_login) {
            cbs_.on_login(login_username_, login_pin_);
        } else {
            advance_to_chat(login_username_);
        }
    }, ButtonOption::Ascii());

    auto register_btn = Button(" Register ", [&] {
        if (login_username_.empty() || login_pin_.empty()) return;
        if (cbs_.on_register) {
            cbs_.on_register(login_username_, login_pin_);
        } else {
            advance_to_chat(login_username_);
        }
    }, ButtonOption::Ascii());

    auto login_form = Container::Vertical({
        username_input,
        pin_input,
        Container::Horizontal({register_btn, login_btn}),
    });

    auto login_renderer = Renderer(login_form, [&]() -> Element {
        Element status = status_msg_.empty()
            ? text("") | dim
            : text(" " + status_msg_) | color(Color::Red);

        return vbox({
            filler(),
            hbox({
                filler(),
                vbox({
                    text("EPIC Secure Messenger") | bold | center,
                    text("End-to-end encrypted messaging") | dim | center,
                    separator(),
                    hbox({text(" Username : "), username_input->Render() | flex}),
                    hbox({text(" PIN      : "), pin_input->Render()      | flex}),
                    separator(),
                    hbox({
                        filler(),
                        register_btn->Render(),
                        text("  "),
                        login_btn->Render(),
                        filler(),
                    }),
                    status | center,
                }) | border | size(WIDTH, EQUAL, 46),
                filler(),
            }),
            filler(),
        });
    });

    // ── Chat ──────────────────────────────────────────────────────────────────
    std::vector<std::string> conv_names;
    for (const auto& c : conversations_)
        conv_names.push_back(c.peer());

    auto conv_menu = Menu(&conv_names, &selected_conv_);

    auto do_send = [&] {
        if (compose_text_.empty()) return;
        if (cbs_.on_send) {
            if (conversations_.empty()) return;
            cbs_.on_send(conversations_[selected_conv_].peer(), compose_text_);
            compose_text_.clear();
        } else {
            // Placeholder: append directly without encryption.
            if (conversations_.empty()) return;
            Message m;
            m.id           = static_cast<uint64_t>(now_ms());
            m.peer         = conversations_[selected_conv_].peer();
            m.recipient    = m.peer;
            m.timestamp_ms = now_ms();
            m.type         = MessageType::Standard;
            m.body         = compose_text_;
            conversations_[selected_conv_].add_message(std::move(m));
            compose_text_.clear();
        }
    };

    auto compose_input = Input(&compose_text_, "Type a message...");
    compose_input = CatchEvent(compose_input, [&](Event e) {
        if (e == Event::Return) { do_send(); return true; }
        return false;
    });

    auto send_btn = Button("Send", do_send, ButtonOption::Ascii());

    auto chat_right  = Container::Horizontal({compose_input, send_btn});
    auto chat_layout = Container::Horizontal({conv_menu, chat_right});

    auto chat_renderer = Renderer(chat_layout, [&]() -> Element {
        Elements msg_els;
        if (!conversations_.empty()) {
            for (const auto& m : conversations_[selected_conv_].messages()) {
                bool sent = (m.recipient != local_username_);
                std::string label = sent
                    ? "[" + format_time(m.timestamp_ms) + "] you : "
                    : "[" + format_time(m.timestamp_ms) + "] " + m.peer + " : ";
                msg_els.push_back(hbox({
                    text(label) | (sent ? color(Color::Blue) : color(Color::White)),
                    text(m.body) | flex,
                }));
            }
            msg_els.back() = msg_els.back() | focus;
        } else {
            msg_els.push_back(text("No messages yet.") | dim | center);
        }

        const std::string peer_title = conversations_.empty()
            ? "No conversations"
            : conversations_[selected_conv_].peer();

        return vbox({
            hbox({
                text("  EPIC") | bold | color(Color::Cyan),
                text(" Secure Messenger") | color(Color::Cyan),
                filler(),
                text(" " + local_username_ + " ") | bold,
            }),
            separator(),
            hbox({
                vbox({
                    text(" Conversations") | bold,
                    separator(),
                    conv_menu->Render() | flex,
                }) | border | size(WIDTH, EQUAL, 22),
                vbox({
                    text("  " + peer_title) | bold,
                    separator(),
                    yframe(vbox(msg_els)) | flex,
                    separator(),
                    hbox({
                        text(" > "),
                        compose_input->Render() | flex,
                        text(" "),
                        send_btn->Render(),
                    }),
                }) | border | flex,
            }) | flex,
        });
    });

    // ── Root ──────────────────────────────────────────────────────────────────
    auto root = Container::Tab(Components{login_renderer, chat_renderer}, &screen_);
    screen.Loop(root);
}
