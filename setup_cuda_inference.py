"""
CUDA 推理环境搭建脚本（一次性）

完成 4 件事：
    1. 检测/安装 CUDA Toolkit（用 winget，需管理员权限 + UAC 确认）
    2. 编译 llama.cpp 的 CUDA 版（llama-cli 等可执行文件）
    3. 安装 llama-cpp-python 的 CUDA 版（Python 绑定）
    4. 验证 GPU 推理可用

⚠️ 重要：本脚本会临时屏蔽 Anaconda 的 PATH，因为 Anaconda 自带的
   OpenSSL/curl 库会干扰 llama.cpp 的链接（之前编译失败的根因）。

用法（用项目 venv 的 python）：
    python setup_cuda_inference.py

前置条件：
    - NVIDIA 驱动已装（你的 595.79 ✅）
    - Visual Studio 2022 C++ 工具链（你的 ✅）
    - CMake（你的 4.2 ✅）
    - winget 可用（你的 ✅）

预计耗时：
    - CUDA Toolkit 下载安装：10-30 分钟（~3GB）
    - llama.cpp 编译：5-15 分钟
    - llama-cpp-python 编译：5-15 分钟
"""
import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LLAMA_DIR = BASE_DIR / "llama.cpp"
GGUF_PATH = BASE_DIR / "phi2-dmpc-q6_k.gguf"

# Visual Studio 的 vcvars64.bat —— 初始化 MSVC 编译环境（PATH/INCLUDE/LIB）
# nvcc 必须在这个环境里才能找到 cl.exe 等 host compiler
VCVARS64 = r"D:\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"


# ----------------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------------
def run(cmd, cwd=None, env=None, check=True, capture=False):
    """运行命令，实时输出或捕获。"""
    print(f"\n$ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    if cwd:
        print(f"  (cwd: {cwd})")
    result = subprocess.run(
        cmd, cwd=cwd, env=env, shell=isinstance(cmd, str),
        capture_output=capture, text=True,
    )
    if check and result.returncode != 0:
        if capture:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"命令失败 (exit {result.returncode}): {cmd}")
    return result


def run_in_msvc_env(cmd_str, cwd=None, check=True, capture=False):
    """
    在 MSVC 编译环境（vcvars64.bat 初始化）下运行一条命令。
    生成一个临时 .bat：先 call vcvars64.bat，再屏蔽 Anaconda，最后执行命令。
    这是让 nvcc 找到 cl.exe + 绕开 MSBuild CUDA .targets 问题的标准做法。

    cmd_str: 要执行的命令字符串（在 .bat 里直接运行）
    """
    ninja_dir = str(BASE_DIR / ".venv" / "Scripts")
    bat_lines = [
        f'@echo off',
        f'call "{VCVARS64}" >nul 2>&1',
        # 屏蔽 Anaconda（OpenSSL/curl 干扰链接）
        f'set "PATH={ninja_dir};%PATH%"',
        f'echo [msvc-env] cl.exe: & where cl.exe >nul 2>&1 && where cl.exe || echo   (not found!)',
    ]
    # 从 PATH 移除 anaconda/miniconda
    bat_lines.append(r'for /f "tokens=1,* delims=;" %%a in ("%PATH%") do (')
    bat_lines.append(r'  set "_clean="')
    bat_lines.append(r'  set "PATH=%%a"')
    # 简单粗暴：直接 set PATH 重新拼接（vcvars 后 Anaconda 路径来自系统 PATH）
    bat_lines = [
        f'@echo off',
        f'call "{VCVARS64}" >nul 2>&1',
        f'set "PATH={ninja_dir};%PATH%"',
        # 移除 PATH 中含 anaconda/miniconda 的条目
        r'call :strip_anaconda',
        f'echo [msvc-env] cl.exe: & where cl.exe',
        f'echo [msvc-env] nvcc: & where nvcc',
        cmd_str,
        f'exit /b %ERRORLEVEL%',
        r':strip_anaconda',
        r'set "_new="',
        r'for %%P in ("%PATH:;=";"%") do (',
        r'  echo %%P | findstr /i /c:"anaconda" /c:"miniconda" >nul || (',
        r'    if defined _new (set "_new=!_new!;%%~P") else (set "_new=%%~P")',
        r'  )',
        r')',
        r'set "PATH=%_new%"',
        r'exit /b 0',
    ]
    bat_content = "\n".join(bat_lines)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".bat", delete=False, encoding="utf-8"
    ) as f:
        f.write("setlocal enabledelayedexpansion\n")
        f.write(bat_content)
        bat_path = f.name
    try:
        print(f"\n$ (in MSVC env) {cmd_str}")
        if cwd:
            print(f"  (cwd: {cwd})")
        result = subprocess.run(
            ["cmd", "/c", bat_path], cwd=cwd,
            capture_output=capture, text=True,
        )
        if check and result.returncode != 0:
            if capture:
                print(result.stdout)
                print(result.stderr, file=sys.stderr)
            raise RuntimeError(f"命令失败 (exit {result.returncode}): {cmd_str}")
        return result
    finally:
        os.unlink(bat_path)


