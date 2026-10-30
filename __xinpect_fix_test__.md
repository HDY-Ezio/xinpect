# 测试文件（已修复）

import hashlib
def h(d):
    return hashlib.sha256(d.encode()).hexdigest()
