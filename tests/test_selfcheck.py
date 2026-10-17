"""
核心自检 —— `pytest` 一条命令证明环境正常
==========================================

全新 clone 后：

    pip install -r requirements.txt     # 只需要标准库 + pytest
    pytest

应当全绿，耗时 < 2 分钟。**这不重跑论文实验**，只验证：

  ① 冻结完整性   v2_frozen / v3_frozen 的 SHA256 与清单一致
  ② 冻结导入     模型确实来自 v3_frozen，版本与关键常量正确
  ③ 机制层       novel_situation 的 8 项自检（规则 60/61/63 等）
  ④ 回归         规则 72 的窗口口径修复
  ⑤ 确定性       同一输入两次运行逐位相同（规则 55 的最小版）

完整复现见 `REPRODUCE.md`。
"""

import hashlib
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---------------------------------------------------------------- ① 冻结完整性
@pytest.mark.parametrize("frozen", ["v2_frozen", "v3_frozen"])
def test_frozen_checksums(frozen):
    d = os.path.join(ROOT, frozen)
    sums = os.path.join(d, "SHA256SUMS.txt")
    assert os.path.exists(sums), f"{frozen}/SHA256SUMS.txt 缺失"
    bad, n = [], 0
    for line in open(sums, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        want, name = line.split(maxsplit=1)
        p = os.path.join(d, name)
        assert os.path.exists(p), f"{frozen}/{name} 缺失"
        got = hashlib.sha256(open(p, "rb").read()).hexdigest()
        n += 1
        # v2 的清单存的是前 16 位，v3 存的是完整 64 位
        if not got.startswith(want):
            bad.append(name)
    assert not bad, f"{frozen} 校验失败：{bad}"
    assert n >= 25, f"{frozen} 只校验了 {n} 个文件，清单可能不完整"


# ---------------------------------------------------------------- ② 冻结导入
def test_v3_frozen_import():
    import novel_situation as NS
    assert os.path.abspath(NS.sim.__file__).startswith(
        os.path.join(ROOT, "v3_frozen")), "模型不是来自 v3_frozen"
    assert NS.sim.MODEL_VERSION == "v3"
    assert NS.sim.COND_RECOVER_AT == 65.0, "v3 的关键常量被改动"


def test_v2_v3_differ_only_by_one_constant():
    """v2 → v3 的唯一可执行差异必须仍然只有 COND_RECOVER_AT（+ 新增 MODEL_VERSION）

    ⚠ 不能用"剥掉 # 注释后逐行比对"—— v3 的模块 docstring 里写了大段
      为什么是 65 的说明，那会被误判成代码差异。**必须比 AST，并剥掉
      docstring**，才是真正的"可执行差异"。
    """
    import ast

    def top_nodes(path):
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)):
                body = node.body
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    node.body = body[1:]          # 剥 docstring
        return [ast.dump(n) for n in tree.body]

    a = top_nodes(os.path.join(ROOT, "v2_frozen", "sim.py"))
    b = top_nodes(os.path.join(ROOT, "v3_frozen", "sim.py"))

    only_a = [x for x in a if x not in b]
    only_b = [x for x in b if x not in a]
    for x in only_a:
        assert "COND_RECOVER_AT" in x, f"v2 独有的可执行语句：{x[:200]}"
    for x in only_b:
        assert ("COND_RECOVER_AT" in x or "MODEL_VERSION" in x), \
            f"v3 独有的可执行语句：{x[:200]}"
    assert len(only_a) == 1 and len(only_b) == 2, \
        f"差异条数不符：v2独有 {len(only_a)}，v3独有 {len(only_b)}"


# ---------------------------------------------------------------- ③ 机制层
def test_mechanism_layer():
    import novel_situation as NS
    NS._test_gate_non_destructive()      # 规则 60
    NS._test_sibling_isolation()         # 规则 61
    NS._test_identical_branches()        # 阴性对照
    NS._test_floor_off_fork()            # 024 的 deepcopy 陷阱
    NS._test_field_audit()               # 规则 63
    NS._test_probe_c()                   # 规则 60/61/65


# ---------------------------------------------------------------- ④ 回归
def test_rule72_window_regression():
    r = subprocess.run([sys.executable, "novel_calibrate3.py", "--test"],
                       cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "规则 72 回归测试通过" in r.stdout


# ---------------------------------------------------------------- ⑤ 确定性
def test_determinism():
    """同一颗种子跑两次，完整可执行状态必须逐位相同（规则 55 的最小版）"""
    import novel_situation as NS

    def run():
        life = NS.scenarios.make(20000, "贫瘠世界")
        NS.run_window(life, 0, 6)
        return NS.full_hash(life)
    assert run() == run(), "同一输入两次运行结果不同 —— 存在未受控的随机性"


def test_final_confirm_gate():
    """final_confirm 的冻结校验闸必须能独立通过"""
    r = subprocess.run([sys.executable, "final_confirm.py", "--check"],
                       cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "MODEL_VERSION=v3" in r.stdout
