#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mission_commander_node - P0-4 任务指挥节点（边缘 SLM，不连接 PX4）

职责：自然语言指令 + 云端相位上下文 → Phi-2 → 确定性安全层 → 任务原语。
只发布 /mission/primitive（String JSON），由 mappo_policy_node 执行，
避免出现两个节点争夺 PX4 setpoint 的问题。

原语格式：
  {"type": "LEADER_TARGET", "target": [x, y], "alt_note": z, ...}
  {"type": "HOLD"}            冻结虚拟 leader
  {"type": "RESUME"}          解除冻结
  {"type": "RECONFIGURE", "formation": "line|column|circle"}

翻译规则（确定性，无 LLM 参与）：
  - 安全层拒绝 → 不发任何原语（保持当前任务），落盘日志
  - 相位为 HOLD（链路新鲜）→ HOLD 原语（云端优先）
  - 相位为 RECONFIGURE 且 SLM 一致 → RECONFIGURE 原语
  - 其余被接受的动作（含 target）→ LEADER_TARGET（x,y；z 仅记录）

SLM 调用、提示词与安全层契约与 nl_command_node 完全一致
（INSTR_BASE 复制自该节点；后续统一抽到 common/slm_client）。
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSDurabilityPolicy, QoSReliabilityPolicy
from std_msgs.msg import Header, String

try:
    from uav_adversarial.common.safety_layer import SafetyLayer, parse_phase
    from uav_adversarial.edge.p04_link import DEGRADED, FRESH, P04Link
except ImportError:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'common'))
    sys.path.insert(0, _HERE)
    from safety_layer import SafetyLayer, parse_phase  # type: ignore
    from p04_link import DEGRADED, FRESH, P04Link  # type: ignore

# 与 nl_command_node 相同（复制，避免 import 该节点连带 px4_msgs）
INSTR_BASE = 'Parse the user natural language command into a structured JSON for UAV DMPC.'
ALLOWED_HOSTS = {'172.21.112.1', '127.0.0.1', 'localhost', '172.21.112.162'}


