from langchain_core.tools import tool
import os
import shutil
import subprocess
import threading
import shlex

# ============================================================
# 安全配置：工作空间根目录
# 所有文件读写操作都限制在此目录内，防止路径遍历攻击。
# 后续与编排引擎集成时，可改为动态传入的工作空间路径。
# ============================================================
WORKSPACE_ROOT = os.path.abspath(os.path.dirname(__file__))
_workspace_local = threading.local()
_event_sink_local = threading.local()

# — 代码搜索时过滤的文本文件扩展名 —
_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".html", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".md", ".txt", ".rst",
    ".sh", ".bat", ".ps1", ".sql", ".java", ".go", ".rs", ".c", ".cpp", ".h",
    ".cs", ".rb", ".php", ".swift", ".kt", ".scala", ".env", ".gitignore",
}

# — pip install 白名单（仅允许安装开发相关工具包）—
_PIP_WHITELIST = {
    "pytest", "pytest-cov", "pytest-asyncio", "pytest-mock",
    "httpx", "requests",
    "ruff", "pylint", "bandit", "black", "mypy", "flake8",
    "fastapi", "uvicorn", "sqlalchemy", "pydantic",
    "pip", "setuptools", "wheel",
}

# ============================================================
# 路径安全校验函数
# ============================================================
def _safe_resolve(path: str, root: str|None = None) -> str:
    """
    将用户传入的路径解析为绝对路径，并校验是否在允许的根目录内。

    设计思路 —— 为什么不能直接 startswith 比较？
    ─────────────────────────────────────────────
    1. Agent 可能传相对路径（如 test_workspace/hello.py），
       它不以 "e:\\vscode\\..." 开头，会被误判为非法。
    2. Agent 可能传 ../../etc/passwd，不做解析的话前缀匹配形同虚设。
    3. 因此必须先 abspath（消除 ../），再 realpath（消除软链接），
       最后才做前缀匹配。
    4、纯路径字符串计算（abspath、commonpath），不检查目录是否真实存在。
    真正的目录创建发生在 write_file 的 os.makedirs(..., exist_ok=True)
    """
    if root is None:
        root = get_workspace()  # 动态读取工作空间

    # 步骤1：处理相对路径 → 绝对路径（消除 . 和 ..）
    full_path = os.path.abspath(os.path.join(root, path))

    # 步骤2：解析软链接（Linux/Mac），使用 realpath 避免绕过路径遍历检查
    try:
        real_path = os.path.realpath(full_path)
    except Exception:
        real_path = full_path

    # 步骤3：前缀匹配
    # os.path.commonpath 保留第一参数的路径大小写，统一 lower 比较以兼容 Windows
    common = os.path.commonpath([real_path, root])
    try:
        if common.lower() != root.lower():
            raise ValueError(
                f"路径遍历攻击拦截: '{path}' 解析后不在工作空间内。"
                f" 解析结果: {real_path}, 根目录: {root}"
            )
    except (TypeError, AttributeError):
        # commonpath 对不同盘符会返回空字符串或抛异常，此时必定越界
        raise ValueError(
            f"路径遍历攻击拦截: '{path}' 解析后不在工作空间内。"
            f" 解析结果: {real_path}, 根目录: {root}"
        )

    return real_path

# ============================================================
# 路径函数：目录扫描（返回相对路径列表）
# ============================================================
def set_workspace(workspace: str):
    """
    设置工作空间根目录，用于后续文件读写操作。
    """
    _workspace_local.workspace = workspace

def get_workspace():
    """
    获取当前工作空间根目录。
    """
    return getattr(_workspace_local, "workspace", WORKSPACE_ROOT)

def set_event_sink(sink):
    _event_sink_local.sink = sink

def get_event_sink():
    return getattr(_event_sink_local, "sink", None)

# ============================================================
# 辅助函数：目录扫描（返回相对路径列表）
# ============================================================
def _scan_dir(root: str, max_depth: int) -> list[str]:
    """深度优先遍历目录树，返回相对于 root 的路径列表。"""
    result: list[str] = []
    stack: list[tuple[str, int]] = [(root, 0)]  # (当前目录, 当前深度)

    while stack:
        cur_path, depth = stack.pop()
        if depth > max_depth:
            continue

        try:
            with os.scandir(cur_path) as entries:
                for entry in entries:
                    # 跳过隐藏文件和 __pycache__
                    if entry.name.startswith('.') or entry.name == '__pycache__':
                        continue
                    rel_path = os.path.relpath(entry.path, root)
                    result.append(rel_path)
                    if entry.is_dir(follow_symlinks=False) and depth + 1 <= max_depth:
                        stack.append((entry.path, depth + 1))
        except PermissionError:
            continue

    return result


