#!/usr/bin/env python3
"""cloud_heartbeat_node - 模拟云端相位规划器的心跳与相位信号

对应创新点3（断连降级机制）的"云端侧"：
  - 每秒发布心跳到 /cloud/heartbeat（含时间戳和当前相位）
  - 心跳存在 = 云-边链路正常；心跳消失 = 断连
  - 停止本节点即可模拟通信中断

用法：
  ros2 run nl_command cloud_heartbeat_node              # 正常心跳
  Ctrl+C 停止 = 模拟断连
  重新启动 = 模拟恢复
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import Header
from builtin_interfaces.msg import Time as TimeMsg


class CloudHeartbeatNode(Node):

    def __init__(self):
        super().__init__('cloud_heartbeat')
        # 心跳频率 1Hz（导师方案中云端是"低频"相位规划）
        self.hb_pub = self.create_publisher(Header, '/cloud/heartbeat', 10)
        self.phase_pub = self.create_publisher(Header, '/cloud/phase', 10)
        self.timer = self.create_timer(1.0, self.publish_heartbeat)
        self.beat_count = 0
        # 模拟的云端当前相位（实际系统由云端LLM根据态势生成）
        self.current_phase = 'HOLD@(0,0,5)'
        self.get_logger().info(
            '云端心跳节点就绪 [1Hz]，当前相位: %s' % self.current_phase)

    def publish_heartbeat(self):
        self.beat_count += 1
        msg = Header()
        now = self.get_clock().now().to_msg()
        msg.stamp = now
        msg.frame_id = 'beat_%d' % self.beat_count
        self.hb_pub.publish(msg)

        # 相位信号（低频：每10拍发一次，模拟云端低频规划）
        if self.beat_count % 10 == 1:
            pmsg = Header()
            pmsg.stamp = now
            pmsg.frame_id = self.current_phase
            self.phase_pub.publish(pmsg)

        if self.beat_count % 30 == 0:
            self.get_logger().info(
                '心跳 #d=%d, 相位=%s' % (self.beat_count, self.current_phase))


def main(args=None):
    rclpy.init(args=args)
    node = CloudHeartbeatNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
