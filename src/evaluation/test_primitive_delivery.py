#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_primitive_delivery.py — /mission/primitive 送达回归测试

流程：
  1. 以与 mappo_policy_node 完全相同的 QoS（depth=10）订阅 /mission/primitive
  2. 以当前时间戳发布一条 HOLD@(0,0,5) 相位到 /cloud/phase
  3. 等 8s，报告是否收到原语
判定指挥节点->执行节点的送达链路是否正常。
"""
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Header, String

received = []


def main():
    rclpy.init()
    node = Node('primitive_delivery_probe')
    node.create_subscription(String, '/mission/primitive',
                             lambda m: received.append(m.data), 10)

    pub = node.create_publisher(Header, '/cloud/phase', 10)
    time.sleep(2.0)
    msg = Header()
    msg.frame_id = 'HOLD@(0,0,5)'
    msg.stamp.sec = int(time.time())
    msg.stamp.nanosec = 0
    pub.publish(msg)
    print('已发布相位 HOLD@(0,0,5) @', msg.stamp.sec)

    end = time.time() + 8.0
    while time.time() < end and not received:
        rclpy.spin_once(node, timeout_sec=0.2)

    if received:
        print('PASS 收到原语:', received[0][:120])
    else:
        print('FAIL 8 秒内未收到任何原语')
    node.destroy_node()
    rclpy.shutdown()
    raise SystemExit(0 if received else 1)


if __name__ == '__main__':
    main()
