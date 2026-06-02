#include <CLI/CLI.hpp>
#include "client/Client.h"

int main(int argc, char* argv[]) {
    CLI::App app{"EPIC secure messaging client"};

    std::string host = "localhost";
    uint16_t    port = 8443;

    app.add_option("--host", host, "Server hostname");
    app.add_option("--port", port, "Server port");

    CLI11_PARSE(app, argc, argv);

    Client client{host, port};
    client.run();
    return 0;
}
