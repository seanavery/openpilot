#include <iostream>
#include <csignal>
#include <unistd.h>
#include <memory>
#include <cstdlib>

#include "messaging/messaging.h"
#include "ch340.h"

void signalHandler(int signum) {
    std::cout << "Interrupt signal (" << signum << ") received." << std::endl;
    exit(signum);
}

int main(int argc, char *argv[]) {
    setenv("ZMQ", "1", 1);
    int err = 0;
    if (argc < 4) {
        // usage product vendor
        std::cout << "usage: ./arduinod <vendor> <product> <ip>" << std::endl;
        return -1;
    }

    // exit handler
    signal(SIGINT, signalHandler);

    // connect to usb device
    CH340 mcu;
    int vendor = std::stoul(argv[1], nullptr, 16);
    int product = std::stoul(argv[2], nullptr, 16);
    std::string ip = argv[3];
    std::cout << "product: " << product << std::endl;
    std::cout << "vendor: " << vendor << std::endl;
    err = mcu.init_usb(vendor, product);
    if (err != 0) {
        std::cout << "mcu init error" << std::endl;
        return -1;
    }

    // usleep(10000);

    // create subscriber
    std::cout << "creating subsocket" << std::endl << "connecting to pubsocket" << std::endl;
    Context *context = Context::create();
    SubSocket *sub = SubSocket::create(context, "controlsMsg", ip, true, true);;
    AlignedBuffer aligned_buf;

    while(1) {
        usleep(20000); // 50 hz loop

        std::unique_ptr<Message> msg(sub->receive());
        if (!msg) {
            std::cout << "no message" << std::endl;
            continue;
        }

        // parse zmq message into ControlsMsg type
        capnp::FlatArrayMessageReader cmsg(aligned_buf.align(msg.get()));
        cereal::Event::Reader event = cmsg.getRoot<cereal::Event>();
        auto controlsMsg = event.getControlsMsg();

        std::vector<unsigned char *> packets;

        if (controlsMsg.hasSteering()) {
            const capnp::Data::Reader& steeringData = controlsMsg.getSteering();
            const unsigned char *steering = reinterpret_cast<const unsigned char*>(steeringData.asBytes().begin());
            std::cout << "steering: " << steering << std::endl;
            packets.push_back((unsigned char *)steering);
        }

        if (controlsMsg.hasThrottle()) {
            const capnp::Data::Reader& throttleData = controlsMsg.getThrottle();
            const unsigned char *throttle = reinterpret_cast<const unsigned char*>(throttleData.asBytes().begin());
            std::cout << "throttle: " << throttle << std::endl;
            packets.push_back((unsigned char *)throttle);
        }

        // send packets to MCU one at a time
        for (auto packet : packets) {
            std::cout << "packet: " << packet << std::endl;
            // send packet
            err = mcu.bulk_write(EP_DATA_OUT, packet, 5, 100);
            if (err < 0) {
                std::cout << "bulk_write error" << std::endl;
            }
        }
    }

    return 0;
}