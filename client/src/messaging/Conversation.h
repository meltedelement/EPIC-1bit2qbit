#pragma once
#include <string>
#include <vector>
#include "messaging/Message.h"

class Conversation {
public:
    explicit Conversation(std::string peer_username);

    void add_message(Message msg);

    const std::vector<Message>& messages()        const;
    const std::string&          peer()            const;

    // Double Ratchet state — opaque JSON blob owned by the C++ layer and passed
    // to the Python subprocess on every encrypt/decrypt call. Updated after each message.
    const std::string& ratchet_state()                    const;
    void               set_ratchet_state(std::string state);

    // Associated data produced by the X3DH exchange — passed to every DR call as AD.
    // Set once when the session is established; never changes for the lifetime of the conversation.
    const std::string& associated_data()                  const;
    void               set_associated_data(std::string ad);

    // TOFU-pinned long-term identity key for this peer (base64 IK_pub).
    // Set on first contact and verified on every subsequent message.
    const std::string& pinned_ik_pub()                    const;
    void               set_pinned_ik_pub(std::string ik_pub);

private:
    std::string          peer_;
    std::vector<Message> messages_;
    std::string          ratchet_state_;
    std::string          associated_data_;
    std::string          pinned_ik_pub_;
};
