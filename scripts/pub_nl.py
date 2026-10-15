#!/usr/bin/env python3
"""发 NL 指令到指定话题
用法：python3 pub_nl.py "UAV 1, assemble at (15, 20, 5)" /drone1/nl_input
"""
import sys
import time

import rclpy
from std_msgs.msg import String


def main():
    text = sys.argv[1] if len(sys.argv) > 1 else 'UAV 1, assemble at (15, 20, 5)'
    topic = sys.argv[2] if len(sys.argv) > 2 else '/drone1/nl_input'
    rclpy.init()
    node = rclpy.create_node('pub_nl')
    pub = node.create_publisher(String, topic, 10)
    msg = String()
    msg.data = text
    for _ in range(3):
        pub.publish(msg)
        time.sleep(0.1)
    rclpy.shutdown()
    print('OK -> {}: {}'.format(topic, text))


if __name__ == '__main__':
    main()