def validate_base_url(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'http' or parts.hostname not in ALLOWED_HOSTS:
        raise ValueError('phi2_base_url 非法（仅允许 http + %s）: %r'
                         % sorted(ALLOWED_HOSTS), url)
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # 拒绝一切重定向


_OPENER = urllib.request.build_opener(_NoRedirect)


class MissionCommanderNode(Node):

    def __init__(self):
        super().__init__('mission_commander_node')
        self.declare_parameter('phi2_base_url', 'http://172.21.112.1:8080/v1')
        self.declare_parameter('phi2_model', 'phi2-phased-v5-q5_k_m.gguf')
        self.declare_parameter('nl_topic', '/nl_input')
        self.declare_parameter('phase_topic', '/cloud/phase')
        self.declare_parameter('heartbeat_topic', '/cloud/heartbeat')
        self.declare_parameter('primitive_topic', '/mission/primitive')
        self.declare_parameter('log_file', '/tmp/mission_commander.jsonl')

        self.base_url = validate_base_url(str(self.get_parameter('phi2_base_url').value))
        self.model = str(self.get_parameter('phi2_model').value)
        self.log_path = Path(str(self.get_parameter('log_file').value))

        self.link = P04Link(self.get_logger().info)
        self.safety = SafetyLayer()
        self._processing = False

        latched = QoSProfile(depth=1,
                              durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
                              reliability=QoSReliabilityPolicy.RELIABLE)
        self._prim_pub = self.create_publisher(
            String, str(self.get_parameter('primitive_topic').value), latched)
        self.create_subscription(
            String, str(self.get_parameter('nl_topic').value), self._on_nl, 10)
        self.create_subscription(
            Header, str(self.get_parameter('phase_topic').value),
            self._on_phase, 10)
        self.create_subscription(
            Header, str(self.get_parameter('heartbeat_topic').value),
            self._on_heartbeat, 10)

        self._log_fh = self.log_path.open('a', encoding='utf-8')
        self._emit('node_start', base_url=self.base_url, model=self.model)
        self.get_logger().info('任务指挥节点就绪: Phi-2=%s model=%s'
                               % (self.base_url, self.model))

    # ------------------------------------------------------------------
    def _emit(self, event, **kw):
        rec = {'t': round(time.time(), 3), 'event': event}
        rec.update(kw)
        self._log_fh.write(json.dumps(rec, ensure_ascii=False, default=str) + '\n')
        self._log_fh.flush()
        self.get_logger().info('[%s] %s' % (event, json.dumps(kw, default=str)[:160]))

    def _now(self):
        return time.time()

    def _on_heartbeat(self, msg: Header):
        self.link.on_heartbeat(self._now(), msg.frame_id)

    def _on_phase(self, msg: Header):
        stamp_s = msg.stamp.sec + msg.stamp.nanosec * 1e-9
        verdict = self.link.on_phase(msg.frame_id, stamp_s, self._now())
        if verdict != 'accepted':
            return
        # 云端低频重发同一相位（0.2Hz）：仅在相位变化时派生原语，避免刷屏
        if msg.frame_id == getattr(self, '_last_phase_emitted', None):
            return
        # 相位派生原语（确定性，不经 SLM）：HOLD 冻结 / RECONFIGURE 换几何。
        # 目标类相位（ASSEMBLE/RECON 的坐标）不直接透传——目标必须经
        # NL→SLM→安全层的数值溯源链（P0-2 结论：无溯源的数值即捏造）。
        parsed = parse_phase(msg.frame_id)
        if not parsed:
            return
        ptype = parsed.get('type')
        if ptype == 'HOLD':
            prim = {'type': 'HOLD', 'source': 'phase', 'phase': msg.frame_id}
        elif ptype == 'RECONFIGURE':
            prim = {'type': 'RECONFIGURE', 'source': 'phase',
                    'phase': msg.frame_id,
                    'formation': parsed.get('formation')}
        else:
            self._last_phase_emitted = msg.frame_id
            return
        self._last_phase_emitted = msg.frame_id
        self._publish_primitive(prim)
        self._emit('primitive', **prim)

    def _on_nl(self, msg: String):
        if self._processing:
            self.get_logger().info('已有指令在处理中，忽略')
            return
        self._processing = True
        threading.Thread(target=self._process_nl, args=(msg.data,), daemon=True).start()

    # ------------------------------------------------------------------
    def _query_slm(self, text):
        nl = chr(10)
        if self.link.state == FRESH and self.link.phase:
            instruction = 'Phase: %s. %s' % (self.link.phase, INSTR_BASE)
        else:
            instruction = INSTR_BASE
        prompt = ('### System:' + nl + instruction + nl + nl +
                  '### User:' + nl + text + nl + nl +
                  '### Response:' + nl)
        payload = json.dumps({
            'model': self.model, 'prompt': prompt,
            'temperature': 0.1, 'max_tokens': 64,
            'stop': ['<|endoftext|>', nl + '###'],
        }).encode('utf-8')
        req = urllib.request.Request(
            self.base_url + '/completions', data=payload,
            headers={'Content-Type': 'application/json'}, method='POST')
        t0 = time.time()
        with _OPENER.open(req, timeout=15) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        return result['choices'][0]['text'].strip(), round((time.time() - t0) * 1000, 1)

    def _publish_primitive(self, payload: dict):
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self._prim_pub.publish(msg)

    def _process_nl(self, text):
        text = text.strip()
        self._emit('nl_input', text=text)
        try:
            content, latency_ms = self._query_slm(text)
        except Exception as e:
            self._emit('slm_error', error=str(e)[:200])
            self._processing = False
            return
        self._emit('slm_raw', prompt_phase=self.link.phase, raw=content,
                   latency_ms=latency_ms)

        phase_label = self.link.phase if self.link.state == FRESH else None
        accepted, action, reason = self.safety.check(content, text, phase_label)
        self._emit('safety', accepted=accepted, reason=reason,
                   action=action, raw=content)
        if not accepted:
            self.get_logger().warn('[安全层·拒绝] %s → 不发原语，保持当前任务' % reason)
            self._processing = False
            return

        ptype, formation, target = None, None, None
        if phase_label:
            parsed = parse_phase(phase_label)
            if parsed:
                ptype = parsed.get('type')
                formation = parsed.get('formation')

        common = {'nl': text, 'phase': phase_label, 'slm_latency_ms': latency_ms,
                  'source': 'mission_commander',
                  'mode': action.get('mode'), 'uav_ids': action.get('uav_ids')}

        if ptype == 'HOLD':
            prim = dict(common, type='HOLD')
        elif ptype == 'RECONFIGURE' and action.get('formation') == formation:
            prim = dict(common, type='RECONFIGURE', formation=formation)
        else:
            x, y, z = [float(v) for v in action['target']]
            prim = dict(common, type='LEADER_TARGET', target=[x, y], alt_note=z)

        self._publish_primitive(prim)
        self._emit('primitive', **prim)
        self._processing = False

    def destroy_node(self):
        try:
            self._log_fh.close()
        except Exception:
            pass
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = MissionCommanderNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
