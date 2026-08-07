# 参考规则库 (Reference Rules)

本目录存放**纯参考/知识库类规则**，当前**无对应执行引擎**。

## 为什么放在这里？

这些语言专项规则全部为 SEMANTIC 类型（无正则 pattern、无 semgrep_id），且
`semantic_scanner.py` 的执行引擎仅支持 Python AST 分析、JS/TS XSS 检查和配置文件检查。
Java、Go、Rust、C++、C#、PHP、Ruby 语言的规则虽然定义了类别和检测建议，
但扫描器无法对这些语言的文件执行实际检测逻辑，属于"死规则"。

## 包含的语言

| 目录 | 语言 | 规则数 | 说明 |
|------|------|--------|------|
| `java/` | Java | 20 | NPE防护、资源管理、Spring框架、JPA性能 |
| `go/` | Go | 15 | goroutine泄漏、defer使用、error处理 |
| `rust/` | Rust | 8 | unsafe使用、panic处理、并发安全 |
| `cpp/` | C++ | 10 | 内存管理、智能指针、缓冲区溢出 |
| `csharp/` | C# | 10 | async/await、空引用、LINQ性能 |
| `php/` | PHP | 10 | SQL注入、XSS、文件包含、反序列化 |
| `ruby/` | Ruby | 8 | SQL拼接、eval注入、Mass Assignment |

## 如何启用？

当 `semantic_scanner.py` 增加对应语言的执行引擎后，将这些目录移回 `rules/` 即可自动加载。

## 如何访问？

代码中可通过 `RuleLoader.get_semantic_rules_with_reference()` 获取包含这些规则在内的
全部语义规则（含 executable + reference）。
