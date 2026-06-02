#include "client/Client.h"
#include "log.h"

#include <CLI/CLI.hpp>

int main(int argc, char** argv) {
    CLI::App app{"EPIC Secure Messenger"};

    bool log_terminal = false;
    app.add_flag("--log-terminal", log_terminal, "Open a terminal window tailing the log file");

    CLI11_PARSE(app, argc, argv);

    if (log_terminal)
        open_log_terminal();

    Client{"1bit2qbit.theburkenator.com", 443}.run();
    return 0;
}
