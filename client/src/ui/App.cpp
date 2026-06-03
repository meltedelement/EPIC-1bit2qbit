#include "ui/App.h"
#include "log.h"
#include <nlohmann/json.hpp>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <ctime>
#include <thread>
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

void App::start_lockout(int seconds) {
    if (lockout_thread_.joinable()) lockout_thread_.join();
    lockout_active_    = true;
    lockout_remaining_ = seconds;
    lockout_thread_ = std::thread([this] {
        while (lockout_remaining_ > 0 && !lockout_quit_) {
            push_status("Incorrect PIN — try again in " +
                        std::to_string(lockout_remaining_.load()) + "s.");
            std::this_thread::sleep_for(std::chrono::seconds(1));
            --lockout_remaining_;
        }
        if (!lockout_quit_) {
            lockout_active_ = false;
            push_status("");
        }
    });
}

void App::set_connected(bool connected) {
    connected_ = connected;
    if (screen_ptr_)
        screen_ptr_->PostEvent(Event::Custom);
}

void App::push_status(std::string msg) {
    epic_log("push_status: " + msg);
    if (screen_ptr_) {
        screen_ptr_->Post([this, m = std::move(msg)]() mutable { status_msg_ = std::move(m); });
    } else {
        status_msg_ = std::move(msg);
    }
}

void App::push_message(const Message& msg) {
    auto update = [this, msg] {
        auto it = std::find_if(conversations_.begin(), conversations_.end(),
                               [&](const Conversation& c) { return c.peer() == msg.peer; });
        if (it == conversations_.end()) {
            conversations_.emplace_back(Conversation{msg.peer});
            conv_names_.push_back(msg.peer);
            it = conversations_.end() - 1;
        }
        it->add_message(msg);
    };
    if (screen_ptr_) screen_ptr_->Post(update);
    else             update();
}

void App::push_sent_message(const Message& msg) {
    auto update = [this, msg] {
        auto it = std::find_if(conversations_.begin(), conversations_.end(),
                               [&](const Conversation& c) { return c.peer() == msg.peer; });
        if (it == conversations_.end()) {
            conversations_.emplace_back(Conversation{msg.peer});
            conv_names_.push_back(msg.peer);
            it = conversations_.end() - 1;
        }
        it->add_message(msg);
    };
    if (screen_ptr_) screen_ptr_->Post(update);
    else             update();
}

void App::update_message_body(uint64_t id, const std::string& new_body) {
    auto update = [this, id, new_body] {
        for (auto& conv : conversations_)
            conv.update_message_body(id, new_body);
    };
    if (screen_ptr_) screen_ptr_->Post(update);
    else             update();
}

void App::update_message_body_by_mid(const std::string& mid, const std::string& new_body) {
    auto update = [this, mid, new_body] {
        for (auto& conv : conversations_)
            conv.update_message_body_by_mid(mid, new_body);
    };
    if (screen_ptr_) screen_ptr_->Post(update);
    else             update();
}

void App::mark_message_deleted(uint64_t id) {
    auto update = [this, id] {
        for (auto& conv : conversations_)
            conv.mark_message_deleted(id);
        selected_msg_     = -1;
        msg_options_open_ = false;
    };
    if (screen_ptr_) screen_ptr_->Post(update);
    else             update();
}

void App::mark_message_deleted_by_mid(const std::string& mid) {
    auto update = [this, mid] {
        for (auto& conv : conversations_)
            conv.mark_message_deleted_by_mid(mid);
    };
    if (screen_ptr_) screen_ptr_->Post(update);
    else             update();
}

void App::remove_message(uint64_t id) {
    auto update = [this, id] {
        for (auto& conv : conversations_)
            conv.remove_message(id);
        selected_msg_      = -1;
        msg_options_open_  = false;
    };
    if (screen_ptr_) screen_ptr_->Post(update);
    else             update();
}

