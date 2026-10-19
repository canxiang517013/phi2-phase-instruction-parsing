#!/usr/bin/env python3
"""migrate_2d_to_3d.py — 将师兄的 2D experiment_core.py 转为 3D 版
一次性完成全部维度修改，输出 phase-aware-llm-meta-controller/src/experiment_core_3d.py

注意：该克隆目录被 .gitignore 忽略，只作本地迁移草稿。仓库中实际维护的版本是
src/training/experiment_core_3d.py，并在迁移结果上手工增加了训练所需的 CLI 参数
（--methods / --episodes / --device / --ollama-url / --llm-model）。重新运行本脚本
不会更新该文件，修改功能请直接编辑 src/training/experiment_core_3d.py。
"""
from pathlib import Path

SRC = Path(__file__).parent / "phase-aware-llm-meta-controller" / "src" / "experiment_core.py"
DST = Path(__file__).parent / "phase-aware-llm-meta-controller" / "src" / "experiment_core_3d.py"

s = SRC.read_text(encoding="utf-8")

# ═══════════════════════════════════════════════════════════════
# 1. 文件头注释
# ═══════════════════════════════════════════════════════════════
s = s.replace(
    'Revised multi-UAV MAPPO comparison experiment.',
    '3D multi-UAV MAPPO comparison experiment (extended from 2D).'
)

# ═══════════════════════════════════════════════════════════════
# 2. BASE_CFG 中的 3D 配置
# ═══════════════════════════════════════════════════════════════
s = s.replace(
    '    leader_start=[0.0, 0.0],\n    leader_target=[200.0, 200.0],',
    '    leader_start=[0.0, 0.0, 20.0],\n    leader_target=[200.0, 200.0, 25.0],'
)
s = s.replace(
    '    start_position_bounds=[-120.0, 120.0, -120.0, 120.0],',
    '    start_position_bounds=[-120.0, 120.0, -120.0, 120.0, 2.0, 80.0],'
)
s = s.replace(
    '    max_speed=15.0,',
    '    max_speed=15.0,\n    max_vertical_speed=8.0,\n    min_altitude=2.0,\n    max_altitude=80.0,'
)
s = s.replace(
    '    formation_threshold=20.0,',
    '    formation_threshold=25.0,'
)

# ═══════════════════════════════════════════════════════════════
# 3. FIXED_START_POSITIONS → 3D
# ═══════════════════════════════════════════════════════════════
s = s.replace(
    '''FIXED_START_POSITIONS = np.array(
    [[100.0, 100.0], [-100.0, 100.0], [-100.0, -100.0], [100.0, -100.0]],
    dtype=np.float32,
)''',
    '''FIXED_START_POSITIONS = np.array(
    [[100.0, 100.0, 10.0], [-100.0, 100.0, 10.0],
     [-100.0, -100.0, 10.0], [100.0, -100.0, 10.0]],
    dtype=np.float32,
)

# 3D tetrahedral formation offsets (normalized to unit sphere)
TETRAHEDRON_OFFSETS = np.array(
    [[ 1.0,  1.0,  1.0],
     [ 1.0, -1.0, -1.0],
     [-1.0,  1.0, -1.0],
     [-1.0, -1.0,  1.0]],
    dtype=np.float32,
) / np.sqrt(3.0)

def fibonacci_sphere(n: int) -> np.ndarray:
    """N points approximately uniform on a unit sphere."""
    pts = np.zeros((n, 3), dtype=np.float32)
    golden = np.pi * (3.0 - np.sqrt(5.0))
    for i in range(n):
        y = 1.0 - (i / max(n - 1, 1)) * 2.0
        r = np.sqrt(max(1.0 - y * y, 0.0))
        theta = golden * i
        pts[i] = [np.cos(theta) * r, np.sin(theta) * r, y]
    return pts'''
)

# ═══════════════════════════════════════════════════════════════
# 4. 环境类 3D 化
# ═══════════════════════════════════════════════════════════════

# 4.1 类名和 docstring
s = s.replace(
    'class MovingLeaderFormationEnv:\n    """Continuous 2-D moving-leader formation benchmark.',
    'class MovingLeaderFormationEnv3D:\n    """Continuous 3-D moving-leader formation benchmark.'
)

# 4.2 angles 初始化（删除 2D angles，使用 3D offsets）
s = s.replace(
    '        self.angles = np.linspace(0, 2 * np.pi, self.n, endpoint=False)',
    '        self.angles = np.linspace(0, 2 * np.pi, self.n, endpoint=False)  # kept for compat\n'
    '        if self.n == 4:\n'
    '            self.formation_offsets = TETRAHEDRON_OFFSETS.copy()\n'
    '        else:\n'
    '            self.formation_offsets = fibonacci_sphere(self.n)'
)

