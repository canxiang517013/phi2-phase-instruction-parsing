#!/usr/bin/env python3
"""send_nl.py - 用 Python 直接发布自然语言指令（绕过损坏的 ros2 topic pub）

用法：
  python3 send_nl.py "UAV 1 fly to 10 0 5"              # 默认话题 /nl_input
  python3 send_nl.py "UAV 2 fly to 0 10 3" /nl_input2   # 指定话题
"""
import sys
import time
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


def main():
    text = sys.argv[1] if len(sys.argv) > 1 else 'UAV 1 fly to 10 20 5'
    topic = sys.argv[2] if len(sys.argv) > 2 else '/nl_input'

    rclpy.init()
    node = Node('nl_sender')
    pub = node.create_publisher(String, topic, 10)
    # 等 2 秒让 DDS 发现完成
    time.sleep(2)
    for i in range(3):
        msg = String()
        msg.data = text
        pub.publish(msg)
        print('published to %s: %s' % (topic, text))
        time.sleep(1.5)
    print('指令已发送')
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