# ============================================================
# 第一个核心工具：读取文件
# ============================================================
@tool
def read_file(path: str, start_line: int = 1, end_line: int = -1) -> str:
    """
    读取项目工作空间内的文件内容。

    参数:
        path: 文件路径，可以是相对路径（如 'src/main.py'）或绝对路径。
              不允许 ../ 逃逸到工作空间外部。
    返回:
        文件内容字符串；若出错则返回错误描述。
    """
    try:
        safe_path = _safe_resolve(path)
    except ValueError as e:
        return str(e)

    try:
        with open(safe_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if start_line > len(lines) or start_line < 1:
                return f"invalid start_line: {start_line}"
            end = None if end_line == -1 else end_line
            chunk = lines[start_line - 1 : end]
            # 设置一个上限，以免内容过长，只返回前 200 行。
            truncated = len(chunk) > 200
            if truncated:
                chunk = chunk[:200]
            text = "".join(f"{line} | {content}" for line, content in enumerate(chunk, start=start_line))
            if truncated:
                text += f"\n...(文件共 {len(lines)} 行，已省略后 {len(lines)-200} 行，请用 start_line/end_line 分段读取)"
            return text

    except FileNotFoundError:
        return f"错误: 文件不存在 —— {path}"
    except PermissionError:
        return f"错误: 没有权限读取 —— {path}"
    except IsADirectoryError:
        return f"错误: 路径是目录而非文件 —— {path}"
    except UnicodeDecodeError:
        return f"错误: 文件不是 UTF-8 文本格式 —— {path}"
    except Exception as e:
        return f"错误: 其他原因 —— {path}, 原因: {e}"


# ============================================================
# 第二个核心工具：写文件
# ============================================================
@tool
def write_file(path: str, content: str) -> str:
    """
    将内容写入指定路径的文件。

    参数:
        path: 文件路径，可以是相对路径或绝对路径。
        content: 要写入的文件内容（字符串）。

    返回:
        成功时返回确认信息；出错时返回错误描述。

    安全措施:
        - 路径遍历防护（通过 _safe_resolve 限制在工作空间内）
        - 覆盖前自动备份旧文件（备份为 path.backup）
    """
    try:
        safe_path = _safe_resolve(path)
    except ValueError as e:
        return str(e)

    try:
        # 如果文件已存在，先备份
        if os.path.isfile(safe_path):
            shutil.copy2(safe_path, f"{safe_path}.backup")

        # 确保父目录存在
        parent = os.path.dirname(safe_path) or "."
        os.makedirs(parent, exist_ok=True)

        # 写入文件
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return f"文件已写入: {path}"

    except PermissionError:
        return f"错误: 没有权限写入 —— {path}"
    except IsADirectoryError:
        return f"错误: 路径是目录而非文件 —— {path}"
    except Exception as e:
        return f"错误: 写入文件失败 —— {path}, 原因: {e}"


# ============================================================
# 第三个核心工具：执行 shell 命令
# ============================================================
@tool
def execute_shell_command(command: str) -> str:
    """
    执行指定的 shell 命令。

    安全措施:
        - 命令白名单：仅允许 python/pytest/pip/ls/cat/echo/ruff/pylint
        - 危险模式拦截：禁止 rm/sudo/curl/wget 及管道/重定向符号
        - 超时控制：30 秒超时，防止无限挂起
    """
    ALLOWED_COMMANDS = ["python", "pytest", "pip", "ls", "cat", "echo", "ruff", "pylint"]
    FORBIDDEN_PATTERNS = ["rm ", "sudo", "curl", "wget", ">", "|", "&"]

    # 空值检查（必须在 split 之前）
    if not command or not command.strip():
        return "错误: 命令为空"

    try:
        arg = shlex.split(command.strip())  # 返回的是一个列表，不能直接用于下面的比较
    except ValueError as e:
        return f"错误: 命令引号不匹配 —— {e}"

    cmd_base = arg[0]  # 命令名（不包含参数）
    if cmd_base not in ALLOWED_COMMANDS:
        return f"错误: 命令 '{cmd_base}' 不在白名单中。允许的命令: {', '.join(ALLOWED_COMMANDS)}"

    # 检查危险模式
    for pattern in FORBIDDEN_PATTERNS:
        if pattern in command:
            return f"错误: 检测到禁止的模式 '{pattern}'。"

    # 执行命令（30s 超时）
    try:
        result = subprocess.run(
            arg,  # 命令列表，不包含参数
            shell=False, 
            capture_output=True, 
            encoding='utf-8',
            errors='ignore', 
            timeout=30,
            cwd=get_workspace()
        )
        if result.returncode == 0:
            return result.stdout
        else:
            # pytest 等工具把结果写在 stdout，失败时必须保留
            output = (result.stdout + "\n" + result.stderr).strip() if result.stdout else result.stderr
            return f"命令执行失败 (exit code {result.returncode}):\n{output}"
    except subprocess.TimeoutExpired:
        return "错误: 命令执行超时（30s），已终止。"
    except FileNotFoundError:
        return f"错误: 命令 '{cmd_base}' 未找到。注意：ls/cat/echo 在 Windows 上可能不可用，可使用 list_directory/read_file 替代。"
    except Exception as e:
        return f"错误: 命令执行异常 —— {e}"


# ============================================================
# 第四个核心工具：列出目录结构
# ============================================================
@tool
def list_directory(path: str = ".") -> str:
    """
    列出指定路径的目录结构（最大深度 10 层）。

    参数:
        path: 目录路径，默认为工作空间根目录。
    返回:
        目录结构列表，每行一个相对路径。
    """
    try:
        safe_path = _safe_resolve(path)
    except ValueError as e:
        return str(e)

    try:
        if not os.path.isdir(safe_path):
            return f"错误: '{path}' 不是一个目录。"

        entries = _scan_dir(safe_path, 10)
        if not entries:
            return f"目录 '{path}' 为空。"
        return "\n".join(sorted(entries))
    except Exception as e:
        return f"错误: 列出目录结构失败 —— {e}"


# ============================================================
# 第五个核心工具：在项目中搜索代码
# ============================================================
@tool
def search_code(query: str) -> str:
    """
    在工作空间中搜索包含指定字符串的代码行。
    自动跳过二进制文件、隐藏目录、__pycache__ 和 node_modules。

    参数:
        query: 要搜索的字符串。
    返回:
        匹配结果列表，格式: 相对路径:行号: 行内容。
    """
    if not query or not query.strip():
        return "错误: 搜索内容不能为空"

    results: list[str] = []
    root = get_workspace()  # 动态读取工作空间

    try:
        for dirpath, dirnames, filenames in os.walk(root):
            # 跳过隐藏目录和虚拟环境
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith('.')
                and d not in ('__pycache__', 'node_modules', 'venv', '.venv', 'env', '.git')
            ]

            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext and ext not in _CODE_EXTENSIONS:
                    continue

                filepath = os.path.join(dirpath, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        for lineno, line in enumerate(f, 1):
                            if query in line:
                                rel_path = os.path.relpath(filepath, root)
                                results.append(f"{rel_path}:{lineno}: {line.rstrip()}")
                except (PermissionError, OSError):
                    continue

                # 限制结果数量，防止 Agent 上下文溢出
                if len(results) >= 200:
                    results.append("... (结果已截断，仅显示前 200 条)")
                    return "\n".join(results)
    except Exception as e:
        return f"错误: 搜索代码失败 —— {e}"

    if not results:
        return f"未在工作空间中找到包含 '{query}' 的文件。"

    return "\n".join(results)


# ============================================================
# 第六个核心工具：安装 Python 依赖（白名单控制）
# ============================================================
@tool
def install_pkg(package: str) -> str:
    """
    安装指定的 Python 包（仅限白名单内的开发工具包）。

    参数:
        package: 要安装的包名，如 'pytest'、'ruff' 等。
    返回:
        安装结果信息。
    """
    if not package or not package.strip():
        return "错误: 包名不能为空"

    # 提取包名（去掉可能的版本号，如 pytest==7.4.0 → pytest）
    pkg_name = package.strip().split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].split("!=")[0].split(">")[0].split("<")[0].strip()

    if pkg_name not in _PIP_WHITELIST:
        allowed = ", ".join(sorted(_PIP_WHITELIST))
        return f"错误: 包 '{pkg_name}' 不在安装白名单中。\n允许安装的包: {allowed}"

    try:
        result = subprocess.run(
            ["pip", "install", package.strip()],
            capture_output=True, text=True, timeout=120,
            encoding='utf-8', errors='ignore'
        )
        if result.returncode == 0:
            return f"安装成功: {package}\n{result.stdout}"
        else:
            return f"安装失败 (exit code {result.returncode}):\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return "错误: pip 安装超时（120s），已终止。"
    except Exception as e:
        return f"错误: 安装依赖失败 —— {e}"

# =======================================
# 第七个核心工具：编辑文件，可以实现局部修改
# =======================================
@tool
def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = True) -> str:
    """
    在指定文件中替换指定字符串。

    参数:
        path: 文件路径，可以是相对路径或绝对路径。
        old_string: 要替换的字符串。
        new_string: 替换后的字符串。
        replace_all: 是否替换所有匹配项，默认为 True。

    返回:
        替换结果信息。
    """
    try:
        safe_path = _safe_resolve(path)
    except ValueError as e:
        return str(e)
    if os.path.isfile(safe_path):
        shutil.copy2(safe_path, f"{safe_path}.backup")
    
    with open(safe_path, 'r', encoding='utf-8') as f:
        content = f.read()
        if old_string not in content:
            return f"未找到 '{old_string}' 在文件中, 请 read_file 查看。"
        if replace_all:
            content = content.replace(old_string, new_string)
        else:
            count = content.count(old_string)
            if count == 1:
                content = content.replace(old_string, new_string)
            else:
                return f"出现 {count} 个 '{old_string}'，请提供更长的上下文"

    with open(safe_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return f"文件已修改: {path}"