# 4.3 _build_nominal_start_positions：shape (n,2)→(n,3)
s = s.replace(
    '''            if arr.shape != (self.n, 2):
                raise ValueError(
                    f"start_positions must have shape {(self.n, 2)}, got {arr.shape}."
                )''',
    '''            if arr.shape != (self.n, 3):
                raise ValueError(
                    f"start_positions must have shape {(self.n, 3)}, got {arr.shape}."
                )'''
)
s = s.replace(
    '''        if self.n == 4:
            return FIXED_START_POSITIONS.copy()
        radius = max(100.0, 1.8 * float(self.cfg["formation_radius"]))
        phase_offset = np.pi / 4.0
        return np.stack(
            [
                radius
                * np.array(
                    [np.cos(a + phase_offset), np.sin(a + phase_offset)],
                    dtype=np.float32,
                )
                for a in self.angles
            ]
        ).astype(np.float32)''',
    '''        if self.n == 4:
            return FIXED_START_POSITIONS.copy()
        radius = max(100.0, 1.8 * float(self.cfg["formation_radius"]))
        return (radius * fibonacci_sphere(self.n)).astype(np.float32)'''
)

# 4.4 start_position_bounds：4 元→6 元
s = s.replace(
    '''        bounds = [float(x) for x in self.cfg["start_position_bounds"]]
        if len(bounds) != 4:
            raise ValueError("start_position_bounds must be [xmin, xmax, ymin, ymax].")
        xmin, xmax, ymin, ymax = bounds''',
    '''        bounds = [float(x) for x in self.cfg["start_position_bounds"]]
        if len(bounds) != 6:
            raise ValueError("start_position_bounds must be [xmin,xmax,ymin,ymax,zmin,zmax].")
        xmin, xmax, ymin, ymax, zmin, zmax = bounds'''
)
s = s.replace(
    '''                candidate = np.array(
                    [self.rng.uniform(xmin, xmax), self.rng.uniform(ymin, ymax)],
                    dtype=np.float32,
                )''',
    '''                candidate = np.array(
                    [self.rng.uniform(xmin, xmax), self.rng.uniform(ymin, ymax),
                     self.rng.uniform(zmin, zmax)],
                    dtype=np.float32,
                )'''
)

# 4.5 reset()：vel zeros (n,2)→(n,3)，leader (2,)→(3,)
s = s.replace(
    '        self.vel = np.zeros((self.n, 2), dtype=np.float32)\n'
    '        self.leader_pos = np.asarray(\n'
    '            self.cfg.get("leader_start", [0.0, 0.0]), dtype=np.float32\n'
    '        ).copy()\n'
    '        self.leader_vel = np.array([0.0, 0.0], dtype=np.float32)\n'
    '        self.leader_target = np.asarray(\n'
    '            self.cfg.get("leader_target", [200.0, 200.0]), dtype=np.float32\n'
    '        ).copy()\n'
    '        if self.leader_target.shape != (2,):\n'
    '            raise ValueError("leader_target must contain exactly two coordinates.")',
    '        self.vel = np.zeros((self.n, 3), dtype=np.float32)\n'
    '        self.leader_pos = np.asarray(\n'
    '            self.cfg.get("leader_start", [0.0, 0.0, 20.0]), dtype=np.float32\n'
    '        ).copy()\n'
    '        self.leader_vel = np.array([0.0, 0.0, 0.0], dtype=np.float32)\n'
    '        self.leader_target = np.asarray(\n'
    '            self.cfg.get("leader_target", [200.0, 200.0, 25.0]), dtype=np.float32\n'
    '        ).copy()\n'
    '        if self.leader_target.shape != (3,):\n'
    '            raise ValueError("leader_target must contain exactly three coordinates.")'
)

# 4.6 targets()：2D cos/sin → 3D formation_offsets
s = s.replace(
    '''    def targets(self) -> np.ndarray:
        offsets = np.stack(
            [self.radius * np.array([np.cos(a), np.sin(a)]) for a in self.angles]
        )
        return (self.leader_pos[None, :] + offsets).astype(np.float32)''',
    '''    def targets(self) -> np.ndarray:
        offsets = self.radius * self.formation_offsets
        return (self.leader_pos[None, :] + offsets).astype(np.float32)'''
)