def clean_env_for_build():
    """
    构建一个屏蔽 Anaconda 的环境变量（用于 llama-cpp-python 的 pip 编译，
    该路径不经过 run_in_msvc_env，但 scikit-build 会调 vcvars）。
    """
    env = os.environ.copy()
    path_parts = env.get("PATH", "").split(os.pathsep)
    filtered = [p for p in path_parts if "anaconda" not in p.lower() and "miniconda" not in p.lower()]
    env["PATH"] = os.pathsep.join(filtered)
    for key in list(env.keys()):
        if "CONDA" in key.upper():
            del env[key]
    return env


def find_cuda_toolkit():
    """检测 CUDA Toolkit 安装路径（含 nvcc）。"""
    # 1. 检查 PATH 里的 nvcc
    nvcc = shutil.which("nvcc")
    if nvcc:
        return Path(nvcc).parent.parent  # bin/nvcc -> 上两级
    # 2. 检查默认安装路径
    base = Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA")
    if base.exists():
        versions = sorted(base.iterdir())
        if versions:
            return versions[-1]  # 最新版本
    return None


# ----------------------------------------------------------------------
# 步骤 1：CUDA Toolkit
# ----------------------------------------------------------------------
def step1_cuda_toolkit():
    print("\n" + "=" * 70)
    print("【步骤 1/4】检测 / 安装 CUDA Toolkit")
    print("=" * 70)

    cuda = find_cuda_toolkit()
    if cuda and (cuda / "bin" / "nvcc.exe").exists():
        print(f"✅ CUDA Toolkit 已安装: {cuda}")
        # 验证 nvcc 版本
        r = run([str(cuda / "bin" / "nvcc.exe"), "--version"], capture=True, check=False)
        print(r.stdout.strip().split("\n")[-1] if r.stdout else "")
        return cuda

    print("未检测到 CUDA Toolkit，开始用 winget 安装...")
    print("⚠️ 这会下载约 3GB，可能弹出 UAC 用户账户控制，请点「是」授权。")
    print("   如果 winget 提示协议，输入 Y 接受。")
    print()

    # winget 安装 CUDA Toolkit（最新版，向下兼容 torch cu128）
    run(["winget", "install", "Nvidia.CUDA", "--accept-package-agreements",
         "--accept-source-agreements"], check=True)

    # 重新检测
    cuda = find_cuda_toolkit()
    if not cuda:
        print("❌ winget 安装后仍未检测到 CUDA Toolkit。")
        print("   请手动从 https://developer.nvidia.com/cuda-12-8-0-download-archive")
        print("   下载安装 CUDA 12.8，然后重新运行本脚本。")
        sys.exit(1)

    print(f"\n✅ CUDA Toolkit 安装成功: {cuda}")
    return cuda


