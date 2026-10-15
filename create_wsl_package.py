#!/usr/bin/env python3
"""create_wsl_package.py - 在 WSL2 中创建 uav_adversarial 包并部署全部代码

用法：在 Windows 侧执行：
  python create_wsl_package.py
或在 WSL2 中执行：
  python3 /mnt/d/2026-2027/Phi-2\ QLoRA/create_wsl_package.py
"""
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
WSL_PKG = Path('/home/chuanyu/px4_ws/src/uav_adversarial')
WSL_PY = WSL_PKG / 'uav_adversarial'

# Windows 侧新结构 -> WSL2 包结构映射
DEPLOY_MAP = {
    # 共享库
    'src/common/phase_rules.py':        'common/phase_rules.py',
    'src/common/phase_link.py':         'common/phase_link.py',
    'src/common/safety_layer.py':       'common/safety_layer.py',
    'src/common/safety_adversarial.py': 'common/safety_adversarial.py',
    # 端侧节点
    'src/nodes/edge/nl_command_node.py': 'edge/nl_command_node.py',
    # 云端节点
    'src/nodes/cloud/phase_generator.py':     'cloud/phase_generator.py',
    'src/nodes/cloud/phase_generator_adv.py': 'cloud/phase_generator_adv.py',
    'src/nodes/cloud/heartbeat_node.py':      'cloud/heartbeat_node.py',
    # 裁判
    'src/nodes/referee/referee_node.py': 'referee/referee_node.py',
    # 工具
    'src/nodes/tools/fault_proxy.py': 'tools/fault_proxy.py',
    # 快捷工具（用户入口）
    'scripts/pub_nl.py':        'tools/pub_nl.py',
    'scripts/pub_situation.py': 'tools/pub_situation.py',
}

SETUP_PY = '''from setuptools import setup

package_name = 'uav_adversarial'
setup(
    name=package_name,
    version='2.0.0',
    packages=[
        package_name,
        package_name + '.common',
        package_name + '.edge',
        package_name + '.cloud',
        package_name + '.referee',
        package_name + '.tools',
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    entry_points={
        'console_scripts': [
            # 端侧
            'edge_node = uav_adversarial.edge.nl_command_node:main',
            # 云端
            'phase_gen = uav_adversarial.cloud.phase_generator:main',
            'phase_gen_adv = uav_adversarial.cloud.phase_generator_adv:main',
            'heartbeat = uav_adversarial.cloud.heartbeat_node:main',
            # 裁判
            'referee = uav_adversarial.referee.referee_node:main',
            # 工具
            'fault_proxy = uav_adversarial.tools.fault_proxy:main',
        ],
    },
)
'''

PACKAGE_XML = '''<?xml version="1.0"?>
<?xml-model href="http://download.ros.org/schema/package_format3.xsd" schematypens="http://www.w3.org/2001/XMLSchema"?>
<package format="3">
  <name>uav_adversarial</name>
  <version>2.0.0</version>
  <description>Multi-UAV adversarial simulation with phase-aware LLM control</description>
  <maintainer email="shuyuchuan@example.com">Shu Yuchuan</maintainer>
  <license>MIT</license>
  <exec_depend>rclpy</exec_depend>
  <exec_depend>std_msgs</exec_depend>
  <exec_depend>px4_msgs</exec_depend>
</package>
'''


def main():
    is_wsl = os.path.exists('/home/chuanyu')
    if not is_wsl:
        print('请在 WSL2 中运行本脚本，或使用 wsl 命令调用')
        print('用法：wsl -d Ubuntu-22.04 -- python3 "/mnt/d/2026-2027/Phi-2 QLoRA/create_wsl_package.py"')
        return

    # 创建包结构
    for sub in ['common', 'edge', 'cloud', 'referee', 'tools']:
        d = WSL_PY / sub
        d.mkdir(parents=True, exist_ok=True)
        init = d / '__init__.py'
        if not init.exists():
            init.touch()

    WSL_PKG.mkdir(parents=True, exist_ok=True)
    (WSL_PKG / 'resource').mkdir(exist_ok=True)
    (WSL_PKG / 'resource' / 'uav_adversarial').touch()

    # 写 setup.py
    setup_path = WSL_PKG / 'setup.py'
    setup_path.write_text(SETUP_PY, encoding='utf-8')

    # 写 package.xml
    xml_path = WSL_PKG / 'package.xml'
    xml_path.write_text(PACKAGE_XML, encoding='utf-8')

    # 部署源码
    for src_rel, dst_rel in DEPLOY_MAP.items():
        src = ROOT / src_rel
        dst = WSL_PY / dst_rel
        if not src.exists():
            print(f'  WARN: {src_rel} 不存在，跳过')
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        print(f'  OK: {src_rel} -> {dst_rel}')

    # 修正 import 路径（相对导入改为包内导入）
    fix_imports()

    print('\n=== 包创建完成 ===')
    print(f'位置: {WSL_PKG}')
    print('\n下一步编译：')
    print('  cd ~/px4_ws && colcon build --packages-select uav_adversarial')
    print('  source install/setup.bash')
    print('  ros2 pkg executables uav_adversarial')


def fix_imports():
    """将 `from .phase_rules import ...` 修正为 `from ..common.phase_rules import ...`"""
    fixes = {
        'edge/nl_command_node.py': [
            ('from .phase_rules import', 'from ..common.phase_rules import'),
            ('from .safety_layer import', 'from ..common.safety_layer import'),
            ('from .phase_link import', 'from ..common.phase_link import'),
            ('from phase_rules import', 'from ..common.phase_rules import'),
            ('from safety_layer import', 'from ..common.safety_layer import'),
            ('from phase_link import', 'from ..common.phase_link import'),
        ],
        'cloud/phase_generator.py': [
            ('from .phase_rules import', 'from ..common.phase_rules import'),
            ('from phase_rules import', 'from ..common.phase_rules import'),
        ],
        'cloud/phase_generator_adv.py': [
            ('from .phase_rules import', 'from ..common.phase_rules import'),
            ('from phase_rules import', 'from ..common.phase_rules import'),
        ],
        'tools/fault_proxy.py': [],
        'referee/referee_node.py': [],
    }

    for filepath, replacements in fixes.items():
        p = WSL_PY / filepath
        if not p.exists():
            continue
        content = p.read_text(encoding='utf-8')
        for old, new in replacements:
            content = content.replace(old, new)
        p.write_text(content, encoding='utf-8')
        if replacements:
            print(f'  IMPORT FIX: {filepath}')


if __name__ == '__main__':
    main()
