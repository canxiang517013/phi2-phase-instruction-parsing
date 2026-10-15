#!/usr/bin/env python3
"""phase_rules - 相位语法校验、规则引擎、LLM 调用的共享库（纯 stdlib，无 ROS 依赖）

被两侧共用，保证"云端校验"与"端侧解析"是同一份契约：
  - cloud_phase_generator.py（WSL2 ROS 节点）
  - phase_consistency_eval.py（Windows 离线评测，规则引擎 vs LLM 一致性）

相位语法契约（与端侧 nl_command_node._parse_cached_phase_target 精确对齐）：
  ASSEMBLE@(x,y)              端侧解析为 [x, y, 5.0]
  HOLD@(x,y,z)                端侧解析为 [x, y, z]
  RECONFIGURE@<formation>     formation ∈ column/circle/grid/wedge/line
  OBSTACLE_AVOID@left@N       端侧解析为 [-N, 0.0, 15.0]
  OBSTACLE_AVOID@right@N      端侧解析为 [N, 0.0, 15.0]
  RECON@(x,y)                 端侧解析为 [x, y, 15.0]

端侧对非法格式静默忽略（返回 None → 安全悬停），因此云端必须在发布前完成
完整语法校验，不能只查前缀（旧实现的缺陷：OBSTACLE_AVOID@up@30 能过云端但被
端侧丢弃）。

自检：python phase_rules.py --selftest
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request

DEFAULT_PHASE = 'HOLD@(0,0,5)'

FORMATION_NAMES = ('column', 'circle', 'grid', 'wedge', 'line')

_NUM = r'-?\d+(?:\.\d+)?'
PHASE_PATTERNS = (
    re.compile(r'^ASSEMBLE@\(%s,%s\)$' % (_NUM, _NUM)),
    re.compile(r'^HOLD@\(%s,%s,%s\)$' % (_NUM, _NUM, _NUM)),
    re.compile(r'^RECONFIGURE@(column|circle|grid|wedge|line)$'),
    re.compile(r'^OBSTACLE_AVOID@(?:left|right)@%s$' % _NUM),
    re.compile(r'^RECON@\(%s,%s\)$' % (_NUM, _NUM)),
    # 对抗相位（红蓝分队博弈）
    re.compile(r'^PURSUE@\(%s,%s\)$' % (_NUM, _NUM)),
    re.compile(r'^INTERCEPT@\(%s,%s,%s\)$' % (_NUM, _NUM, _NUM)),
    re.compile(r'^EVADE@\(%s,%s\)$' % (_NUM, _NUM)),
    re.compile(r'^DEFEND_ZONE@\(%s,%s,%s\)$' % (_NUM, _NUM, _NUM)),
    re.compile(r'^RETREAT@\(%s,%s\)$' % (_NUM, _NUM)),
    re.compile(r'^ENCIRCLE@\(%s,%s,%s\)$' % (_NUM, _NUM, _NUM)),
)


def validate_phase(phase):
    """完整语法校验：True 表示端侧一定能解析该相位字符串。"""
    if not phase or not isinstance(phase, str):
        return False
    return any(p.match(phase.strip()) for p in PHASE_PATTERNS)


def phase_type(phase):
    """相位类型（去参数），用于金标准的宽松匹配。

    OBSTACLE_AVOID@left@30 -> OBSTACLE_AVOID:left
    RECONFIGURE@wedge      -> RECONFIGURE:wedge
    ASSEMBLE@(12,-8)       -> ASSEMBLE
    """
    if not phase or '@' not in phase:
        return phase
    head, _, rest = phase.partition('@')
    if head == 'OBSTACLE_AVOID':
        side = rest.split('@')[0]
        return '%s:%s' % (head, side)
    if head == 'RECONFIGURE':
        return '%s:%s' % (head, rest)
    return head


def extract_phase(text):
    """从 LLM 原始输出提取候选相位：去 markdown 围栏、取第一行、去句尾句点。"""
    if not text:
        return ''
    line = text.strip().strip('`').strip()
    line = line.split('\n')[0].strip()
    return line.rstrip('.').strip()


def rule_infer(situation):
    """规则引擎：关键词→相位（自 cloud_phase_generator 迁出）。

    相对原版的唯一行为修正：RECONFIGURE 分支移到 RECON 之前——
    'reconfigure' 包含子串 'recon'，原分支顺序会把 "Reconfigure to column."
    误判为 RECON（评测 dry-run 发现的隐藏 bug，修复以保证规则基线不是稻草人）。

    局限（评测脚本会量化）：无 HOLD 分支（带参数的 HOLD 会回落默认值）、
    无关键词的隐式语义态势全部回落 HOLD@(0,0,5)。
    """
    s = situation.lower()
    nums = [float(v) for v in re.findall(r'-?\d+', s)]

    if any(k in s for k in ('obstacle', 'hazard', 'threat', 'danger',
                            'collision', 'evade', '紧急', '障碍', '威胁')):
        dist = next((int(n) for n in nums if 10 <= n <= 50), 30)
        if 'left' in s or '左' in s:
            return f'OBSTACLE_AVOID@left@{dist}'
        return f'OBSTACLE_AVOID@right@{dist}'
    if any(k in s for k in ('reconfigure', 'change formation', 'reshuffle',
                            '重构', '变换队形')):
        for form in FORMATION_NAMES:
            if form in s:
                return f'RECONFIGURE@{form}'
        return 'RECONFIGURE@line'
    if any(k in s for k in ('gather', 'assemble', 'rally', 'form up',
                            '集结', '集合', '编组')):
        x = int(nums[0]) if len(nums) >= 2 else 0
        y = int(nums[1]) if len(nums) >= 2 else 0
        return f'ASSEMBLE@({x},{y})'
    if any(k in s for k in ('recon', 'scout', 'investigate', 'observe',
                            '侦察', '前出')):
        x = int(nums[0]) if len(nums) >= 2 else 100
        y = int(nums[1]) if len(nums) >= 2 else 100
        return f'RECON@({x},{y})'
    return DEFAULT_PHASE


# ---------------------------------------------------------------------------
# LLM 推断（云端大模型路径，DeepSeek / GLM / 本地 llama.cpp server 通用）
# ---------------------------------------------------------------------------

PHASE_PROMPT = """You are the cloud-level phase planner of a UAV swarm.
Read the situation report and output exactly ONE phase signal for the edge side.