void App::set_conversations(std::vector<Conversation> convs) {
    conversations_ = std::move(convs);
    conv_names_.clear();
    for (const auto& c : conversations_)
        conv_names_.push_back(c.peer());
    selected_conv_ = 0;
}

void App::advance_to_chat(std::string username) {
    local_username_ = std::move(username);
    active_screen_ = 1;
}

void App::return_to_login() {
    if (screen_ptr_) {
        screen_ptr_->Post([this] {
            conversations_.clear();
            conv_names_.clear();
            selected_conv_ = 0;
            compose_text_.clear();
            new_peer_.clear();
            local_username_.clear();
            status_msg_.clear();
            active_screen_ = 0;
        });
    } else {
        conversations_.clear();
        conv_names_.clear();
        selected_conv_ = 0;
        compose_text_.clear();
        new_peer_.clear();
        local_username_.clear();
        status_msg_.clear();
        active_screen_ = 0;
    }
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
    InputOption pwd_opt;
    pwd_opt.password = true;

    auto username_input = Input(&login_username_, "username");
    auto password_input = Input(&login_password_, "password", pwd_opt);
    auto key_pin_input  = Input(&login_key_pin_,  "6-digit PIN", pwd_opt);

    // Restrict PIN input to digits only, capped at 6 characters.
    key_pin_input = CatchEvent(key_pin_input, [&](Event e) {
        if (e.is_character()) {
            char c = e.character().empty() ? '\0' : e.character()[0];
            if (!std::isdigit(static_cast<unsigned char>(c))) return true;
            if (login_key_pin_.size() >= 6) return true;
        }
        return false;
    });

    auto login_btn = Button(" Login ", [&] {
        if (lockout_active_) return;
        if (login_username_.empty() || login_password_.empty() || login_key_pin_.empty()) return;
        if (cbs_.on_login) {
            cbs_.on_login(login_username_, login_password_, login_key_pin_);
        } else {
            advance_to_chat(login_username_);
        }
    }, ButtonOption::Ascii());

    auto register_btn = Button(" Register ", [&] {
        if (login_username_.empty() || login_password_.empty() || login_key_pin_.empty()) return;
        if (login_key_pin_.size() != 6) {
            push_status("Key PIN must be exactly 6 digits.");
            return;
        }
        if (cbs_.on_register) {
            cbs_.on_register(login_username_, login_password_, login_key_pin_);
        } else {
            advance_to_chat(login_username_);
        }
    }, ButtonOption::Ascii());

    auto login_form = Container::Vertical({
        username_input,
        password_input,
        key_pin_input,
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
                    hbox({text(" Password : "), password_input->Render() | flex}),
                    hbox({text(" Key PIN  : "), key_pin_input->Render()  | flex}),
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
    for (const auto& c : conversations_)
        conv_names_.push_back(c.peer());

    auto conv_menu = Menu(&conv_names_, &selected_conv_);

    auto add_conversation = [&] {
        if (new_peer_.empty()) return;
        auto it = std::find_if(conversations_.begin(), conversations_.end(),
                               [&](const Conversation& c) { return c.peer() == new_peer_; });
        if (it == conversations_.end()) {
            conversations_.emplace_back(Conversation{new_peer_});
            conv_names_.push_back(new_peer_);
            selected_conv_ = static_cast<int>(conversations_.size()) - 1;
        } else {
            selected_conv_ = static_cast<int>(std::distance(conversations_.begin(), it));
        }
        new_peer_.clear();
    };

    auto new_peer_input = Input(&new_peer_, "New chat...");
    new_peer_input = CatchEvent(new_peer_input, [&](Event e) {
        if (e == Event::Return) { add_conversation(); return true; }
        return false;
    });
    auto new_conv_btn = Button("+", add_conversation, ButtonOption::Ascii());
    auto left_panel   = Container::Vertical({conv_menu,
                                             Container::Horizontal({new_peer_input, new_conv_btn})});

    // compose_text_ serves three modes depending on editing_msg_ / forwarding_msg_:
    //   normal      → body of new message to send
    //   editing     → new body for the selected message
    //   forwarding  → recipient to forward to (body saved in forwarding_body_)
    auto do_send = [&] {
        if (compose_text_.empty()) return;
        if (editing_msg_) {
            if (cbs_.on_edit) cbs_.on_edit(editing_msg_id_, compose_text_);
            compose_text_     = "";
            editing_msg_      = false;
            editing_msg_id_   = 0;
            selected_msg_     = -1;
            msg_options_open_ = false;
        } else if (forwarding_msg_) {
            if (cbs_.on_forward) cbs_.on_forward(compose_text_, forwarding_body_);
            else if (cbs_.on_send) cbs_.on_send(compose_text_, forwarding_body_);
            compose_text_     = "";
            forwarding_msg_   = false;
            forwarding_body_  = "";
            selected_msg_     = -1;
            msg_options_open_ = false;
        } else {
            if (cbs_.on_send) {
                if (conversations_.empty()) return;
                cbs_.on_send(conversations_[selected_conv_].peer(), compose_text_);
                compose_text_.clear();
            } else {
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
        }
    };

    auto compose_input = Input(&compose_text_, "Type a message...");
    compose_input = CatchEvent(compose_input, [&](Event e) {
        if (e == Event::Return) { do_send(); return true; }
        if (e == Event::Escape && (editing_msg_ || forwarding_msg_)) {
            compose_text_    = "";
            editing_msg_     = false;
            forwarding_msg_  = false;
            editing_msg_id_  = 0;
            forwarding_body_ = "";
            return true;
        }
        if (e == Event::ArrowUp && compose_text_.empty() &&
                !editing_msg_ && !forwarding_msg_ && !conversations_.empty()) {
            const auto& msgs = conversations_[selected_conv_].messages();
            if (!msgs.empty()) {
                selected_msg_     = static_cast<int>(msgs.size()) - 1;
                msg_options_open_ = false;
            }
            return true;
        }
        return false;
    });

    auto send_btn = Button("Send", do_send, ButtonOption::Ascii());

    auto logout_btn = Button(" Logout ", [&] {
        if (cbs_.on_logout) cbs_.on_logout();
        else return_to_login();
    }, ButtonOption::Ascii());

    auto chat_right     = Container::Horizontal({compose_input, send_btn});
    auto chat_panels    = Container::Horizontal({left_panel, chat_right});
    auto chat_layout    = Container::Vertical({logout_btn, chat_panels});

    // Key navigation and options key-bindings for the whole chat area
    chat_layout = CatchEvent(chat_layout, [&](Event e) {
        if (conversations_.empty()) return false;
        const auto& msgs = conversations_[selected_conv_].messages();
        if (msgs.empty() || selected_msg_ < 0) return false;

        // Arrow navigation (only when not in edit/forward text mode)
        if (!editing_msg_ && !forwarding_msg_) {
            if (e == Event::ArrowUp) {
                selected_msg_ = std::max(0, selected_msg_ - 1);
                msg_options_open_ = false;
                return true;
            }
            if (e == Event::ArrowDown) {
                int last = static_cast<int>(msgs.size()) - 1;
                selected_msg_     = (selected_msg_ >= last) ? -1 : selected_msg_ + 1;
                msg_options_open_ = false;
                return true;
            }
            if (e == Event::Return) {
                msg_options_open_ = !msg_options_open_;
                return true;
            }
        }

        if (e == Event::Escape) {
            msg_options_open_ = false;
            selected_msg_     = -1;
            editing_msg_      = false;
            forwarding_msg_   = false;
            compose_text_     = "";
            editing_msg_id_   = 0;
            forwarding_body_  = "";
            return true;
        }

        // Option key-bindings (only when options menu is open)
        if (!msg_options_open_) return false;
        if (selected_msg_ >= static_cast<int>(msgs.size())) return false;
        const auto& sel  = msgs[selected_msg_];
        bool is_sent     = (sel.recipient != local_username_);

        if (e.is_character()) {
            char c = e.character().empty() ? '\0' : e.character()[0];
            if (c == 'e' || c == 'E') {
                if (is_sent && is_editable(sel.timestamp_ms, now_ms())) {
                    compose_text_     = sel.body;
                    editing_msg_      = true;
                    editing_msg_id_   = sel.id;
                    msg_options_open_ = false;
                } else if (is_sent) {
                    push_status("Edit window has closed for this message.");
                }
                return true;
            }
            if (c == 'd' || c == 'D') {
                if (is_sent) {
                    if (is_editable(sel.timestamp_ms, now_ms())) {
                        if (cbs_.on_delete) cbs_.on_delete(sel.id, false);
                    } else {
                        push_status("Delete window has closed for this message.");
                    }
                }
                msg_options_open_ = false;
                return true;
            }
            if (c == 'f' || c == 'F') {
                forwarding_body_  = sel.body;
                forwarding_msg_   = true;
                compose_text_     = "";
                msg_options_open_ = false;
                return true;
            }
            if (c == 'v' || c == 'V') {
                if (sel.mid.empty()) {
                    push_status("Cannot verify: message ID unavailable (message predates this feature).");
                    msg_options_open_ = false;
                    return true;
                }
                if (!sel.wire_ciphertext.empty()) {
                    // Payload matches the on-chain format: "{mid}:{full_envelope_JSON}"
                    // (mirrors daemons/batcher.py: f"{r.mid}:{r.ciphertext}")
                    const std::string payload = sel.mid + ":" + sel.wire_ciphertext;
                    std::string encoded;
                    for (unsigned char uc : payload) {
                        if (std::isalnum(uc) || uc=='-'||uc=='_'||uc=='.'||uc=='~')
                            encoded += static_cast<char>(uc);
                        else {
                            char buf[4];
                            std::snprintf(buf, sizeof(buf), "%%%02X", uc);
                            encoded += buf;
                        }
                    }
                    std::string url = "https://1bit2qbit.theburkenator.com/verify/?message=" + encoded;
#ifdef _WIN32
                    ShellExecuteA(nullptr, "open", url.c_str(), nullptr, nullptr, SW_SHOWNORMAL);
#else
                    std::system(("xdg-open '" + url + "' &").c_str());
#endif
                } else {
                    push_status("Cannot verify: no envelope stored for this message.");
                }
                msg_options_open_ = false;
                return true;
            }
        }
        return false;
    });

    auto chat_renderer = Renderer(chat_layout, [&]() -> Element {
        // ── Message list ──────────────────────────────────────────────────────
        Elements msg_els;
        if (!conversations_.empty()) {
            const auto& msgs = conversations_[selected_conv_].messages();
            for (int i = 0; i < static_cast<int>(msgs.size()); ++i) {
                const auto& m = msgs[i];
                // Use sender if set; fall back to recipient-based logic for old rows
                bool sent = m.sender.empty() ? (m.recipient != local_username_)
                                             : (m.sender == local_username_);
                bool sel  = (i == selected_msg_);
                std::string label = sent
                    ? "[" + format_time(m.timestamp_ms) + "] you : "
                    : "[" + format_time(m.timestamp_ms) + "] " + m.peer + " : ";
                auto row = hbox({
                    text(sel ? " > " : "   "),
                    text(label) | (sent ? color(Color::Blue) : color(Color::White)),
                    m.deleted ? (text("(deleted)") | dim | flex) : (text(m.body) | flex),
                    (!m.deleted && m.edited)              ? (text(" (edited)")    | dim) : text(""),
                    m.type == MessageType::Forward        ? (text(" (forwarded)") | dim) : text(""),
                });
                if (sel) row = row | inverted;
                msg_els.push_back(row);
            }
            if (!msg_els.empty())
                msg_els.back() = msg_els.back() | focus;
            else
                msg_els.push_back(text("No messages yet.") | dim | center);
        } else {
            msg_els.push_back(text("No messages yet.") | dim | center);
        }

        // ── Action / hint bar ─────────────────────────────────────────────────
        Element action_bar = text("");
        if (editing_msg_) {
            action_bar = text(" Editing — [Enter]=confirm  [Esc]=cancel") | color(Color::Yellow);
        } else if (forwarding_msg_) {
            action_bar = text(" Forward to (type recipient, Enter to send, Esc to cancel)") | color(Color::Yellow);
        } else if (selected_msg_ >= 0 && !conversations_.empty()) {
            const auto& msgs = conversations_[selected_conv_].messages();
            if (selected_msg_ < static_cast<int>(msgs.size())) {
                bool is_sent = (msgs[selected_msg_].recipient != local_username_);
                if (msg_options_open_) {
                    std::string hint = " Options:";
                    if (is_sent) {
                        bool in_window = is_editable(msgs[selected_msg_].timestamp_ms, now_ms());
                        hint += in_window ? "  [E]dit" : "  [E]dit(expired)";
                        hint += in_window ? "  [D]elete" : "  [D]elete(expired)";
                    }
                    hint += "  [F]orward  [V]erify  [Esc]=close";
                    action_bar = text(hint) | color(Color::Yellow);
                } else {
                    action_bar = text(" [Enter]=options  [↑↓]=navigate  [Esc]=deselect") | dim;
                }
            }
        }

        const std::string peer_title = conversations_.empty()
            ? "No conversations"
            : conversations_[selected_conv_].peer();

        Elements header_els = {
            text("  EPIC") | bold | color(Color::Cyan),
            text(" Secure Messenger") | color(Color::Cyan),
        };
        if (!connected_.load())
            header_els.push_back(text(" ● NO CONNECTION") | color(Color::Red) | bold);
        header_els.push_back(filler());
        header_els.push_back(text(" " + local_username_ + " ") | bold);
        header_els.push_back(logout_btn->Render());

        // ── Compose bar ───────────────────────────────────────────────────────
        std::string compose_label = editing_msg_     ? " Edit > "
                                  : forwarding_msg_  ? " Fwd to > "
                                  :                    " > ";
        Element compose_bar = hbox({
            text(compose_label) | (editing_msg_ || forwarding_msg_ ? color(Color::Yellow) : color(Color::White)),
            compose_input->Render() | flex,
            text(" "),
            send_btn->Render(),
        });

        return vbox({
            hbox(std::move(header_els)),
            separator(),
            hbox({
                vbox({
                    text(" Conversations") | bold,
                    separator(),
                    conv_menu->Render() | flex,
                    separator(),
                    hbox({
                        new_peer_input->Render() | flex,
                        new_conv_btn->Render(),
                    }),
                }) | border | size(WIDTH, EQUAL, 22),
                vbox({
                    text("  " + peer_title) | bold,
                    separator(),
                    yframe(vbox(msg_els)) | flex,
                    separator(),
                    action_bar,
                    separator(),
                    compose_bar,
                }) | border | flex,
            }) | flex,
        });
    });

    // ── Root ──────────────────────────────────────────────────────────────────
    auto root = Container::Tab(Components{login_renderer, chat_renderer}, &active_screen_);
    screen_ptr_ = &screen;

    std::atomic<bool> running{true};
    std::thread refresh_thread([&] {
        while (running.load()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            if (running.load())
                screen.PostEvent(Event::Custom);
        }
    });

    screen.Loop(root);
    screen_ptr_ = nullptr;
    running = false;
    lockout_quit_ = true;
    refresh_thread.join();
    if (lockout_thread_.joinable()) lockout_thread_.join();
}
