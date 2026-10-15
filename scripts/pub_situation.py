#!/usr/bin/env python3
"""发态势到 /cloud/situation（触发云端相位切换）
用法：python3 pub_situation.py "enemy detected, assemble at (15, 20)"
"""
import sys
import time

import rclpy
from std_msgs.msg import String


def main():
    text = sys.argv[1] if len(sys.argv) > 1 else 'enemy detected, assemble immediately at (15, 20)'
    rclpy.init()
    node = rclpy.create_node('pub_situation')
    pub = node.create_publisher(String, '/cloud/situation', 10)
    msg = String()
    msg.data = text
    for _ in range(3):
        pub.publish(msg)
        time.sleep(0.1)
    rclpy.shutdown()
    print('OK:', text)


if __name__ == '__main__':
    main()