Phase grammar (the output must be one line matching exactly one of these):
- ASSEMBLE@(x,y)                      e.g. ASSEMBLE@(12,-8)
- HOLD@(x,y,z)                        e.g. HOLD@(0,0,5)
- RECONFIGURE@<formation>             formation: column/circle/grid/wedge/line
- OBSTACLE_AVOID@left@N or @right@N   N = lateral distance in meters (10-50)
- RECON@(x,y)                         e.g. RECON@(120,90)

Rules:
- Output ONE line only, uppercase, full words "left"/"right" (never L/R).
- Use coordinates and distances from the situation when given; otherwise pick sensible values (obstacle 25-35 m, altitude 3-15 m).
- When the situation implies a maneuver without naming it (downdraft ahead, regroup order, scouting request, formation tightening), infer the matching phase.

Examples:
Situation: Obstacle cluster detected 30 m ahead on the right flank.
Answer: OBSTACLE_AVOID@right@30
Situation: Radar shows a strong downdraft zone 25 m ahead; lateral detour to the left is advised.
Answer: OBSTACLE_AVOID@left@25
Situation: Command requests all units consolidate at checkpoint Bravo (12,-8) for the night.
Answer: ASSEMBLE@(12,-8)"""

RETRY_HINT = ('Invalid phase "%s". Reply with exactly ONE line matching the '
              'grammar: ASSEMBLE@(x,y) | HOLD@(x,y,z) | RECONFIGURE@<column/'
              'circle/grid/wedge/line> | OBSTACLE_AVOID@<left|right>@N | '
              'RECON@(x,y). Uppercase, full words "left"/"right", no other text.')


def chat_completion(base_url, model, messages, api_key=None,
                    timeout=20.0, max_tokens=64, temperature=0.0):
    """OpenAI 兼容 /chat/completions 调用（DeepSeek/GLM/本地 llama.cpp 通用）。

    返回 (content, usage, latency_ms)；usage 为 dict（本地 server 可能缺省为 {}）。
    网络错误 / HTTP 错误向上抛 RuntimeError，由调用方决定重试或降级。
    """
    payload = {
        'model': model,
        'messages': messages,
        'max_tokens': max_tokens,
        'stream': False,
    }
    # deepseek-reasoner 不支持 temperature 等采样参数，传入会报 400
    if 'reasoner' not in model:
        payload['temperature'] = temperature
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = 'Bearer %s' % api_key

    url = base_url.rstrip('/') + '/chat/completions'
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method='POST')
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        detail = ''
        try:
            detail = e.read().decode('utf-8', 'replace')[:300]
        except Exception:
            pass
        raise RuntimeError('HTTP %s: %s' % (e.code, detail)) from e
    latency_ms = (time.perf_counter() - t0) * 1000.0

    choices = body.get('choices') or [{}]
    content = choices[0].get('message', {}).get('content', '') or ''
    return content, (body.get('usage') or {}), latency_ms


def llm_infer_phase(base_url, model, api_key, situation,
                    timeout=20.0, max_tokens=64, temperature=0.0):
    """完整 LLM 推断链：调用 → 提取 → 完整语法校验 → 带错误反馈重试 1 次。

    返回 (phase 或 None, info dict)。info 字段：
      attempts / latencies_ms / prompt_tokens / completion_tokens /
      errors / parse_ok（first / after_retry / False）
    """
    messages = [
        {'role': 'system', 'content': PHASE_PROMPT},
        {'role': 'user', 'content': situation},
    ]
    info = {
        'attempts': 0,
        'latencies_ms': [],
        'prompt_tokens': 0,
        'completion_tokens': 0,
        'errors': [],
        'parse_ok': False,
    }

    for attempt in (1, 2):
        info['attempts'] = attempt
        try:
            content, usage, latency = chat_completion(
                base_url, model, messages, api_key,
                timeout=timeout, max_tokens=max_tokens, temperature=temperature)
        except Exception as e:
            info['errors'].append(str(e))
            continue
        info['latencies_ms'].append(round(latency, 1))
        info['prompt_tokens'] += usage.get('prompt_tokens', 0) or 0
        info['completion_tokens'] += usage.get('completion_tokens', 0) or 0

        phase = extract_phase(content)
        if validate_phase(phase):
            info['parse_ok'] = True
            info['parse_stage'] = 'first' if attempt == 1 else 'after_retry'
            return phase, info
        # 带错误反馈重试一次（提高格式 adherence，同时留下可统计的重试率）
        messages.append({'role': 'assistant', 'content': content})
        messages.append({'role': 'user', 'content': RETRY_HINT % phase})

    info.setdefault('parse_stage', 'failed')
    return None, info


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------

_SELFTEST_VALID = [
    'ASSEMBLE@(12,-8)',
    'ASSEMBLE@(0,0)',
    'ASSEMBLE@(-10.5,8)',
    'HOLD@(0,0,5)',
    'HOLD@(3,-2,7)',
    'RECONFIGURE@column',
    'RECONFIGURE@wedge',
    'OBSTACLE_AVOID@left@30',
    'OBSTACLE_AVOID@right@40',
    'OBSTACLE_AVOID@right@25.5',
    'RECON@(120,90)',
    'RECON@(-60,-40)',
]

_SELFTEST_INVALID = [
    '',                                  # 空
    'HOLD',                              # 无参数
    'assemble@(1,2)',                    # 小写
    'OBSTACLE_AVOID@L@30',               # 缩写方向（端侧 docstring 的坑）
    'OBSTACLE_AVOID@up@30',              # 非法方向
    'RECONFIGURE@diamond',               # 未知队形
    'RECONFIGURE@',                      # 空队形
    'ASSEMBLE@(12,)',                    # 参数缺失
    'ASSEMBLE@(12,-8',                   # 缺右括号
    'HOLD@(1,2)',                        # HOLD 少一维
    'RECON@(120,90,5)',                  # RECON 多一维
    'The phase is OBSTACLE_AVOID@left@30',  # 混入自然语言
    'OBSTACLE_AVOID@left@30m',           # 带单位
    'RECON@(120, 90)',                   # 带空格（从严：端侧虽能容忍，云端统一不发）
]

_SELFTEST_TYPE = [
    ('OBSTACLE_AVOID@left@30', 'OBSTACLE_AVOID:left'),
    ('OBSTACLE_AVOID@right@40', 'OBSTACLE_AVOID:right'),
    ('RECONFIGURE@wedge', 'RECONFIGURE:wedge'),
    ('ASSEMBLE@(12,-8)', 'ASSEMBLE'),
    ('HOLD@(0,0,5)', 'HOLD'),
]

_SELFTEST_RULE = [
    ('Obstacle detected 30 m ahead on the left side.', 'OBSTACLE_AVOID@left@30'),
    ('All units gather at rally point (15, 20).', 'ASSEMBLE@(15,20)'),
    ('Scout ahead to point (60, -40).', 'RECON@(60,-40)'),
    ('Change formation to wedge.', 'RECONFIGURE@wedge'),
    ('Reconfigure to column formation.', 'RECONFIGURE@column'),
    ('Nothing to report.', 'HOLD@(0,0,5)'),
]


def selftest():
    ok = True
    for s in _SELFTEST_VALID:
        if not validate_phase(s):
            print('[FAIL] 应为合法: %r' % s)
            ok = False
    for s in _SELFTEST_INVALID:
        if validate_phase(s):
            print('[FAIL] 应为非法: %r' % s)
            ok = False
    for s, want in _SELFTEST_TYPE:
        got = phase_type(s)
        if got != want:
            print('[FAIL] phase_type(%r) = %r, 期望 %r' % (s, got, want))
            ok = False
    for s, want in _SELFTEST_RULE:
        got = rule_infer(s)
        if got != want:
            print('[FAIL] rule_infer(%r) = %r, 期望 %r' % (s, got, want))
            ok = False
    if validate_phase('ASSEMBLE@(12,-8)') and not validate_phase('assembled@(1,2)'):
        pass  # 大小写敏感已覆盖
    print('[selftest] %s（%d 合法 + %d 非法 + %d 类型 + %d 规则）' %
          ('全部通过' if ok else '存在失败', len(_SELFTEST_VALID),
           len(_SELFTEST_INVALID), len(_SELFTEST_TYPE), len(_SELFTEST_RULE)))
    return 0 if ok else 1


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(selftest())
    print(__doc__)