# ----------------------------------------------------------------------
# 步骤 2：编译 llama.cpp CUDA 版
# ----------------------------------------------------------------------
def step2_build_llamacpp(cuda_path):
    print("\n" + "=" * 70)
    print("【步骤 2/4】编译 llama.cpp（CUDA 加速）")
    print("=" * 70)

    if not LLAMA_DIR.exists():
        print(f"克隆 llama.cpp 到 {LLAMA_DIR} ...")
        run(["git", "clone", "https://github.com/ggerganov/llama.cpp", str(LLAMA_DIR)])

    build_dir = LLAMA_DIR / "build"
    if build_dir.exists():
        print(f"清理旧的 build 目录: {build_dir}")
        shutil.rmtree(build_dir, ignore_errors=True)

    cuda_bin = str(cuda_path / "bin")
    # 用 Ninja 生成器（-G Ninja）绕开 MSBuild 的 CUDA .targets 集成
    # （后者 CudaToolkitDir 解析脆弱，导致 "CUDA Toolkit directory '' does not exist"）
    # LLAMA_BUILD_UI/SERVER=OFF：禁用 Web UI（其 dist.tar.gz 需从 huggingface.co 下载，本机不可达）
    configure_cmd = (
        f'cmake -G Ninja -B "{build_dir}" -S "{LLAMA_DIR}" '
        f'-DGGML_CUDA=ON '
        f'-DLLAMA_CURL=OFF '        # 禁用 curl，避免链接问题
        f'-DLLAMA_OPENSSL=OFF '     # 禁用 OpenSSL（避免误链系统里的 MinGW 版 libcrypto.a）
        f'-DLLAMA_BUILD_UI=OFF '    # 禁用 Web UI（避免 HF 下载）
        f'-DLLAMA_BUILD_SERVER=OFF '
        f'-DGGML_NATIVE=ON '
        f'-DCMAKE_BUILD_TYPE=Release '
        f'-DCMAKE_CUDA_COMPILER="{cuda_bin}\\nvcc.exe" '
        f'-DCUDAToolkit_ROOT="{cuda_path}"'
    )

    print("配置 CMake (Ninja 生成器 + CUDA)...")
    run_in_msvc_env(configure_cmd, cwd=str(BASE_DIR))

    print("编译中（5-15 分钟，请耐心等待）...")
    # 新版 llama.cpp 把 llama-cli 改名为 llama-app（可执行文件叫 llama.exe）
    build_cmd = f'cmake --build "{build_dir}" --target llama llama-quantize -- -j%NUMBER_OF_PROCESSORS%'
    run_in_msvc_env(build_cmd, cwd=str(BASE_DIR))

    # Ninja 生成器输出在 build/bin/ 下（无 Release 子目录）
    cli = build_dir / "bin" / "llama.exe"
    if not cli.exists():
        cli = build_dir / "llama-cli.exe"  # 旧版本兼容
    if not cli.exists():
        cli = build_dir / "llama-app.exe"
    if cli.exists():
        print(f"\n✅ llama.cpp CUDA 编译成功: {cli}")
    else:
        print(f"❌ 编译后未找到 llama 可执行文件，检查 {build_dir / 'bin'}")
        sys.exit(1)
    return cli