# 4.7 update_leader()：zeros(2)→zeros(3)
s = s.replace(
    '            self.leader_vel = np.zeros(2, dtype=np.float32)\n            return',
    '            self.leader_vel = np.zeros(3, dtype=np.float32)\n            return'
)
s = s.replace(
    '            self.leader_pos = self.leader_target.copy()\n'
    '            self.leader_vel = np.zeros(2, dtype=np.float32)\n'
    '            return\n'
    '        desired_speed = min(self.leader_speed, distance / self.dt)',
    '            self.leader_pos = self.leader_target.copy()\n'
    '            self.leader_vel = np.zeros(3, dtype=np.float32)\n'
    '            return\n'
    '        desired_speed = min(self.leader_speed, distance / self.dt)'
)
s = s.replace(
    '''        if float(np.dot(direction, remaining)) <= 0.0:
            self.leader_pos = self.leader_target.copy()
            self.leader_vel = np.zeros(2, dtype=np.float32)''',
    '''        if float(np.dot(direction, remaining)) <= 0.0:
            self.leader_pos = self.leader_target.copy()
            self.leader_vel = np.zeros(3, dtype=np.float32)'''
)

# 4.8 pairwise_metrics：正四面体边长
s = s.replace(
    '''                diff = abs(float(self.angles[i] - self.angles[j]))
                angle_diff = min(diff, 2 * np.pi - diff)
                desired = float(2 * self.radius * np.sin(angle_diff / 2))''',
    '''                diff = float(np.linalg.norm(
                    self.formation_offsets[i] - self.formation_offsets[j]))
                desired = diff * self.radius'''
)

# 4.9 step()：速度限幅 2D→3D 分轴 + 高度约束
s = s.replace(
    '''        self.vel += actions * float(self.cfg["act_scale"]) * action_scales * self.dt
        speed = np.linalg.norm(self.vel, axis=1, keepdims=True)
        safe_speed = np.maximum(speed, 1e-8)
        self.vel = np.where(
            speed > self.max_speed,
            self.vel / safe_speed * self.max_speed,
            self.vel,
        )
        self.pos += self.vel * self.dt''',
    '''        self.vel += actions * float(self.cfg["act_scale"]) * action_scales * self.dt
        # 3D: horizontal/vertical split-axis speed limiting
        h_speed = np.linalg.norm(self.vel[:, :2], axis=1, keepdims=True)
        safe_h = np.maximum(h_speed, 1e-8)
        self.vel[:, :2] = np.where(
            h_speed > self.max_speed,
            self.vel[:, :2] / safe_h * self.max_speed,
            self.vel[:, :2],
        )
        max_v = float(self.cfg.get("max_vertical_speed", 8.0))
        self.vel[:, 2] = np.clip(self.vel[:, 2], -max_v, max_v)
        self.pos += self.vel * self.dt
        # 3D: altitude hard bounds
        min_alt = float(self.cfg.get("min_altitude", 0.0))
        max_alt = float(self.cfg.get("max_altitude", 1e9))
        self.pos[:, 2] = np.clip(self.pos[:, 2], min_alt, max_alt)'''
)

# ═══════════════════════════════════════════════════════════════
# 5. Actor 网络 2D→3D
# ═══════════════════════════════════════════════════════════════
s = s.replace(
    '''            nn.Linear(64, 2),
        )
        self.log_std = nn.Parameter(torch.zeros(2))''',
    '''            nn.Linear(64, 3),
        )
        self.log_std = nn.Parameter(torch.zeros(3))'''
)

# ═══════════════════════════════════════════════════════════════
# 6. 环境实例化引用更新
# ═══════════════════════════════════════════════════════════════
s = s.replace(
    '        env = MovingLeaderFormationEnv(local_cfg)',
    '        env = MovingLeaderFormationEnv3D(local_cfg)'
)
s = s.replace(
    '        env = MovingLeaderFormationEnv(cfg)',
    '        env = MovingLeaderFormationEnv3D(cfg)'
)
s = s.replace(
    '    env = MovingLeaderFormationEnv(local_cfg)',
    '    env = MovingLeaderFormationEnv3D(local_cfg)'
)
s = s.replace(
    '    env = MovingLeaderFormationEnv(cfg)',
    '    env = MovingLeaderFormationEnv3D(cfg)'
)

# ═══════════════════════════════════════════════════════════════
# 7. results_dir 默认值
# ═══════════════════════════════════════════════════════════════
s = s.replace(
    '    results_dir="comparison_results_revised",',
    '    results_dir="comparison_results_3d",'
)

DST.write_text(s, encoding="utf-8")

# 统计改动
import difflib
orig = SRC.read_text(encoding="utf-8").splitlines()
new = s.splitlines()
diff = list(difflib.unified_diff(orig, new, lineterm=""))
changes = sum(1 for l in diff if l.startswith(("+", "-")) and not l.startswith(("+++", "---")))
print(f"Written: {DST}")
print(f"Total lines: {len(new)}")
print(f"Changed lines (approx): {changes}")
