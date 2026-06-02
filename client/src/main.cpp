#include "client/Client.h"

int main() {
    Client{"localhost", 443}.run();
    return 0;
}