# ----------------------------------------------------------------------
# 步骤 3：安装 llama-cpp-python CUDA 版
# ----------------------------------------------------------------------
def step3_install_llama_cpp_python(cuda_path):
    print("\n" + "=" * 70)
    print("【步骤 3/4】安装 llama-cpp-python（CUDA 版）")
    print("=" * 70)

    # 先检查是否已装且支持 CUDA
    r = run([sys.executable, "-c",
             "import llama_cpp; print('已装')" ], check=False, capture=True)
    if r.returncode == 0 and "已装" in r.stdout:
        r2 = run([sys.executable, "-c",
                  "from llama_cpp import llama_supports_gpu_offload; "
                  "print('GPU offload:', llama_supports_gpu_offload())"],
                 check=False, capture=True)
        if r2.returncode == 0 and "True" in r2.stdout:
            print("✅ llama-cpp-python CUDA 版已安装且支持 GPU offload")
            return
        else:
            print("已装但非 CUDA 版，重新编译...")

    # 先卸载旧的
    run([sys.executable, "-m", "pip", "uninstall", "-y", "llama-cpp-python"],
        check=False, capture=True)

    # 确保 scikit-build-core 和 ninja 已装（--no-build-isolation 需要它们在 venv 里）
    run([sys.executable, "-m", "pip", "install", "scikit-build-core", "ninja",
         "packaging"], check=False, capture=True)

    # 生成一个自包含的 .bat：vcvars 初始化 + 屏蔽 Anaconda + pip 编译
    # （用 .bat 是因为 CMAKE_ARGS 里不能可靠地传递含空格的路径，
    #   改为靠 vcvars 的 PATH 让 CMake 自动发现 nvcc）
    bat = (
        f'@echo off\n'
        f'setlocal enabledelayedexpansion\n'
        f'call "{VCVARS64}" >nul 2>&1\n'
        f'set "PATH={BASE_DIR / ".venv" / "Scripts"};%PATH%"\n'
        # 屏蔽 Anaconda（OpenSSL/curl 干扰链接）
        f'set "_new="\n'
        f'for %%P in ("%PATH:;=\\"%\\"") do (\n'
        f'  echo %%P | findstr /i /c:"anaconda" /c:"miniconda" >nul || (\n'
        f'    if defined _new (set "_new=!_new!;%%~P") else (set "_new=%%~P")\n'
        f'  )\n'
        f')\n'
        f'set "PATH=%_new%"\n'
        # CMAKE_ARGS 不传含空格的路径，靠 PATH 让 CMake 找到 nvcc
        f'set "CMAKE_ARGS=-DGGML_CUDA=ON -DLLAMA_CURL=OFF -DLLAMA_OPENSSL=OFF -DLLAMA_BUILD_UI=OFF -DGGML_NATIVE=ON"\n'
        f'for %%I in (nvcc) do set "CUDACXX=%%~$PATH:I"\n'
        f'set "CMAKE_GENERATOR=Ninja"\n'
        f'"{sys.executable}" -m pip install llama-cpp-python '
        f'--no-cache-dir --force-reinstall --no-build-isolation\n'
        f'exit /b %ERRORLEVEL%\n'
    )
    bat_path = str(BASE_DIR / "_build_lcpp_cuda.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat)

    print("从源码编译 llama-cpp-python CUDA 版（5-15 分钟）...")
    print(f"  （通过 {bat_path} 在 MSVC 环境下编译）")
    try:
        result = subprocess.run(["cmd", "/c", bat_path], cwd=str(BASE_DIR))
        if result.returncode != 0:
            raise RuntimeError(f"llama-cpp-python 编译失败 (exit {result.returncode})")
    finally:
        os.unlink(bat_path)

    # 验证
    r = run([sys.executable, "-c",
             "from llama_cpp import llama_supports_gpu_offload; "
             "print('GPU offload:', llama_supports_gpu_offload())"],
            capture=True, check=False)
    if r.returncode == 0 and "True" in r.stdout:
        print("\n✅ llama-cpp-python CUDA 版安装成功，支持 GPU offload")
    else:
        print("\n❌ 安装后验证失败。输出:")
        print(r.stdout)
        print(r.stderr)
        sys.exit(1)


# ----------------------------------------------------------------------
# 步骤 4：验证 GPU 推理
# ----------------------------------------------------------------------
def step4_verify():
    print("\n" + "=" * 70)
    print("【步骤 4/4】验证 GPU 推理")
    print("=" * 70)

    if not GGUF_PATH.exists():
        print(f"⚠️ GGUF 模型不存在: {GGUF_PATH}")
        print("  跳过推理验证（环境已就绪，生成模型后可用 benchmark_gguf.py 测评）")
        return

    print(f"用 {GGUF_PATH.name} 做一次 GPU 推理测试...")
    test_code = (
        "from llama_cpp import Llama; "
        "llm = Llama(model_path=r'" + str(GGUF_PATH) + "', "
        "n_gpu_layers=-1, n_ctx=512, verbose=False); "
        "out = llm('### System:\\nParse command for UAV DMPC.\\n\\n### User:\\nUAV 1, fly to (1,2,3).\\n\\n### Response:\\n', "
        "max_tokens=32, temperature=0.1, stop=['<|endoftext|>']); "
        "print('输出:', out['choices'][0]['text'].strip()); "
        "print('耗时相关 tokens:', out['usage']['completion_tokens'])"
    )
    r = run([sys.executable, "-c", test_code], check=False, capture=True)
    if r.returncode == 0:
        print(r.stdout)
        print("\n✅ GPU 推理验证成功！现在可以运行: python benchmark_gguf.py")
    else:
        print("❌ 推理验证失败:")
        print(r.stdout)
        print(r.stderr)


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def main():
    print("=" * 70)
    print("  CUDA 推理环境搭建（CUDA Toolkit + llama.cpp + llama-cpp-python）")
    print("=" * 70)

    # 前置检查
    if not shutil.which("cmake"):
        print("❌ 未找到 cmake，请先安装 CMake")
        sys.exit(1)
    if not Path("D:/Microsoft Visual Studio/2022").exists() and not shutil.which("cl"):
        print("⚠️ 警告：未检测到 Visual Studio C++ 工具链，编译可能失败")

    cuda_path = step1_cuda_toolkit()
    step2_build_llamacpp(cuda_path)
    step3_install_llama_cpp_python(cuda_path)
    step4_verify()

    print("\n" + "=" * 70)
    print("  ✅ 全部完成！CUDA 推理环境已就绪")
    print("=" * 70)
    print("下一步：运行 python benchmark_gguf.py 做 Q6_K GPU 推理测评")
    print(f"  预期吞吐：40-60 tok/s（vs 当前 transformers 4-bit 的 10 tok/s）")


if __name__ == "__main__":
    main()
