#!/usr/bin/env python3
"""cloud_phase_generator - 云端相位规划器

对应创新点1"云端LLM低频生成相位信号"：
  - 订阅 /cloud/situation（态势文本，String）
  - 相位推断引擎可切换（ROS 参数 llm_provider 或环境变量 CLOUD_LLM_PROVIDER）：
      rule      规则引擎（关键词匹配，默认，无外部依赖）
      deepseek  DeepSeek API（云端大模型，研究主线）
      glm       智谱 GLM API（备选/横向对比）
      local     本地 llama.cpp server（用端侧模型模拟云端，对照组）
  - 发布 /cloud/phase（如 "OBSTACLE_AVOID@left@30"，Header.frame_id 承载）
  - 发布 /cloud/heartbeat（1Hz）

与端侧的通信量对比（创新点1核心价值）：
  - 全态势文本：100-200 token
  - 相位信号：10-15 token（压缩一个量级）

可靠性设计（论文开销审计的云端数据来源）：
  - LLM 推断在后台工作线程执行，绝不阻塞 1Hz 心跳定时器
    （若在回调里同步调用，秒级 LLM 延迟会让端侧 3 秒心跳超时误判 DEGRADED）
  - LLM 输出经完整语法校验（phase_rules.validate_phase，与端侧解析同一契约），
    非法输出带错误反馈重试 1 次，仍失败回退规则引擎（断网时云端节点不死）
  - 每次调用落盘 JSONL 统计（延迟/token 用量/解析阶段/是否回退），
    每 20 次输出一次汇总日志，节点退出时输出总结

用法（WSL2，需先复制到 px4_ws 并 colcon build，见 README）：
  # 规则模式（默认，回归验证旧行为）
  ros2 run nl_command cloud_phase_generator
  # DeepSeek 模式（key 只走环境变量，不进 ROS 参数避免落入日志）
  CLOUD_LLM_PROVIDER=deepseek DEEPSEEK_API_KEY=sk-xxx \
      ros2 run nl_command cloud_phase_generator
  # ROS 参数覆盖（provider/base_url/model/timeout 均可）
  ros2 run nl_command cloud_phase_generator --ros-args -p llm_provider:=glm
"""

import json
import os
import queue
import sys
import threading
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Header

try:
    from .phase_rules import (DEFAULT_PHASE, PHASE_PROMPT, llm_infer_phase,
                              rule_infer)
except ImportError:  # 直接以脚本方式运行（python3 cloud_phase_generator.py）
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from phase_rules import (DEFAULT_PHASE, PHASE_PROMPT, llm_infer_phase,
                             rule_infer)

# provider 预设（base_url / 默认模型 / API key 的环境变量名）
PROVIDERS = {
    'deepseek': {
        'base_url': 'https://api.deepseek.com/v1',
        'model': 'deepseek-chat',        # 换 deepseek-reasoner 需调大 llm_max_tokens
        'key_env': 'DEEPSEEK_API_KEY',
    },
    'glm': {
        'base_url': 'https://open.bigmodel.cn/api/paas/v4',
        'model': 'glm-4-flash',          # 免费档；对比可换 glm-4-plus
        'key_env': 'GLM_API_KEY',
    },
    'local': {
        'base_url': 'http://172.21.112.1:8080/v1',   # Windows 宿主机 llama.cpp server
        'model': 'phi2-phased-v5-q5_k_m.gguf',
        'key_env': None,                 # 本地 server 无需鉴权
    },
}


def _percentile(sorted_vals, q):
    """最近邻法百分位（样本量小，够用且无依赖）。"""
    if not sorted_vals:
        return 0.0
    idx = int(round(q * (len(sorted_vals) - 1)))
    return sorted_vals[idx]


class CloudPhaseGenerator(Node):

    def __init__(self):
        super().__init__('cloud_phase_generator')

        # ---- 配置：ROS 参数优先，环境变量兜底；API key 只走环境变量 ----
        self.declare_parameter(
            'llm_provider', os.environ.get('CLOUD_LLM_PROVIDER', 'rule'))
        self.declare_parameter('llm_base_url', '')    # 空 = 用 provider 预设
        self.declare_parameter('llm_model', '')       # 空 = 用 provider 预设
        self.declare_parameter('llm_timeout', 20.0)
        self.declare_parameter('llm_max_tokens', 64)
        self.declare_parameter('llm_temperature', 0.0)
        self.declare_parameter('llm_fallback_rule', True)
        self.declare_parameter(
            'stats_file',
            os.path.join(os.path.expanduser('~'), 'cloud_llm_stats.jsonl'))

        provider = str(self.get_parameter('llm_provider').value).strip().lower()
        if provider == 'true':  # 兼容旧常量 USE_LLM=True 的用法
            provider = 'deepseek'
        if provider != 'rule' and provider not in PROVIDERS:
            self.get_logger().error(
                '未知 llm_provider: %s（可选 rule/%s），回退 rule'
                % (provider, '/'.join(PROVIDERS)))
            provider = 'rule'
        self._provider = provider

        preset = PROVIDERS.get(provider, {})
        self._base_url = (str(self.get_parameter('llm_base_url').value).strip()
                          or preset.get('base_url', ''))
        self._model = (str(self.get_parameter('llm_model').value).strip()
                       or preset.get('model', ''))
        self._timeout = float(self.get_parameter('llm_timeout').value)
        self._max_tokens = int(self.get_parameter('llm_max_tokens').value)
        self._temperature = float(self.get_parameter('llm_temperature').value)
        self._fallback_rule = bool(self.get_parameter('llm_fallback_rule').value)
        self._stats_file = str(self.get_parameter('stats_file').value)

        self._api_key = os.environ.get('CLOUD_LLM_API_KEY', '')
        key_env = preset.get('key_env')
        if not self._api_key and key_env:
            self._api_key = os.environ.get(key_env, '')

        # ---- 话题（与旧版完全一致，端侧零改动） ----
        self._situation_sub = self.create_subscription(
            String, '/cloud/situation', self._on_situation, 10)
        self._phase_pub = self.create_publisher(Header, '/cloud/phase', 10)
        self._hb_pub = self.create_publisher(Header, '/cloud/heartbeat', 10)

        self._current_phase = DEFAULT_PHASE  # 初始默认
        self._lock = threading.Lock()

        # 心跳 1Hz
        self._hb_timer = self.create_timer(1.0, self._publish_heartbeat)
        # 相位低频重发（0.2Hz，每5秒重发一次当前相位）
        self._phase_timer = self.create_timer(5.0, self._republish_phase)

        self._beat_count = 0
        self._call_count = 0
        self._latencies = []
        self._stats_lock = threading.Lock()

        # 推断工作线程：LLM 调用秒级延迟不能阻塞心跳定时器
        self._sit_queue = queue.Queue()
        self._stop = threading.Event()
        self._worker = threading.Thread(
            target=self._infer_worker, name='phase_infer', daemon=True)
        self._worker.start()

        self.get_logger().info(
            '云端相位规划器就绪 | provider=%s model=%s url=%s | 初始相位: %s'
            % (self._provider, self._model or '-', self._base_url or '-',
               self._current_phase))
        if self._provider != 'rule':
            self.get_logger().info(
                'API key: %s | 兜底规则: %s | 统计文件: %s'
                % ('已配置' if self._api_key or self._provider == 'local' else
                   '缺失（将全部回退规则）', self._fallback_rule,
                   self._stats_file))
        self.get_logger().info('等待态势输入: ros2 topic pub /cloud/situation ...')

    # ------------------------------------------------------------------
    # 推断主链
    # ------------------------------------------------------------------

    def _on_situation(self, msg: String):
        """收到态势文本 → 入队（异步），回调立即返回，心跳不受影响。"""
        situation = msg.data.strip()
        if not situation:
            return
        self.get_logger().info('[态势] %s' % situation[:80])
        self._sit_queue.put(situation)

    def _infer_worker(self):
        while not self._stop.is_set():
            try:
                situation = self._sit_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            phase, info = self._infer(situation)
            if phase:
                with self._lock:
                    self._current_phase = phase
                self._publish_phase(phase)
                engine = info.get('engine', self._provider)
                self.get_logger().info(
                    '[云端→端侧] 相位信号: %s（engine=%s, %.0fms）'
                    % (phase, engine, info.get('total_latency_ms', 0.0)))
            else:
                self.get_logger().warn(
                    '相位推断失败，维持: %s' % self._current_phase)
            self._record_stats(situation, phase, info)

    def _infer(self, situation):
        """按 provider 分派：rule 直接推断；LLM 失败可回退规则。"""
        if self._provider == 'rule':
            return rule_infer(situation), {'engine': 'rule'}

        phase, info = llm_infer_phase(
            self._base_url, self._model, self._api_key, situation,
            timeout=self._timeout, max_tokens=self._max_tokens,
            temperature=self._temperature)
        info['engine'] = self._provider
        info['total_latency_ms'] = sum(info.get('latencies_ms', []))
        if info.get('errors'):
            self.get_logger().error(
                'LLM 调用失败: %s' % '; '.join(info['errors'])[:200])

        if phase:
            return phase, info
        if self._fallback_rule:
            phase = rule_infer(situation)
            info['fallback'] = True
            self.get_logger().warn(
                '[LLM→规则兜底] LLM 未产出合法相位，规则引擎接管: %s' % phase)
            return phase, info
        return None, info

    # ------------------------------------------------------------------
    # 统计落盘（E7 风格的云端开销审计）
    # ------------------------------------------------------------------

    def _record_stats(self, situation, phase, info):
        record = {
            'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'engine': info.get('engine', self._provider),
            'model': self._model,
            'phase': phase or '',
            'parse_stage': info.get('parse_stage', 'none'),
            'attempts': info.get('attempts', 0),
            'latencies_ms': info.get('latencies_ms', []),
            'total_latency_ms': round(info.get('total_latency_ms', 0.0), 1),
            'prompt_tokens': info.get('prompt_tokens', 0),
            'completion_tokens': info.get('completion_tokens', 0),
            'fallback': bool(info.get('fallback', False)),
            'errors': info.get('errors', [])[:3],
            'situation': situation[:80],
        }
        try:
            with open(self._stats_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
        except OSError as e:
            self.get_logger().warn('统计落盘失败: %s' % e)

        with self._stats_lock:
            self._call_count += 1
            if record['total_latency_ms']:
                self._latencies.append(record['total_latency_ms'])
            if self._call_count % 20 == 0:
                self._log_summary()

    def _log_summary(self):
        lat = sorted(self._latencies)
        if not lat:
            return
        mean = sum(lat) / len(lat)
        self.get_logger().info(
            '[统计] %d 次推断 | 延迟 mean=%.0fms p95=%.0fms max=%.0fms'
            % (self._call_count, mean, _percentile(lat, 0.95), lat[-1]))

    # ------------------------------------------------------------------
    # 发布（话题契约不变）
    # ------------------------------------------------------------------

    def _publish_phase(self, phase: str):
        msg = Header()
        msg.stamp = self.get_clock().now().to_msg()
        msg.frame_id = phase
        self._phase_pub.publish(msg)

    def _republish_phase(self):
        """低频重发当前相位（保持端侧缓存新鲜）。"""
        with self._lock:
            phase = self._current_phase
        self._publish_phase(phase)

    def _publish_heartbeat(self):
        self._beat_count += 1
        msg = Header()
        msg.stamp = self.get_clock().now().to_msg()
        msg.frame_id = 'beat_%d' % self._beat_count
        self._hb_pub.publish(msg)

    def destroy_node(self):
        self._stop.set()
        if self._call_count:
            self.get_logger().info(
                '[退出总结] 共 %d 次推断' % self._call_count)
            self._log_summary()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = CloudPhaseGenerator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
