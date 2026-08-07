#!/usr/bin/env python3
"""为未覆盖的43个维度补充规则"""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))

def save_json(rel_path, rules_data):
    path = os.path.join(BASE, rel_path)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(rules_data, f, ensure_ascii=False, indent=2)
    print(f"  ✅ {rel_path} ({len(rules_data['rules'])} rules)")

# ============================================================
# B1 - 规则引擎 缺失维度
# ============================================================

# B1-09 注解规范
save_json('common/annotation_rules.json', {"rules": [
    {
        "id": "B1-09-R001", "name": "Deprecated标记的函数仍被调用", "severity": "medium",
        "category": "annotation-convention",
        "description": "调用了已标记为@Deprecated的函数/方法，应使用推荐的新接口替代。",
        "suggestion": "替换为@Deprecated注解推荐的替代方案；如无替代方案，评估是否需要继续使用。",
        "applicable_files": ["*.java","*.kt","*.ts","*.js","*.py","*.cs"]
    },
    {
        "id": "B1-09-R002", "name": "Override注解缺失", "severity": "low",
        "category": "annotation-convention",
        "description": "重写父类方法时未添加@Override注解，可能导致签名不匹配时无法被编译器检测到。",
        "suggestion": "所有重写父类方法的地方都添加@Override注解。",
        "applicable_files": ["*.java","*.kt","*.ts","*.cs"]
    },
    {
        "id": "B1-09-R003", "name": "注解参数使用不当", "severity": "medium",
        "category": "annotation-convention",
        "description": "注解使用了错误的参数值或在不适用的上下文中使用了注解（如@Test注解用在非测试方法上）。",
        "suggestion": "检查注解的适用范围和参数值是否正确；参考框架文档确认注解用法。",
        "applicable_files": ["*.java","*.kt","*.ts","*.py","*.cs"]
    },
    {
        "id": "B1-09-R004", "name": "缺少必要的框架注解", "severity": "medium",
        "category": "annotation-convention",
        "description": "使用了框架（Spring/Flask/Django等）但未添加必要注解，如@Service、@Component、@RequestMapping等缺失。",
        "suggestion": "根据框架要求添加对应注解；确保组件能被正确扫描和注入。",
        "applicable_files": ["*.java","*.kt","*.py","*.ts","*.cs"]
    },
    {
        "id": "B1-09-R005", "name": "SuppressWarnings滥用", "severity": "medium",
        "category": "annotation-convention",
        "description": "使用@SuppressWarnings压制了大量编译器警告，可能掩盖真实问题。",
        "suggestion": "逐一审查被压制的警告，修复根本问题；仅对确实无法修复的第三方库兼容问题使用压制。",
        "applicable_files": ["*.java","*.kt","*.ts","*.cs"]
    }
]})

# B1-10 空值基础检查
save_json('common/null_check_rules.json', {"rules": [
    {
        "id": "B1-10-R001", "name": "未判空直接调用方法", "severity": "high",
        "category": "null-check",
        "description": "对可能为null/undefined的对象直接调用方法或访问属性，未进行空值检查，运行时将抛出NullPointerException或TypeError。",
        "suggestion": "在调用前添加空值检查；使用可选链操作符（?.）；使用Optional/Maybe类型包装可能为空的值。",
        "applicable_files": ["*.java","*.js","*.ts","*.py","*.cs","*.go"]
    },
    {
        "id": "B1-10-R002", "name": "函数返回null但未文档化", "severity": "medium",
        "category": "null-check",
        "description": "函数可能在某些路径下返回null，但调用方未被告知该风险，导致未判空就使用返回值。",
        "suggestion": "在函数文档/类型标注中明确标注返回值可能为null；使用@Nullable注解或Optional<T>返回类型。",
        "applicable_files": ["*.java","*.kt","*.ts","*.py","*.cs"]
    },
    {
        "id": "B1-10-R003", "name": "集合可能为null直接遍历", "severity": "high",
        "category": "null-check",
        "description": "对可能为null的集合/数组直接进行for循环或forEach操作，null将导致空指针异常。",
        "suggestion": "遍历前检查集合是否为null；返回空集合代替null；使用Collections.emptyList()作为默认值。",
        "applicable_files": ["*.java","*.js","*.ts","*.py","*.cs","*.go"]
    },
    {
        "id": "B1-10-R004", "name": "三元表达式中null分支缺失", "severity": "medium",
        "category": "null-check",
        "description": "三元运算符或nullish coalescing未正确处理null/undefined分支，导致后续使用可能为空的值。",
        "suggestion": "为null情况提供合理的默认值；使用??运算符提供fallback值。",
        "applicable_files": ["*.js","*.ts","*.java","*.cs","*.py"]
    },
    {
        "id": "B1-10-R005", "name": "equals比较中变量可能为null", "severity": "high",
        "category": "null-check",
        "description": "使用variable.equals(literal)形式比较，当variable为null时将抛出NPE。应反转为literal.equals(variable)。",
        "suggestion": "将常量/字面量放在equals左侧；使用Objects.equals()；使用==null提前返回。",
        "applicable_files": ["*.java","*.cs"]
    },
    {
        "id": "B1-10-R006", "name": "解构赋值中未处理null", "severity": "medium",
        "category": "null-check",
        "description": "对可能为null的对象进行解构赋值（如const {a, b} = obj），当obj为null/undefined时将抛出TypeError。",
        "suggestion": "解构前检查对象是否为null；提供默认空对象：const {a, b} = obj || {}。",
        "applicable_files": ["*.js","*.ts","*.py"]
    }
]})

# B1-11 资源泄漏基础模式
save_json('common/resource_leak_rules.json', {"rules": [
    {
        "id": "B1-11-R001", "name": "文件流未在finally/finally等价结构中关闭", "severity": "high",
        "category": "resource-leak",
        "description": "打开了文件/流/连接等资源但未在finally块或使用try-with-resources/closeable模式中确保释放，异常发生时资源将永久泄漏。",
        "suggestion": "使用try-with-resources（Java）、using（C#）、with（Python）或defer（Go）确保资源释放；在finally中手动close。",
        "applicable_files": ["*.java","*.py","*.cs","*.go","*.js","*.ts"]
    },
    {
        "id": "B1-11-R002", "name": "数据库连接未关闭", "severity": "high",
        "category": "resource-leak",
        "description": "获取了数据库连接（Connection）但未在使用后关闭，连接池将被耗尽导致服务不可用。",
        "suggestion": "使用try-with-resources管理Connection；使用连接池并确保finally中关闭；使用ORM框架的自动连接管理。",
        "applicable_files": ["*.java","*.py","*.cs","*.go","*.js","*.ts"]
    },
    {
        "id": "B1-11-R003", "name": "HTTP响应体未消费/关闭", "severity": "medium",
        "category": "resource-leak",
        "description": "发起HTTP请求后未读取或关闭Response Body，底层连接无法被连接池复用，导致连接泄漏。",
        "suggestion": "使用defer response.Body.Close()（Go）；确保读取完响应体或在finally中关闭；使用try-with-resources。",
        "applicable_files": ["*.go","*.java","*.py","*.js","*.ts"]
    },
    {
        "id": "B1-11-R004", "name": "事件监听器未移除", "severity": "medium",
        "category": "resource-leak",
        "description": "注册了事件监听器（addEventListener/on）但在组件销毁/页面卸载时未移除，导致内存泄漏和重复触发。",
        "suggestion": "在组件unmount/dispose/destroy生命周期中移除所有监听器；使用AbortController管理。",
        "applicable_files": ["*.js","*.ts","*.vue","*.jsx","*.tsx"]
    },
    {
        "id": "B1-11-R005", "name": "定时器未清除", "severity": "medium",
        "category": "resource-leak",
        "description": "使用setTimeout/setInterval/setInterval创建了定时器但未在适当时机clearInterval/clearTimeout，导致内存泄漏或非预期执行。",
        "suggestion": "保存定时器ID，在组件销毁或不再需要时清除；在useEffect返回函数中清理。",
        "applicable_files": ["*.js","*.ts","*.vue","*.jsx","*.tsx"]
    }
]})

# B1-15 颜色对比度
save_json('web/accessibility_rules.json', {"rules": [
    {
        "id": "B1-15-R001", "name": "文本与背景颜色对比度不足(WCAG AA)", "severity": "medium",
        "category": "color-contrast",
        "description": "普通文本（<18px或<14px bold）与背景色的对比度低于4.5:1，不满足WCAG 2.1 AA标准，视障用户难以阅读。",
        "suggestion": "确保普通文本对比度≥4.5:1；大文本≥3:1；使用WebAIM Contrast Checker等工具验证颜色组合。",
        "applicable_files": ["*.css","*.scss","*.less","*.vue","*.jsx","*.tsx","*.html","*.wxml","*.wxss"]
    },
    {
        "id": "B1-15-R002", "name": "仅使用颜色传达信息", "severity": "medium",
        "category": "color-contrast",
        "description": "仅通过颜色差异来传达信息（如红色表示错误、绿色表示成功），色盲用户无法区分。",
        "suggestion": "除颜色外增加图标、文字标签或图案来传达信息；使用形状和纹理辅助区分。",
        "applicable_files": ["*.css","*.scss","*.vue","*.jsx","*.tsx","*.html","*.wxml"]
    },
    {
        "id": "B1-15-R003", "name": "占位符文本对比度不足", "severity": "low",
        "category": "color-contrast",
        "description": "表单placeholder文本颜色过浅，与输入框背景对比度不足，影响可读性。但注意placeholder不应替代label。",
        "suggestion": "确保placeholder颜色与背景对比度≥4.5:1（若需可读）；重要信息不要仅放在placeholder中。",
        "applicable_files": ["*.css","*.scss","*.vue","*.jsx","*.tsx","*.html","*.wxml"]
    },
    {
        "id": "B1-15-R004", "name": "交互元素焦点指示对比度不足", "severity": "medium",
        "category": "color-contrast",
        "description": "键盘焦点指示器（outline/focus ring）与周围颜色对比度不足3:1，键盘用户难以看到当前焦点位置。",
        "suggestion": "使用高对比度的focus样式；outline颜色与背景对比度≥3:1；不要使用outline:none替代为不可见的焦点样式。",
        "applicable_files": ["*.css","*.scss","*.less","*.vue","*.jsx","*.tsx"]
    }
]})

# ============================================================
# B2 - 安全扫描 缺失维度
# ============================================================

# B2-14 不安全直接对象引用(IDOR)
save_json('brain2_security/idor.json', {"rules": [
    {
        "id": "SEC-IDOR-001", "name": "IDOR：通过修改ID参数直接访问其他用户资源", "severity": "high",
        "category": "idor",
        "description": "API通过用户可控的ID参数（如/user/123/profile）直接访问资源，未验证当前用户是否有权访问该ID对应的资源，攻击者修改ID即可越权。",
        "suggestion": "在服务端验证请求用户与资源的归属关系；使用不可预测的资源标识符（UUID）；实现基于session的用户鉴权而非参数传递用户ID。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.php","*.cs"]
    },
    {
        "id": "SEC-IDOR-002", "name": "IDOR：批量枚举接口缺少防护", "severity": "high",
        "category": "idor",
        "description": "资源接口允许通过递增ID批量枚举所有资源（如/order/1、/order/2...），无任何频率限制或随机化。",
        "suggestion": "使用UUID替代自增ID；添加请求频率限制；实现服务端权限校验；对敏感接口增加验证码。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.php","*.cs"]
    },
    {
        "id": "SEC-IDOR-003", "name": "IDOR：引用令牌可预测", "severity": "medium",
        "category": "idor",
        "description": "使用可预测的引用令牌（如自增序号、时间戳、用户名）作为资源标识符，攻击者可轻易猜测其他资源的标识。",
        "suggestion": "使用CSPRNG生成的不可预测令牌；使用UUID v4；对引用令牌进行加密签名。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.php"]
    },
    {
        "id": "SEC-IDOR-004", "name": "IDOR：间接引用未校验所有权", "severity": "high",
        "category": "idor",
        "description": "通过间接引用（如购物车ID、订单号）访问资源时，仅校验引用有效性但未校验当前用户是否拥有该资源。",
        "suggestion": "在数据访问层加入所有权校验：SELECT * FROM orders WHERE id=? AND user_id=当前用户ID。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.php","*.cs"]
    }
]})

# B2-18 不安全设计
save_json('brain2_security/insecure_design.json', {"rules": [
    {
        "id": "SEC-DES-001", "name": "缺少业务逻辑校验：金额可为负数", "severity": "high",
        "category": "insecure-design",
        "description": "交易/支付接口允许传入负数金额，攻击者可通过负数金额反向获利（如退款-100元变为获得100元）。",
        "suggestion": "在服务端严格校验金额必须为正数；使用白名单校验所有数值输入；对金额计算使用Decimal类型。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs"]
    },
    {
        "id": "SEC-DES-002", "name": "缺少速率限制导致暴力破解", "severity": "high",
        "category": "insecure-design",
        "description": "登录、验证码发送、密码重置等敏感接口缺少请求速率限制，攻击者可无限次尝试暴力破解。",
        "suggestion": "实施IP级别和用户级别的速率限制；登录失败后递增延迟；验证码使用图形验证；5次失败后锁定账户。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs","*.php"]
    },
    {
        "id": "SEC-DES-003", "name": "信任边界不清晰：客户端数据直接用于安全决策", "severity": "high",
        "category": "insecure-design",
        "description": "将客户端传递的数据（如用户角色、权限级别、价格）直接用于安全决策，攻击者可篡改这些数据绕过安全检查。",
        "suggestion": "所有安全决策必须基于服务端状态；权限信息从session/token中获取而非客户端传递；价格从数据库查询而非前端传入。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs","*.php"]
    },
    {
        "id": "SEC-DES-004", "name": "缺少并发竞态保护（TOCTOU）", "severity": "high",
        "category": "insecure-design",
        "description": "先检查后执行（Time-of-Check-Time-of-Use）存在竞态条件，如检查余额>金额后再扣款，并发请求可能导致超额消费。",
        "suggestion": "使用数据库事务+行级锁（SELECT FOR UPDATE）；使用乐观锁（version字段）；使用分布式锁保护关键操作。",
        "applicable_files": ["*.java","*.py","*.go","*.cs","*.js","*.ts"]
    },
    {
        "id": "SEC-DES-005", "name": "密码重置流程设计缺陷", "severity": "high",
        "category": "insecure-design",
        "description": "密码重置使用可预测的token（如用户ID的hash）、token不过期、重置后旧token仍有效、或重置链接通过HTTP传输。",
        "suggestion": "使用CSPRNG生成重置token；设置短有效期（15分钟）；重置后立即使token失效；强制HTTPS传输。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs","*.php"]
    },
    {
        "id": "SEC-DES-006", "name": "缺少多因素认证(MFA)的高敏感操作", "severity": "medium",
        "category": "insecure-design",
        "description": "高敏感操作（如大额转账、管理员权限变更、API密钥生成）仅依赖单因素认证，缺少二次验证。",
        "suggestion": "为高敏感操作添加MFA验证（如短信验证码、TOTP、硬件密钥）；实现分级别的认证要求。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs"]
    }
]})

# B2-25 批量赋值(Mass Assignment)
save_json('brain2_security/mass_assignment.json', {"rules": [
    {
        "id": "SEC-MA-001", "name": "批量赋值：未限制可更新字段", "severity": "high",
        "category": "mass-assignment",
        "description": "将用户提交的JSON/表单数据直接绑定到模型对象进行创建/更新，攻击者可提交额外字段（如is_admin=true、role=admin）提升权限。",
        "suggestion": "使用白名单指定允许更新的字段（如Rails的strong parameters、Django的fields参数、Spring的@InitBinder）；创建专门的DTO对象。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs","*.php","*.rb"]
    },
    {
        "id": "SEC-MA-002", "name": "批量赋值：敏感字段未从序列化中排除", "severity": "high",
        "category": "mass-assignment",
        "description": "模型/实体类中包含不应由用户设置的字段（如password_hash、role、balance），但未通过注解或配置排除这些字段。",
        "suggestion": "使用@JsonIgnore（Jackson）、@Expose(serialize=false)等注解排除敏感字段；使用视图模型（ViewModel）分离输入输出。",
        "applicable_files": ["*.java","*.cs","*.py","*.ts"]
    },
    {
        "id": "SEC-MA-003", "name": "批量赋值：PATCH请求未过滤字段", "severity": "high",
        "category": "mass-assignment",
        "description": "PATCH/PUT接口将请求体全量映射到更新逻辑，允许攻击者修改不应变更的字段（如created_at、owner_id）。",
        "suggestion": "在更新前过滤请求字段，仅保留白名单中的字段；使用专门的Update DTO限制可修改属性。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs","*.php"]
    }
]})

# B2-26 业务逻辑安全
save_json('brain2_security/business_logic_security.json', {"rules": [
    {
        "id": "SEC-BL-001", "name": "业务逻辑：价格/数量未在服务端二次校验", "severity": "high",
        "category": "business-logic-security",
        "description": "订单金额完全依赖前端传入的价格和数量计算，服务端未进行二次校验，攻击可篡改请求以极低价格下单。",
        "suggestion": "服务端从数据库查询商品价格重新计算总价；数量与库存校验在服务端完成；不信任任何客户端传入的金额数据。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs","*.php"]
    },
    {
        "id": "SEC-BL-002", "name": "业务逻辑：优惠券/折扣可重复使用", "severity": "high",
        "category": "business-logic-security",
        "description": "优惠券/折扣码在核销后未标记为已使用，或并发请求可导致同一优惠券被多次核销。",
        "suggestion": "使用数据库事务+行锁保证原子性核销；核销前检查使用状态；限制每个用户/设备的使用次数。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs","*.php"]
    },
    {
        "id": "SEC-BL-003", "name": "业务逻辑：状态流转校验缺失", "severity": "high",
        "category": "business-logic-security",
        "description": "业务状态变更未校验前置状态（如已取消的订单重新支付、已发货的订单再次发货），可能导致业务数据不一致。",
        "suggestion": "在状态变更前校验当前状态是否允许该操作；使用状态机模式管理业务流程；添加状态转换白名单。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs"]
    },
    {
        "id": "SEC-BL-004", "name": "业务逻辑：缺少幂等性保护", "severity": "medium",
        "category": "business-logic-security",
        "description": "支付、转账等关键操作的API缺少幂等性保护，网络重试或恶意重放可能导致重复扣款。",
        "suggestion": "使用唯一请求ID（Idempotency-Key）确保操作幂等；在数据库层面使用唯一约束；返回已处理结果而非重复执行。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs"]
    },
    {
        "id": "SEC-BL-005", "name": "业务逻辑：库存扣减无并发保护", "severity": "high",
        "category": "business-logic-security",
        "description": "库存扣减使用先查后改的非原子操作，并发场景下可能出现超卖（卖出超过实际库存的数量）。",
        "suggestion": "使用数据库行锁（SELECT FOR UPDATE）；使用Redis原子递减；使用乐观锁版本号控制。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs"]
    }
]})

# ============================================================
# B3 - AI语义分析 缺失维度
# ============================================================

# B3-05 类型安全与类型错误
save_json('brain3_semantic/type_safety_rules.json', {"rules": [
    {
        "id": "B3-05-R001", "name": "隐式类型转换导致逻辑错误", "severity": "high",
        "category": "type-safety",
        "description": "使用==而非===进行JavaScript比较，隐式类型转换导致意外匹配（如0==''为true、null==undefined为true），产生逻辑错误。",
        "suggestion": "始终使用===和!==进行比较；启用TypeScript strict模式；使用ESLint的eqeqeq规则。",
        "applicable_files": ["*.js","*.ts"]
    },
    {
        "id": "B3-05-R002", "name": "不安全的类型断言/强转", "severity": "high",
        "category": "type-safety",
        "description": "使用as（TypeScript）、(Type)（C#）、强制类型转换将对象转为不兼容类型，运行时可能出现方法不存在或属性访问失败。",
        "suggestion": "使用类型守卫（type guard）进行运行时类型检查；使用instanceof判断；避免不必要的类型断言。",
        "applicable_files": ["*.ts","*.cs","*.java","*.cpp"]
    },
    {
        "id": "B3-05-R003", "name": "泛型参数推断错误", "severity": "medium",
        "category": "type-safety",
        "description": "泛型函数调用时未显式指定类型参数，编译器推断的类型与实际使用不匹配，导致后续操作类型不安全。",
        "suggestion": "显式指定泛型类型参数；检查推断结果是否符合预期；在复杂场景下使用类型注解明确约束。",
        "applicable_files": ["*.ts","*.java","*.cs","*.kotlin"]
    },
    {
        "id": "B3-05-R004", "name": "数值精度丢失", "severity": "high",
        "category": "type-safety",
        "description": "使用浮点数（float/double）进行金额、计数等精确计算，由于IEEE 754精度限制导致计算结果不准确（如0.1+0.2≠0.3）。",
        "suggestion": "使用Decimal/BigDecimal类型处理金额；整数运算使用最小单位（分）；比较浮点数时使用epsilon容差。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs","*.go"]
    },
    {
        "id": "B3-05-R005", "name": "any/Object类型滥用绕过类型系统", "severity": "medium",
        "category": "type-safety",
        "description": "大量使用any（TypeScript）、Object（Java）、interface{}（Go）等逃逸类型，绕过编译期类型检查，运行时可能出现类型错误。",
        "suggestion": "定义具体的接口/类型替代any；使用泛型约束替代Object；启用strict/strictNullChecks。",
        "applicable_files": ["*.ts","*.java","*.go","*.cs"]
    }
]})

# B3-07 资源生命周期管理
save_json('brain3_semantic/resource_lifecycle_rules.json', {"rules": [
    {
        "id": "B3-07-R001", "name": "复杂路径下的资源泄漏", "severity": "high",
        "category": "resource-lifecycle",
        "description": "在包含多个条件分支、异常处理路径的复杂代码中，某些路径上资源（文件、连接、锁）未被关闭，容易遗漏。",
        "suggestion": "使用语言提供的资源管理语法糖（try-with-resources/using/with/defer）；将资源获取和释放在同一作用域内管理。",
        "applicable_files": ["*.java","*.py","*.cs","*.go","*.js","*.ts"]
    },
    {
        "id": "B3-07-R002", "name": "双重释放/关闭资源", "severity": "medium",
        "category": "resource-lifecycle",
        "description": "同一资源在不同代码路径中被释放/关闭两次（如手动close后又触发defer close），可能导致panic或使用已释放资源。",
        "suggestion": "确保每个资源只有一个释放点；使用标志位跟踪释放状态；优先使用自动资源管理语法。",
        "applicable_files": ["*.go","*.c","*.cpp","*.java","*.py"]
    },
    {
        "id": "B3-07-R003", "name": "使用已释放的资源（Use-After-Free）", "severity": "critical",
        "category": "resource-lifecycle",
        "description": "资源（内存/文件/连接）被释放后仍被引用或使用，在C/C++中导致未定义行为，在其他语言中抛出异常。",
        "suggestion": "释放后立即将引用设为null；使用智能指针（shared_ptr/unique_ptr）管理生命周期；使用Rust的所有权模型。",
        "applicable_files": ["*.c","*.cpp","*.rust","*.go","*.java"]
    },
    {
        "id": "B3-07-R004", "name": "锁未在异常路径释放", "severity": "high",
        "category": "resource-lifecycle",
        "description": "获取锁后在try块中执行业务逻辑，但如果在获取锁之后、进入try之前或catch/finally中发生异常，锁可能永远不释放导致死锁。",
        "suggestion": "使用try-finally确保锁释放；使用上下文管理器（with语句）；使用defer unlock；将锁的获取和使用紧密绑定。",
        "applicable_files": ["*.java","*.py","*.go","*.cs","*.js","*.ts","*.c","*.cpp"]
    },
    {
        "id": "B3-07-R005", "name": "连接池中的连接未正确归还", "severity": "high",
        "category": "resource-lifecycle",
        "description": "从连接池获取的连接/会话在使用后未归还到池中（如异常退出时未释放），导致连接池耗尽。",
        "suggestion": "始终在finally/defer中归还连接；使用连接池的context manager；设置连接超时自动回收。",
        "applicable_files": ["*.java","*.py","*.go","*.cs","*.js","*.ts"]
    }
]})

# B3-08 算法正确性
save_json('brain3_semantic/algorithm_correctness_rules.json', {"rules": [
    {
        "id": "B3-08-R001", "name": "排序比较函数不满足全序关系", "severity": "high",
        "category": "algorithm-correctness",
        "description": "自定义排序比较函数不满足传递性、反对称性或完全性（如compare(a,b)>0且compare(b,c)>0但compare(a,c)<=0），导致排序结果不确定或崩溃。",
        "suggestion": "确保比较函数满足全序关系：自反性(a==a)、反对称性、传递性；使用标准库排序而非自实现。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs","*.go","*.cpp"]
    },
    {
        "id": "B3-08-R002", "name": "二分查找边界条件错误", "severity": "high",
        "category": "algorithm-correctness",
        "description": "二分查找中left/right初始化、循环条件（<vs<=）、中间值计算（溢出风险）或边界更新（left=mid vs left=mid+1）存在错误。",
        "suggestion": "使用left<=right标准模板；mid用left+(right-left)/2防溢出；仔细确认边界更新方向。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs","*.go","*.cpp","*.c"]
    },
    {
        "id": "B3-08-R003", "name": "递归缺少终止条件导致栈溢出", "severity": "critical",
        "category": "algorithm-correctness",
        "description": "递归函数缺少正确的基准条件（base case）或基准条件永远无法满足，导致无限递归最终StackOverflow。",
        "suggestion": "确保每个递归都有明确的终止条件；添加递归深度限制；考虑使用迭代+栈替代深递归。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs","*.go","*.cpp","*.c"]
    },
    {
        "id": "B3-08-R004", "name": "哈希表/Map的键类型使用不当", "severity": "medium",
        "category": "algorithm-correctness",
        "description": "使用浮点数、数组、对象等作为哈希键，由于浮点精度或引用比较语义导致查找失败；或使用可变对象作键，修改后无法检索。",
        "suggestion": "使用不可变类型作为哈希键；浮点数键使用整数化或字符串化；对象键使用JSON序列化或自定义hashCode。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs","*.go"]
    },
    {
        "id": "B3-08-R005", "name": "滑动窗口/双指针边界遗漏", "severity": "medium",
        "category": "algorithm-correctness",
        "description": "滑动窗口或双指针算法中，窗口边界更新条件不正确导致遗漏有效窗口或产生无效窗口（如空数组、单元素、全相同元素）。",
        "suggestion": "显式处理边界情况（空输入、单元素）；用测试用例验证窗口收缩/扩张条件；注意off-by-one错误。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs","*.go","*.cpp"]
    }
]})

# B3-09 状态机完整性
save_json('brain3_semantic/state_machine_rules.json', {"rules": [
    {
        "id": "B3-09-R001", "name": "状态转移缺少合法校验", "severity": "high",
        "category": "state-machine",
        "description": "状态变更时未校验当前状态是否允许转移到目标状态（如已完成的订单被标记为待支付），导致非法状态转换。",
        "suggestion": "定义合法的状态转移矩阵（state transition table）；在变更前校验当前状态是否在允许的转移源状态集合中。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs"]
    },
    {
        "id": "B3-09-R002", "name": "状态枚举不完整", "severity": "medium",
        "category": "state-machine",
        "description": "状态处理逻辑（switch/if-else链）未覆盖所有可能的状态值，新增状态后未更新处理逻辑导致静默忽略。",
        "suggestion": "使用穷举检查（exhaustive check）确保所有状态都有处理；对未处理状态抛出异常而非静默忽略。",
        "applicable_files": ["*.java","*.ts","*.cs","*.py","*.go"]
    },
    {
        "id": "B3-09-R003", "name": "状态初始化缺失", "severity": "high",
        "category": "state-machine",
        "description": "对象/实体的状态字段未设置初始值，首次使用时处于未定义状态，可能导致空指针或错误逻辑分支。",
        "suggestion": "在构造函数/初始化块中设置明确的初始状态；使用枚举类型约束状态值范围。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs"]
    },
    {
        "id": "B3-09-R004", "name": "并发状态更新冲突", "severity": "high",
        "category": "state-machine",
        "description": "多个线程/请求并发更新同一实体的状态字段，缺少乐观锁/悲观锁保护，可能导致状态跳跃或丢失更新。",
        "suggestion": "使用乐观锁（version字段+WHERE version=?）；使用CAS操作；使用状态机库保证原子转换。",
        "applicable_files": ["*.java","*.py","*.go","*.cs","*.js","*.ts"]
    }
]})

# B3-14 时间与日期处理
save_json('brain3_semantic/datetime_rules.json', {"rules": [
    {
        "id": "B3-14-R001", "name": "时区处理不当", "severity": "high",
        "category": "datetime",
        "description": "使用本地时间（LocalTime/LocalDateTime）存储跨时区数据，或在时区转换时未使用IANA时区标识符，导致时间错乱。",
        "suggestion": "内部统一使用UTC存储时间；显示时转换为用户本地时区；使用ZonedDateTime/OffsetDateTime带时区类型。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs"]
    },
    {
        "id": "B3-14-R002", "name": "日期格式解析不安全", "severity": "medium",
        "category": "datetime",
        "description": "使用不安全的日期解析方法（如SimpleDateFormat非线程安全、Date.parse宽松模式），可能解析出错误日期或抛出未处理异常。",
        "suggestion": "使用线程安全的DateTimeFormatter（Java）/ dayjs + 严格模式；显式指定格式模式；处理解析异常。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs"]
    },
    {
        "id": "B3-14-R003", "name": "时间比较使用错误方法", "severity": "medium",
        "category": "datetime",
        "description": "使用字符串比较日期（如'2024-01-01'>'2024-1-1'格式不一致导致错误）、或使用getTime()比较不同精度的时间戳。",
        "suggestion": "使用日期对象的原生比较方法（isBefore/isAfter/compareTo）；确保比较的时间精度一致。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs"]
    },
    {
        "id": "B3-14-R004", "name": "未处理闰年/夏令时边界", "severity": "low",
        "category": "datetime",
        "description": "日期计算中硬编码了每月天数（如365天/年、30天/月）未考虑闰年；或未处理夏令时切换时的时间跳跃。",
        "suggestion": "使用Duration/Period进行日期运算而非毫秒加减；使用java.time API自动处理夏令时；测试闰年边界。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs"]
    }
]})

# B3-15 文件I/O正确性
save_json('brain3_semantic/file_io_rules.json', {"rules": [
    {
        "id": "B3-15-R001", "name": "文件打开模式错误", "severity": "high",
        "category": "file-io",
        "description": "以只读模式打开文件后尝试写入、以文本模式读写二进制数据、或未指定编码导致乱码。",
        "suggestion": "根据操作目的选择正确的模式（r/w/a/rb/wb）；文本文件显式指定编码（UTF-8）；二进制文件使用二进制模式。",
        "applicable_files": ["*.py","*.js","*.ts","*.java","*.go","*.cs"]
    },
    {
        "id": "B3-15-R002", "name": "路径拼接不安全", "severity": "high",
        "category": "file-io",
        "description": "使用字符串拼接构造文件路径（如dir + '/' + filename），在不同操作系统上可能失败，且容易引入路径遍历漏洞。",
        "suggestion": "使用path.join（Node.js）、os.path.join/pathlib（Python）、Paths.get（Java）、filepath.Join（Go）等路径API。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.go","*.cs"]
    },
    {
        "id": "B3-15-R003", "name": "文件读写未处理大文件", "severity": "medium",
        "category": "file-io",
        "description": "使用readAllBytes/readFileSync等方法一次性将大文件读入内存，可能导致OOM（Out of Memory）。",
        "suggestion": "使用流式读取（Stream/Reader/BufferedReader）逐块处理；对大文件使用mmap或分块读取。",
        "applicable_files": ["*.java","*.js","*.ts","*.py","*.go","*.cs"]
    },
    {
        "id": "B3-15-R004", "name": "文件存在性检查与操作非原子（TOCTOU）", "severity": "medium",
        "category": "file-io",
        "description": "先检查文件是否存在（if exists）再打开操作，在检查和操作之间文件可能被其他进程删除或替换（竞态条件）。",
        "suggestion": "使用原子操作（如O_CREAT|O_EXCL）；使用try-catch处理文件不存在异常而非预先检查；使用文件锁。",
        "applicable_files": ["*.py","*.js","*.java","*.go","*.cs","*.c","*.cpp"]
    }
]})

# B3-16 正则表达式正确性
save_json('brain3_semantic/regex_correctness_rules.json', {"rules": [
    {
        "id": "B3-16-R001", "name": "正则表达式语法错误", "severity": "high",
        "category": "regex-correctness",
        "description": "正则表达式包含语法错误：未转义的特殊字符、未闭合的括号/方括号、无效的量词组合（如**或+?）等，运行时抛出异常。",
        "suggestion": "使用正则表达式测试工具验证语法；对特殊字符进行转义；使用RegExp.escape或等效方法处理动态输入。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.go","*.cs","*.rb","*.php"]
    },
    {
        "id": "B3-16-R002", "name": "贪婪匹配导致意外捕获", "severity": "medium",
        "category": "regex-correctness",
        "description": "使用贪婪量词（.*或.+）匹配HTML标签、引号内容等嵌套结构，导致匹配范围远超预期（如匹配整个文件而非单个标签）。",
        "suggestion": "使用非贪婪量词（.*?或.+?）；使用否定字符集（[^\"]*匹配引号内容）；对HTML/XML使用专用解析器而非正则。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.go","*.cs","*.rb"]
    },
    {
        "id": "B3-16-R003", "name": "捕获组引用错误", "severity": "medium",
        "category": "regex-correctness",
        "description": "正则中使用反向引用\\1但实际捕获组数量不匹配，或在替换字符串中使用$1但组不存在，导致运行时错误或替换结果异常。",
        "suggestion": "确认捕获组编号与引用一致；使用命名捕获组（(?P<name>...)）提高可读性和正确性。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.go","*.cs","*.rb"]
    },
    {
        "id": "B3-16-R004", "name": "Unicode/多字节字符处理不当", "severity": "medium",
        "category": "regex-correctness",
        "description": "使用.匹配字符时未启用Unicode标志（u/s），无法正确匹配emoji、 surrogate pairs等多字节字符；或使用\\w无法匹配中文等Unicode字符。",
        "suggestion": "处理Unicode文本时启用u标志（JavaScript）或re.UNICODE（Python）；使用\\p{L}匹配Unicode字母。",
        "applicable_files": ["*.js","*.ts","*.py","*.java"]
    },
    {
        "id": "B3-16-R005", "name": "字符集范围定义错误", "severity": "medium",
        "category": "regex-correctness",
        "description": "字符集中范围写反（如[z-a]）导致匹配空集或抛出错误；或范围过大（如[0-z]包含了不期望的特殊字符）。",
        "suggestion": "检查字符集范围的起止顺序；避免使用过宽的字符范围；明确列出需要的字符而非使用宽范围。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.go","*.cs","*.rb"]
    }
]})

# B3-18 测试语义审查
save_json('brain3_semantic/test_semantic_rules.json', {"rules": [
    {
        "id": "B3-18-R001", "name": "测试断言缺失或无意义", "severity": "medium",
        "category": "test-semantic",
        "description": "测试方法中没有断言（assert），或仅有toBeTruthy()等弱断言，无法验证实际业务逻辑是否正确。",
        "suggestion": "每个测试至少有一个明确的断言验证预期行为；使用精确的断言方法（toEqual/toBe/toContain）而非模糊断言。",
        "applicable_files": ["*.test.js","*.test.ts","*.spec.js","*.spec.ts","*Test.java","*_test.py","*_test.go"]
    },
    {
        "id": "B3-18-R002", "name": "测试之间存在依赖/执行顺序敏感", "severity": "high",
        "category": "test-semantic",
        "description": "测试用例依赖其他测试的执行结果（如共享可变状态、依赖数据库中的数据、依赖全局变量的前一个测试设置），并行或乱序执行时失败。",
        "suggestion": "每个测试独立设置和清理环境（beforeEach/afterEach）；使用测试fixture或factory创建独立数据；避免共享可变状态。",
        "applicable_files": ["*.test.js","*.test.ts","*.spec.*","*Test.java","*_test.py","*_test.go"]
    },
    {
        "id": "B3-18-R003", "name": "测试过度mock导致无法验证真实行为", "severity": "medium",
        "category": "test-semantic",
        "description": "测试中mock了几乎所有依赖，mock的返回值与真实实现行为不一致，测试通过但实际代码仍有bug。",
        "suggestion": "仅mock外部依赖（网络、数据库、第三方API）；对内部逻辑使用真实实现；增加集成测试验证真实行为。",
        "applicable_files": ["*.test.*","*.spec.*","*Test.java","*_test.py","*_test.go"]
    },
    {
        "id": "B3-18-R004", "name": "测试仅覆盖happy path", "severity": "medium",
        "category": "test-semantic",
        "description": "测试用例仅覆盖了正常路径（happy path），未覆盖边界条件、错误路径、异常情况，无法发现防御性编程的缺陷。",
        "suggestion": "补充边界值测试（空值、最大值、最小值）；补充错误路径测试（网络失败、权限不足、数据不存在）；使用等价类划分。",
        "applicable_files": ["*.test.*","*.spec.*","*Test.java","*_test.py","*_test.go"]
    },
    {
        "id": "B3-18-R005", "name": "测试中包含硬编码的敏感信息", "severity": "high",
        "category": "test-semantic",
        "description": "测试代码中硬编码了真实的API密钥、数据库密码、生产环境URL等敏感信息，可能随代码提交到版本库泄露。",
        "suggestion": "使用环境变量或测试配置文件管理敏感信息；使用mock/fake服务替代真实外部服务；CI中使用secrets管理。",
        "applicable_files": ["*.test.*","*.spec.*","*Test.java","*_test.py","*_test.go","conftest.py"]
    }
]})

# B3-20 重构建议生成
save_json('brain3_semantic/refactor_suggestion_rules.json', {"rules": [
    {
        "id": "B3-20-R001", "name": "可用策略模式替代的条件分支", "severity": "low",
        "category": "refactor-suggestion",
        "description": "存在大量if-else/switch分支且每个分支执行不同的策略逻辑，适合用策略模式替代以提高可扩展性。",
        "suggestion": "将每个分支逻辑提取为独立的策略类/函数；使用Map/字典映射条件到策略；新增场景时只需添加新策略无需修改主逻辑。",
        "applicable_files": ["*.java","*.ts","*.py","*.cs","*.go"]
    },
    {
        "id": "B3-20-R002", "name": "可用建造者模式替代的长参数列表", "severity": "low",
        "category": "refactor-suggestion",
        "description": "构造函数或方法参数超过5个且包含多个可选参数，可读性差且容易传错参数顺序。",
        "suggestion": "使用Builder模式逐步构建对象；或将参数封装为配置对象（Config/Options）；使用命名参数/关键字参数。",
        "applicable_files": ["*.java","*.ts","*.cs","*.py","*.go"]
    },
    {
        "id": "B3-20-R003", "name": "可用模板方法消除重复的算法骨架", "severity": "low",
        "category": "refactor-suggestion",
        "description": "多个子类中存在相同的方法骨架（步骤序列），仅部分步骤实现不同，适合使用模板方法模式提取公共骨架。",
        "suggestion": "在基类中定义模板方法，将不变步骤放在基类，可变步骤定义为抽象方法由子类实现。",
        "applicable_files": ["*.java","*.cs","*.ts","*.py"]
    },
    {
        "id": "B3-20-R004", "name": "可用观察者模式解耦事件处理", "severity": "low",
        "category": "refactor-suggestion",
        "description": "模块间通过直接调用紧密耦合，一个操作需要通知多个模块执行不同逻辑，适合用观察者/事件模式解耦。",
        "suggestion": "引入事件总线（EventBus）或发布-订阅模式；操作只发布事件，由订阅者各自响应；降低模块间耦合度。",
        "applicable_files": ["*.java","*.ts","*.py","*.cs","*.go"]
    },
    {
        "id": "B3-20-R005", "name": "提取函数消除重复代码块", "severity": "medium",
        "category": "refactor-suggestion",
        "description": "相同的代码逻辑出现在多处（≥2次），每次修改需同步更新所有副本，容易遗漏导致不一致。",
        "suggestion": "将重复代码提取为独立函数/方法；通过参数化差异部分保持灵活性；确保提取后的函数职责单一。",
        "applicable_files": ["*.java","*.js","*.ts","*.py","*.cs","*.go","*.rb","*.php"]
    }
]})

# ============================================================
# B4 - 性能分析 缺失维度
# ============================================================

# B4-02 字符串操作性能
save_json('brain4_performance/perf_string_rules.json', {"rules": [
    {
        "id": "PERF-STR-001", "name": "循环中使用+拼接字符串", "severity": "medium",
        "category": "string-performance",
        "description": "在循环中使用+=拼接字符串，每次拼接创建新的String对象，时间复杂度为O(n²)。Java/Python中尤其严重。",
        "suggestion": "Java使用StringBuilder；Python使用''.join(list)；JavaScript使用数组push后join；Go使用strings.Builder。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go"]
    },
    {
        "id": "PERF-STR-002", "name": "频繁创建正则表达式对象", "severity": "medium",
        "category": "string-performance",
        "description": "在函数内部或循环中重复创建相同模式的RegExp/Pattern对象，正则编译开销被重复执行。",
        "suggestion": "将正则表达式提升为模块级常量（const REGEX = /pattern/）；使用Pattern.compile缓存（Java）；复用已编译的正则对象。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs","*.go"]
    },
    {
        "id": "PERF-STR-003", "name": "大字符串使用substring反复切割", "severity": "medium",
        "category": "string-performance",
        "description": "对大字符串反复使用substring/slice进行切割处理，每次切割都创建新字符串副本，内存和时间开销大。",
        "suggestion": "使用split一次性分割；使用正则的matchAll迭代匹配；使用StringReader/BufferedReader流式处理。",
        "applicable_files": ["*.java","*.js","*.ts","*.py","*.cs","*.go"]
    },
    {
        "id": "PERF-STR-004", "name": "不必要的字符串编解码转换", "severity": "low",
        "category": "string-performance",
        "description": "在数据处理链路中反复进行字符串与Buffer/Bytes的转换（如string→Buffer→string→Buffer），每次转换都涉及内存分配和拷贝。",
        "suggestion": "统一数据格式，减少不必要的编解码；在流处理中保持Buffer形式直到最终需要字符串时再转换。",
        "applicable_files": ["*.js","*.ts","*.py","*.go","*.java"]
    },
    {
        "id": "PERF-STR-005", "name": "模板字符串在循环中反复编译", "severity": "low",
        "category": "string-performance",
        "description": "使用模板引擎（Handlebars/EJS/Jinja2）在循环中反复编译同一模板字符串，模板解析开销被重复。",
        "suggestion": "预编译模板为函数，循环中只执行渲染；使用模板缓存机制。",
        "applicable_files": ["*.js","*.ts","*.py","*.java"]
    },
    {
        "id": "PERF-STR-006", "name": "使用indexOf替代includes/includes的性能差异", "severity": "low",
        "category": "string-performance",
        "description": "在仅需判断存在性的场景使用indexOf !== -1而非includes，虽然功能等价但includes语义更清晰且在现代引擎中有优化。",
        "suggestion": "使用includes/some进行存在性判断；使用startsWith/endsWith替代substring比较。",
        "applicable_files": ["*.js","*.ts"]
    }
]})

# B4-03 集合与数据结构选择
save_json('brain4_performance/perf_collection_rules.json', {"rules": [
    {
        "id": "PERF-COL-001", "name": "使用数组进行频繁的查找/包含判断", "severity": "medium",
        "category": "collection-performance",
        "description": "使用Array/List的includes/contains进行频繁的查找操作，时间复杂度为O(n)；当数据量大且查找频繁时应使用Set/Map（O(1)）。",
        "suggestion": "将频繁查找的数组转换为Set（new Set(arr)）；需要键值查找时使用Map；对于有序数据使用二分查找。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs","*.go"]
    },
    {
        "id": "PERF-COL-002", "name": "在数组头部频繁插入/删除元素", "severity": "medium",
        "category": "collection-performance",
        "description": "使用Array.unshift()或在List头部插入/删除元素，每次操作需要移动所有后续元素，时间复杂度O(n)。",
        "suggestion": "使用链表（LinkedList）替代数组实现队列；或使用双端队列（Deque）；在尾部操作后reverse。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs"]
    },
    {
        "id": "PERF-COL-003", "name": "在循环中使用filter/map链式创建新数组", "severity": "medium",
        "category": "collection-performance",
        "description": "对大数组连续使用多个filter/map/reduce，每次调用都创建新数组并遍历整个数据集，内存和时间开销倍增。",
        "suggestion": "合并多个filter/map为单次遍历；使用for-of循环减少中间数组创建；对超大数据集考虑使用生成器/迭代器。",
        "applicable_files": ["*.js","*.ts"]
    },
    {
        "id": "PERF-COL-004", "name": "使用Object/Map作为队列（FIFO）", "severity": "low",
        "category": "collection-performance",
        "description": "使用数组的shift()实现FIFO队列，每次shift操作O(n)；高频操作场景下性能较差。",
        "suggestion": "使用双指针实现环形队列；使用专门的Queue/Deque数据结构；或使用链表实现。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs","*.go"]
    },
    {
        "id": "PERF-COL-005", "name": "大集合的排序未指定比较函数", "severity": "low",
        "category": "collection-performance",
        "description": "对包含数字的数组使用sort()但未提供比较函数，JavaScript默认按字符串字典序排序（如10排在2前面）。",
        "suggestion": "始终为sort提供比较函数：arr.sort((a,b) => a-b)；或使用localeCompare处理字符串排序。",
        "applicable_files": ["*.js","*.ts"]
    },
    {
        "id": "PERF-COL-006", "name": "集合遍历中使用索引而非迭代器", "severity": "low",
        "category": "collection-performance",
        "description": "对LinkedList等链表结构使用索引访问（list.get(i)），每次get从头遍历，总体O(n²)。",
        "suggestion": "使用迭代器/增强for循环遍历链表结构；对需要随机访问的场景使用ArrayList。",
        "applicable_files": ["*.java","*.cs"]
    }
]})

# B4-05 不必要的对象创建
save_json('brain4_performance/perf_object_creation_rules.json', {"rules": [
    {
        "id": "PERF-OBJ-001", "name": "循环内创建不必要的临时对象", "severity": "medium",
        "category": "object-creation-performance",
        "description": "在循环体内反复创建可复用的对象（如DateFormat、Random、Pattern、StringBuilder等），造成大量短生命周期对象，增加GC压力。",
        "suggestion": "将可复用对象提升到循环外部；使用对象池复用高频创建的对象；使用ThreadLocal管理非线程安全对象。",
        "applicable_files": ["*.java","*.js","*.ts","*.py","*.cs","*.go"]
    },
    {
        "id": "PERF-OBJ-002", "name": "自动装箱/拆箱产生多余对象", "severity": "low",
        "category": "object-creation-performance",
        "description": "在循环中频繁使用Integer/Long等包装类型进行算术运算，每次运算触发自动装箱创建新对象。",
        "suggestion": "使用基本类型（int/long/double）进行密集计算；使用原始类型集合（如TIntList、Eclipse Collections）。",
        "applicable_files": ["*.java","*.cs","*.kt"]
    },
    {
        "id": "PERF-OBJ-003", "name": "函数调用时创建不必要的配置对象", "severity": "low",
        "category": "object-creation-performance",
        "description": "每次函数调用都创建新的配置/选项对象，但配置值在多次调用间不变。",
        "suggestion": "将不变配置提取为常量/模块级变量；使用默认参数替代配置对象；使用对象冻结（Object.freeze）复用。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs"]
    },
    {
        "id": "PERF-OBJ-004", "name": "过度使用深拷贝", "severity": "medium",
        "category": "object-creation-performance",
        "description": "使用JSON.parse(JSON.stringify(obj))或lodash.cloneDeep进行深拷贝，但实际只需要浅拷贝或只读访问。",
        "suggestion": "评估是否真正需要深拷贝；使用Object.assign/展开运算符进行浅拷贝；使用Object.freeze使对象只读避免意外修改。",
        "applicable_files": ["*.js","*.ts","*.py"]
    },
    {
        "id": "PERF-OBJ-005", "name": "日志/调试语句中创建不必要的字符串", "severity": "low",
        "category": "object-creation-performance",
        "description": "在日志语句中使用字符串拼接/模板字符串（如log.debug('data: ' + JSON.stringify(obj))），即使日志级别不满足也会创建字符串。",
        "suggestion": "使用延迟求值的日志API（如log.debug(() -> 'data: ' + obj)）；先检查日志级别再构造消息。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs"]
    }
]})

# B4-10 无用计算与重复计算
save_json('brain4_performance/perf_redundant_computation_rules.json', {"rules": [
    {
        "id": "PERF-RED-001", "name": "循环内重复计算不变表达式", "severity": "medium",
        "category": "redundant-computation",
        "description": "在循环体内计算不依赖循环变量的表达式（如Math.sqrt(constant)、数组长度arr.length、配置查询等），每次迭代重复计算。",
        "suggestion": "将循环不变量提升到循环外部（hoisting）；预先计算并缓存结果。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs","*.go","*.c","*.cpp"]
    },
    {
        "id": "PERF-RED-002", "name": "可缓存的纯函数被反复调用", "severity": "medium",
        "category": "redundant-computation",
        "description": "相同的纯函数（相同输入总是相同输出）被反复调用，如数据转换、格式化处理等，每次重新计算。",
        "suggestion": "使用Memoization缓存纯函数结果；React中使用useMemo/useCallback；后端使用本地缓存（Map/LRU Cache）。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs","*.go"]
    },
    {
        "id": "PERF-RED-003", "name": "重复的数据库/API查询", "severity": "high",
        "category": "redundant-computation",
        "description": "在同一请求处理链路中多次查询相同的数据（如用户信息、配置数据），未使用请求级缓存。",
        "suggestion": "使用请求级缓存（Request-scoped Cache）；使用DataLoader批量加载；将共享数据注入上下文对象。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs","*.go"]
    },
    {
        "id": "PERF-RED-004", "name": "条件分支中计算未使用的结果", "severity": "low",
        "category": "redundant-computation",
        "description": "在if-else分支中两侧都计算了相同的值，或计算了某个值但在条件不满足时该值未被使用。",
        "suggestion": "将计算移入实际使用它的条件分支中；提前返回避免不必要的计算。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs","*.go"]
    },
    {
        "id": "PERF-RED-005", "name": "对同一数据反复排序", "severity": "medium",
        "category": "redundant-computation",
        "description": "对同一数据集在多处反复排序，或排序后未缓存结果，后续又需要相同排序顺序的数据。",
        "suggestion": "排序一次并缓存结果；使用预排序的数据结构（如TreeSet/SortedMap）；维护排序后的索引。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs","*.go"]
    }
]})

# B4-11 正则表达式性能
save_json('brain4_performance/perf_regex_rules.json', {"rules": [
    {
        "id": "PERF-REG-001", "name": "正则表达式存在灾难性回溯风险", "severity": "high",
        "category": "regex-performance",
        "description": "正则表达式包含嵌套量词（如(a+)+或(a|a)*）或重叠的交替分支，对特定输入可能产生指数级回溯（ReDoS）。",
        "suggestion": "消除嵌套量词；使用原子组（atomic group）或占有量词（possessive quantifier）；使用非回溯正则引擎（如RE2）。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs","*.go","*.rb"]
    },
    {
        "id": "PERF-REG-002", "name": "使用正则处理可用字符串方法解决的简单匹配", "severity": "low",
        "category": "regex-performance",
        "description": "使用正则表达式进行简单的字符串查找/替换（如查找固定子串、判断前后缀），可用更高效的原生方法替代。",
        "suggestion": "使用indexOf/includes替代/substring/.test()；使用startsWith/endsWith替代正则锚点；使用split替代正则切割。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs","*.go"]
    },
    {
        "id": "PERF-REG-003", "name": "正则表达式过度使用通配符", "severity": "medium",
        "category": "regex-performance",
        "description": "正则中使用.*或[\\s\\S]*匹配大段文本，引擎需要大量回溯尝试，尤其在多行文本中性能急剧下降。",
        "suggestion": "使用更精确的字符集替代.（如[^<]*替代.*?匹配HTML内容）；使用[^\\n]*替代.*匹配单行。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs","*.go"]
    },
    {
        "id": "PERF-REG-004", "name": "大文本上反复执行正则匹配", "severity": "medium",
        "category": "regex-performance",
        "description": "对大文本（如整个文件内容）反复执行正则匹配/替换，每次都需要从头扫描整个文本。",
        "suggestion": "合并多个正则为一次扫描；使用流式处理逐行匹配；对固定位置的提取使用substring而非正则。",
        "applicable_files": ["*.js","*.ts","*.py","*.java","*.cs","*.go"]
    }
]})

# B4-16 序列化/反序列化性能
save_json('brain4_performance/perf_serialization_rules.json', {"rules": [
    {
        "id": "PERF-SER-001", "name": "使用反射式序列化框架处理大数据量", "severity": "medium",
        "category": "serialization-performance",
        "description": "使用JSON.stringify/parse、Java原生序列化、Python pickle等反射式框架处理大量数据，反射开销在大数据量场景下显著。",
        "suggestion": "对高频序列化场景使用Protocol Buffers/MessagePack/FlatBuffers等二进制格式；或使用代码生成替代反射。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go"]
    },
    {
        "id": "PERF-SER-002", "name": "序列化包含大量不必要字段", "severity": "medium",
        "category": "serialization-performance",
        "description": "序列化整个实体对象时包含大量不需要的字段（如密码hash、大文本字段、关联对象），增加网络传输和内存开销。",
        "suggestion": "使用DTO/VO只包含需要的字段；使用@JsonIgnore排除不必要的字段；实现按需字段选择。",
        "applicable_files": ["*.java","*.ts","*.py","*.cs","*.go"]
    },
    {
        "id": "PERF-SER-003", "name": "反序列化未使用流式解析处理大数据", "severity": "medium",
        "category": "serialization-performance",
        "description": "使用DOM式解析（如JSON.parse、xml.etree）处理大型JSON/XML文件，将整个文档加载到内存中构建树结构。",
        "suggestion": "使用SAX/StAX流式解析（Java）；使用JSON Stream/ijson逐条处理（Python）；使用stream-json逐块解析（Node.js）。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go"]
    }
]})

# ============================================================
# B5 - 依赖审计 缺失维度
# ============================================================

# B5-05 恶意包检测
save_json('brain5_deps/dependency_malware.json', {"rules": [
    {
        "id": "DEP-MAL-001", "name": "疑似Typosquatting恶意包", "severity": "critical",
        "category": "dependency_malware",
        "description": "依赖包名称与知名包高度相似但存在拼写差异（如lodash→1odash、event-stream→event-streams），可能是恶意仿冒包。",
        "suggestion": "仔细核对包名拼写；检查包的发布者和下载量；使用npm audit或Snyk扫描已知恶意包。",
        "applicable_files": ["package.json","requirements.txt","pom.xml","go.mod","Gemfile","*.csproj"]
    },
    {
        "id": "DEP-MAL-002", "name": "依赖包包含可疑的安装脚本", "severity": "critical",
        "category": "dependency_malware",
        "description": "依赖包的postinstall/preinstall脚本执行可疑操作（如下载外部二进制、访问加密货币矿池、窃取环境变量）。",
        "suggestion": "审查postinstall脚本内容；使用--ignore-scripts跳过安装脚本；使用npm audit检查已知恶意包。",
        "applicable_files": ["package.json"]
    },
    {
        "id": "DEP-MAL-003", "name": "依赖包发布者可信度低", "severity": "medium",
        "category": "dependency_malware",
        "description": "依赖包由新注册的账户发布、发布者无其他公开包、或包名与知名组织相似但发布者不匹配。",
        "suggestion": "验证包发布者的npm/GitHub身份；检查包的发布历史和版本模式；对比官方注册表中的发布者信息。",
        "applicable_files": ["package.json","requirements.txt","pom.xml","go.mod"]
    },
    {
        "id": "DEP-MAL-004", "name": "依赖包体积异常或与描述不符", "severity": "medium",
        "category": "dependency_malware",
        "description": "依赖包的实际大小远超同类包的正常范围，或包内包含混淆代码、加密数据、可执行文件等异常内容。",
        "suggestion": "使用Bundlephobia检查包大小；审查包内文件列表；对混淆代码保持警惕。",
        "applicable_files": ["package.json","requirements.txt","pom.xml","go.mod"]
    }
]})

# B5-06 SBOM生成与管理
save_json('brain5_deps/dependency_sbom.json', {"rules": [
    {
        "id": "DEP-SBOM-001", "name": "项目缺少SBOM（软件物料清单）", "severity": "medium",
        "category": "dependency_sbom",
        "description": "项目未生成或维护SBOM文件，无法快速了解项目完整的依赖树（含传递依赖），影响漏洞响应和合规审计效率。",
        "suggestion": "使用CDX（CycloneDX）或SPDX格式生成SBOM；集成到CI/CD管道自动生成；每次发版时更新SBOM。",
        "applicable_files": ["package.json","pom.xml","go.mod","requirements.txt","*.csproj"]
    },
    {
        "id": "DEP-SBOM-002", "name": "SBOM与实际依赖不同步", "severity": "medium",
        "category": "dependency_sbom",
        "description": "SBOM文件存在但未随依赖变更更新，记录的组件版本与实际使用的版本不一致，影响漏洞排查的准确性。",
        "suggestion": "将SBOM生成集成到CI/CD管道中自动执行；每次依赖变更后重新生成SBOM；使用自动化工具（如cyclonedx-cli）校验一致性。",
        "applicable_files": ["*.sbom.json","*.spdx","bom.json","bom.xml"]
    },
    {
        "id": "DEP-SBOM-003", "name": "SBOM缺少关键元数据", "severity": "low",
        "category": "dependency_sbom",
        "description": "SBOM文件中缺少组件的版本号、许可证信息、来源（purl）等关键元数据，降低SBOM的实用价值。",
        "suggestion": "确保每个组件包含：名称、版本、purl（Package URL）、许可证、hash值；使用SBOM生成工具自动填充。",
        "applicable_files": ["*.sbom.json","*.spdx","bom.json","bom.xml"]
    }
]})

# B5-07 漏洞可利用性评估
save_json('brain5_deps/dependency_exploitability.json', {"rules": [
    {
        "id": "DEP-EXP-001", "name": "已知漏洞但当前代码路径未触发", "severity": "low",
        "category": "dependency_exploitability",
        "description": "依赖存在已知CVE漏洞，但项目中仅使用了该库的部分功能，漏洞代码路径可能未被实际调用，实际风险低于CVE评级。",
        "suggestion": "分析漏洞的触发条件（如特定函数、特定参数）；确认项目中是否调用了受影响代码路径；如未触发可降低优先级但仍应计划升级。",
        "applicable_files": ["package.json","pom.xml","go.mod","requirements.txt","*.csproj"]
    },
    {
        "id": "DEP-EXP-002", "name": "漏洞利用成熟度评估缺失", "severity": "medium",
        "category": "dependency_exploitability",
        "description": "仅依赖CVSS评分评估漏洞严重性，未考虑漏洞的实际利用成熟度（Exploit Maturity），如是否有公开PoC、是否已被在野利用。",
        "suggestion": "参考Snyk/EPSS评分评估实际可利用性；区分有公开exploit的高危漏洞和理论上的高危漏洞；优先修复已被在野利用的漏洞。",
        "applicable_files": ["package.json","pom.xml","go.mod","requirements.txt"]
    },
    {
        "id": "DEP-EXP-003", "name": "漏洞影响范围未评估", "severity": "medium",
        "category": "dependency_exploitability",
        "description": "已知依赖存在漏洞但未评估该漏洞在项目中的实际影响范围（多少服务使用、是否暴露在外网、涉及的数据敏感度）。",
        "suggestion": "评估受影响服务的暴露面（内网vs外网）；评估涉及数据的敏感度；根据实际影响确定修复优先级。",
        "applicable_files": ["package.json","pom.xml","go.mod","requirements.txt"]
    }
]})

# B5-09 传递依赖风险
save_json('brain5_deps/dependency_transitive.json', {"rules": [
    {
        "id": "DEP-TRANS-001", "name": "传递依赖中存在高危漏洞", "severity": "high",
        "category": "dependency_transitive",
        "description": "直接依赖的子依赖（传递依赖）中存在高危CVE漏洞，虽然直接依赖本身无漏洞，但传递依赖的漏洞同样影响应用安全。",
        "suggestion": "运行npm audit/mvn dependency:analyze检查传递依赖漏洞；升级直接依赖到已修复传递依赖漏洞的版本；使用overrides/resolutions强制指定安全版本。",
        "applicable_files": ["package.json","pom.xml","go.mod","requirements.txt","*.csproj"]
    },
    {
        "id": "DEP-TRANS-002", "name": "依赖树过深（传递链过长）", "severity": "medium",
        "category": "dependency_transitive",
        "description": "依赖树嵌套层级过深（>5层），传递依赖数量远超直接依赖，增加了供应链攻击面和版本冲突风险。",
        "suggestion": "审查并替换依赖链过长的包；使用更轻量的替代包；使用peerDependencies减少嵌套。",
        "applicable_files": ["package.json","pom.xml","go.mod","requirements.txt"]
    },
    {
        "id": "DEP-TRANS-003", "name": "传递依赖版本冲突（Diamond Dependency）", "severity": "medium",
        "category": "dependency_transitive",
        "description": "多个直接依赖引用同一传递依赖的不同版本（菱形依赖），可能导致运行时行为不一致或功能缺失。",
        "suggestion": "使用resolutions/overrides统一传递依赖版本；升级直接依赖到兼容同一传递依赖版本的组合。",
        "applicable_files": ["package.json","pom.xml","go.mod","requirements.txt"]
    },
    {
        "id": "DEP-TRANS-004", "name": "传递依赖缺少版本锁定", "severity": "medium",
        "category": "dependency_transitive",
        "description": "传递依赖未在lock文件中锁定精确版本，安装时可能获取到不兼容的新版本，导致构建不可复现。",
        "suggestion": "确保lock文件（package-lock.json、poetry.lock、go.sum）提交到版本控制；使用确定性安装命令。",
        "applicable_files": ["package.json","pom.xml","go.mod","requirements.txt"]
    }
]})

# B5-11 漏洞修复建议
save_json('brain5_deps/dependency_remediation.json', {"rules": [
    {
        "id": "DEP-REM-001", "name": "漏洞依赖有可用安全版本但未升级", "severity": "high",
        "category": "dependency_remediation",
        "description": "依赖存在已知CVE漏洞且已有修复版本发布，但项目仍使用受影响版本，存在可利用的安全风险。",
        "suggestion": "升级到安全版本；如存在breaking change，评估迁移工作量并制定升级计划；使用npm audit fix自动修复。",
        "applicable_files": ["package.json","pom.xml","go.mod","requirements.txt","*.csproj"]
    },
    {
        "id": "DEP-REM-002", "name": "漏洞依赖无修复版本且无替代方案", "severity": "critical",
        "category": "dependency_remediation",
        "description": "依赖存在高危漏洞但维护者已停止维护，无安全版本可用，项目面临持续的安全风险。",
        "suggestion": "寻找功能等价的替代包；fork并自行维护安全补丁；部署WAF/运行时防护作为临时缓解措施。",
        "applicable_files": ["package.json","pom.xml","go.mod","requirements.txt"]
    },
    {
        "id": "DEP-REM-003", "name": "升级依赖未进行兼容性验证", "severity": "medium",
        "category": "dependency_remediation",
        "description": "为修复漏洞升级依赖版本但未运行测试验证兼容性，可能引入新的bug或breaking change。",
        "suggestion": "升级后运行完整测试套件；查阅CHANGELOG确认breaking changes；使用Dependabot/Renovate自动创建PR并运行CI。",
        "applicable_files": ["package.json","pom.xml","go.mod","requirements.txt","*.csproj"]
    }
]})

# B5-12 许可证义务追踪
save_json('brain5_deps/dependency_license_obligation.json', {"rules": [
    {
        "id": "DEP-LIC-OB-001", "name": "GPL许可证义务未履行（需开源）", "severity": "critical",
        "category": "dependency_license_obligation",
        "description": "项目使用了GPL许可证的依赖并以二进制形式分发，但未将项目源码以GPL许可证开放，违反GPL的传染性条款。",
        "suggestion": "评估是否可以将项目开源为GPL；如不可以，替换GPL依赖为LGPL/MIT/Apache等许可的替代包；或采用SaaS模式（AGPL需注意网络交互）。",
        "applicable_files": ["package.json","pom.xml","go.mod","requirements.txt","LICENSE"]
    },
    {
        "id": "DEP-LIC-OB-002", "name": "Apache 2.0/MIT许可证的署名义务未满足", "severity": "medium",
        "category": "dependency_license_obligation",
        "description": "使用了Apache 2.0或MIT许可证的依赖，但在分发时未包含原始版权声明和许可证文本，违反许可证要求。",
        "suggestion": "在产品通知文件（NOTICES）中包含所有依赖的许可证文本和版权声明；使用license-checker工具自动生成。",
        "applicable_files": ["NOTICE","LICENSE","package.json","pom.xml"]
    },
    {
        "id": "DEP-LIC-OB-003", "name": "专利声明义务未追踪", "severity": "low",
        "category": "dependency_license_obligation",
        "description": "Apache 2.0许可证要求明确标注专利授权范围，但未追踪哪些依赖包含专利条款，可能影响专利纠纷中的权益。",
        "suggestion": "维护依赖的专利声明清单；评估依赖是否包含专利授权条款；咨询法务确认专利风险。",
        "applicable_files": ["package.json","pom.xml","go.mod","NOTICE"]
    }
]})

# B5-13 依赖瘦身优化
save_json('brain5_deps/dependency_optimization.json', {"rules": [
    {
        "id": "DEP-OPT-001", "name": "存在未使用的依赖", "severity": "medium",
        "category": "dependency_optimization",
        "description": "package.json/requirements.txt/pom.xml中声明的依赖在代码中未被import或使用，增加了安装时间和供应链风险。",
        "suggestion": "使用depcheck（JS）/pipdeptree（Python）/mvn dependency:analyze（Java）检测未使用依赖；从配置文件中移除。",
        "applicable_files": ["package.json","requirements.txt","pom.xml","go.mod","*.csproj","Gemfile"]
    },
    {
        "id": "DEP-OPT-002", "name": "可使用更轻量替代的依赖", "severity": "low",
        "category": "dependency_optimization",
        "description": "引入了功能庞大但仅使用少量功能的依赖包（如引入lodash全库但只用了map和filter、引入moment.js但只用了格式化）。",
        "suggestion": "使用按需引入（lodash-es/map）或更轻量的替代（dayjs替代moment、date-fns替代moment、原生方法替代underscore）。",
        "applicable_files": ["package.json","requirements.txt","pom.xml","go.mod"]
    },
    {
        "id": "DEP-OPT-003", "name": "devDependencies混入生产依赖", "severity": "medium",
        "category": "dependency_optimization",
        "description": "将仅开发时使用的依赖（如测试框架、类型定义、构建工具）放在了dependencies而非devDependencies中，增加生产包体积。",
        "suggestion": "将测试框架（jest/mocha）、类型定义（@types/*）、构建工具（webpack/eslint）移到devDependencies；使用npm install --production部署。",
        "applicable_files": ["package.json"]
    }
]})

# ============================================================
# B6 - 代码质量 缺失维度
# ============================================================

# B6-07 内聚性度量
save_json('brain6_code_quality/cohesion_rules.json', {"rules": [
    {
        "id": "CQ-COH-001", "name": "类内聚性缺失（LCOM过高）", "severity": "medium",
        "category": "cohesion",
        "description": "类中存在多组方法各自使用不同的字段集合，组间无共享数据（LCOM值高），表明类承担了多个不相关的职责。",
        "suggestion": "将低内聚的类拆分为多个高内聚的类，每个类专注于一个职责；使用Extract Class重构。",
        "applicable_files": ["*.java","*.cs","*.py","*.ts","*.go"]
    },
    {
        "id": "CQ-COH-002", "name": "类的字段仅被单个方法使用", "severity": "low",
        "category": "cohesion",
        "description": "类中定义了多个私有字段，但每个字段仅被一个方法使用，这些字段和方法应该提取为独立的类或作为方法局部变量。",
        "suggestion": "将仅被单个方法使用的字段和方法提取到独立类中；或将其降级为方法内局部变量。",
        "applicable_files": ["*.java","*.cs","*.py","*.ts"]
    },
    {
        "id": "CQ-COH-003", "name": "模块功能分散缺乏统一主题", "severity": "medium",
        "category": "cohesion",
        "description": "模块/文件中导出的函数/类涉及多个不相关的业务领域（如同时处理用户认证和日志格式化），缺乏功能内聚性。",
        "suggestion": "按业务领域重新组织模块；每个模块/文件应有一个明确统一的主题（功能性内聚）。",
        "applicable_files": ["*.js","*.ts","*.py","*.go","*.java","*.cs"]
    }
]})

# B6-10 错误的抽象层次
save_json('brain6_code_quality/abstraction_rules.json', {"rules": [
    {
        "id": "CQ-ABS-001", "name": "高层模块混入底层实现细节", "severity": "medium",
        "category": "abstraction-level",
        "description": "高层业务逻辑函数中直接包含底层实现细节（如在业务Service中直接拼接SQL字符串、操作DOM、处理HTTP字节流），违反关注点分离。",
        "suggestion": "将底层实现细节下沉到专门的模块/层中；高层模块只调用抽象接口；遵循依赖倒置原则。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go"]
    },
    {
        "id": "CQ-ABS-002", "name": "同一函数内混合不同抽象层级的操作", "severity": "medium",
        "category": "abstraction-level",
        "description": "一个函数中同时包含高层业务操作（如validateOrder）和底层技术操作（如parseDate、concatString），阅读者需要不断切换思维层级。",
        "suggestion": "将不同层级的操作提取到独立的函数中；保持每个函数在同一抽象层级；使用Step Down规则（每个函数下一层只调用同层或更低层的函数）。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go"]
    },
    {
        "id": "CQ-ABS-003", "name": "接口定义包含实现相关概念", "severity": "medium",
        "category": "abstraction-level",
        "description": "接口/抽象类的定义中暴露了实现细节（如方法参数使用具体类型而非抽象类型、返回值暴露数据库实体）。",
        "suggestion": "接口使用抽象类型定义；返回DTO而非数据库实体；接口定义应描述'做什么'而非'怎么做'。",
        "applicable_files": ["*.java","*.cs","*.ts","*.go"]
    },
    {
        "id": "CQ-ABS-004", "name": "配置/环境变量硬编码在业务逻辑中", "severity": "medium",
        "category": "abstraction-level",
        "description": "业务逻辑中硬编码了具体的配置值（如URL、超时时间、阈值），这些本应属于配置层而非业务逻辑层。",
        "suggestion": "将配置值提取到配置文件或常量类中；通过依赖注入传入配置；业务逻辑只依赖抽象配置接口。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go"]
    }
]})

# B6-11 过长参数列表
save_json('brain6_code_quality/parameter_rules.json', {"rules": [
    {
        "id": "CQ-PARAM-001", "name": "函数参数超过4个", "severity": "medium",
        "category": "parameter-list",
        "description": "函数/方法参数数量超过4个，增加了调用复杂度和出错概率（参数顺序混淆），且通常表明函数职责过多。",
        "suggestion": "将相关参数封装为参数对象（Parameter Object）；拆分为多个职责更单一的函数；使用Builder模式。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go","*.c","*.cpp"]
    },
    {
        "id": "CQ-PARAM-002", "name": "多个连续的同类型参数", "severity": "medium",
        "category": "parameter-list",
        "description": "函数有多个连续的同类型参数（如3个string、4个number），调用时极易混淆参数顺序。",
        "suggestion": "使用对象/字典传参替代位置参数；或使用命名参数（Python kwargs、Kotlin命名参数）。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go"]
    },
    {
        "id": "CQ-PARAM-003", "name": "布尔参数控制函数行为分支", "severity": "medium",
        "category": "parameter-list",
        "description": "函数接收布尔参数来决定执行不同的逻辑分支（如process(flag ? 'a' : 'b')），表明函数实际承担了两个职责。",
        "suggestion": "将布尔分支拆为两个独立的函数（如processA()和processB()）；或使用策略模式。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go"]
    }
]})

# B6-12 过大类/上帝类
save_json('brain6_code_quality/god_class_rules.json', {"rules": [
    {
        "id": "CQ-GC-001", "name": "上帝类/过大类", "severity": "high",
        "category": "god-class",
        "description": "类的方法数量超过20个或代码行数超过500行，包含了过多职责，违反单一职责原则，任何修改都可能影响其他功能。",
        "suggestion": "按职责拆分为多个小类；使用Extract Class重构；将相关方法分组到内部类或辅助类中。",
        "applicable_files": ["*.java","*.cs","*.py","*.ts","*.go"]
    },
    {
        "id": "CQ-GC-002", "name": "类的字段数量过多", "severity": "medium",
        "category": "god-class",
        "description": "类定义了超过10个实例字段，通常表明类管理了过多的状态，不同字段组可能服务于不同的职责。",
        "suggestion": "识别字段组（总是被同一组方法使用的字段），将每组提取为独立类；减少字段间的隐式耦合。",
        "applicable_files": ["*.java","*.cs","*.py","*.ts"]
    },
    {
        "id": "CQ-GC-003", "name": "类的公共方法过多暴露内部细节", "severity": "medium",
        "category": "god-class",
        "description": "类的公共方法过多（>15个），暴露了大量内部操作，外部调用者需要深入了解类的内部结构才能正确使用。",
        "suggestion": "减少公共方法数量，隐藏内部实现细节；使用Facade模式提供简化的外部接口；将辅助方法改为private。",
        "applicable_files": ["*.java","*.cs","*.py","*.ts","*.go"]
    },
    {
        "id": "CQ-GC-004", "name": "工具类/Utils类方法过多", "severity": "medium",
        "category": "god-class",
        "description": "Utils/Helper类积累了大量不相关的方法（StringUtils、DateUtils、CommonUtils等变成了垃圾桶），职责不明确。",
        "suggestion": "按领域拆分工具类（如UserValidator、PaymentFormatter）；将方法移到其操作的对象上（面向对象）；定期清理不再使用的方法。",
        "applicable_files": ["*.java","*.cs","*.py","*.ts","*.go"]
    }
]})

# B6-13 shotgun surgery & B6-14 数据泥团 → 追加到 bad_smell 文件
save_json('brain6_code_quality/bad_smell_extra_rules.json', {"rules": [
    {
        "id": "CQ-BS-EXT-001", "name": "散弹式修改：一个变更需修改多个类的多处代码", "severity": "high",
        "category": "code-smell-extra",
        "description": "每次需求变更都需要修改多个不同类中的多个方法（如添加新字段需修改Model、DTO、Controller、Service中各一处），代码组织不利于维护。",
        "suggestion": "将分散的相关行为集中到一个类中（Inline Class）；使用策略模式或模板方法减少分散修改；考虑是否可以使用配置驱动。",
        "applicable_files": ["*.java","*.cs","*.py","*.ts","*.go"]
    },
    {
        "id": "CQ-BS-EXT-002", "name": "数据泥团：相同的数据项在多处结伴出现", "severity": "medium",
        "category": "code-smell-extra",
        "description": "相同的3个或以上数据项（如firstName/lastName/phone、x/y/z坐标）总是同时出现在多个函数参数、类字段中，表明缺少对应的值对象。",
        "suggestion": "将数据泥团提取为值对象（Value Object）或记录类型（Record/struct）；如Address(name, phone, city)替代三个独立参数。",
        "applicable_files": ["*.java","*.cs","*.py","*.ts","*.go","*.c"]
    },
    {
        "id": "CQ-BS-EXT-003", "name": "过长方法（超过50行）", "severity": "medium",
        "category": "code-smell-extra",
        "description": "方法体超过50行代码，通常包含多个逻辑步骤混在一起，难以理解、测试和维护。",
        "suggestion": "将方法按逻辑步骤拆分为多个小方法；每个方法只做一件事；方法名应清晰表达其意图。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go","*.c","*.cpp","*.rb"]
    }
]})

# B6-16 可维护性评分
save_json('brain6_code_quality/maintainability_score_rules.json', {"rules": [
    {
        "id": "CQ-MS-001", "name": "可维护性评分综合报告", "severity": "medium",
        "category": "maintainability-score",
        "description": "综合认知复杂度、代码行数、重复率、测试覆盖率、依赖耦合度等指标，输出A-F等级的可维护性评分，帮助快速定位质量瓶颈。",
        "suggestion": "对D/F级模块优先进行重构；设定最低可维护性等级标准（如C级以上）；每个迭代改进一个低分模块。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go","*.cpp","*.c"]
    },
    {
        "id": "CQ-MS-002", "name": "质量门禁：新增代码可维护性不达标", "severity": "medium",
        "category": "maintainability-score",
        "description": "本次提交/PR中新增的代码可维护性指标低于团队设定的质量门禁阈值（如复杂度>15、重复率>5%）。",
        "suggestion": "在CI中集成质量门禁检查；新增代码必须满足可维护性要求后才可合并；对不达标代码要求重构。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go"]
    },
    {
        "id": "CQ-MS-003", "name": "可维护性退化检测", "severity": "medium",
        "category": "maintainability-score",
        "description": "与上一版本相比，模块的可维护性指标明显退化（复杂度增加>20%、重复率增加>5%），表明代码质量正在恶化。",
        "suggestion": "对比版本间的可维护性指标变化；对退化严重的模块安排重构sprint；建立质量退化告警机制。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go"]
    }
]})

# B6-21 重构建议
save_json('brain6_code_quality/refactor_rules.json', {"rules": [
    {
        "id": "CQ-REF-001", "name": "提供具体重构方案", "severity": "low",
        "category": "refactor",
        "description": "对检测到的代码坏味道提供具体的重构方案，包括重构类型（Extract Method/Move Class等）、步骤和预期效果。",
        "suggestion": "为每个坏味道推荐具体的重构手法；提供重构前后的代码示例；标注重构的风险点和测试建议。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go"]
    },
    {
        "id": "CQ-REF-002", "name": "重构优先级排序", "severity": "low",
        "category": "refactor",
        "description": "根据代码坏味道的严重程度、影响范围和修复成本，对重构建议进行优先级排序，帮助开发者决定处理顺序。",
        "suggestion": "按ROI（影响面/工作量）排序重构项；优先处理高风险模块（如核心业务逻辑、频繁变更模块）。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go"]
    },
    {
        "id": "CQ-REF-003", "name": "安全重构检查清单", "severity": "low",
        "category": "refactor",
        "description": "在执行重构前检查是否具备安全重构的前提条件（充分测试覆盖、版本控制、小步重构等），降低重构引入新bug的风险。",
        "suggestion": "确认测试覆盖率>70%再进行重构；每次只做一种重构；重构后运行完整测试；使用IDE的重构工具而非手动修改。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go"]
    },
    {
        "id": "CQ-REF-004", "name": "重构时机识别", "severity": "low",
        "category": "refactor",
        "description": "识别适合进行重构的时机（如功能开发完成后的整理期、bug修复时的周边改进、团队迭代回顾中的技术债务评审）。",
        "suggestion": "遵循童子军规则（每次离开时让代码比来时更干净）；在每个sprint预留重构时间；利用代码审查触发重构讨论。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go"]
    }
]})

# B6-22 代码质量趋势
save_json('brain6_code_quality/quality_trend_rules.json', {"rules": [
    {
        "id": "CQ-QT-001", "name": "代码质量指标趋势跟踪", "severity": "low",
        "category": "quality-trend",
        "description": "跟踪代码质量关键指标（复杂度均值、重复率、测试覆盖率、问题密度）的时间序列变化，识别质量改善或退化趋势。",
        "suggestion": "每周/每个sprint生成质量趋势报告；设定质量基线和改善目标；对持续退化的模块及时干预。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go"]
    },
    {
        "id": "CQ-QT-002", "name": "新引入vs存量问题区分", "severity": "medium",
        "category": "quality-trend",
        "description": "区分本次变更新引入的质量问题和历史存量问题，帮助团队聚焦于防止质量退化而非被存量问题淹没。",
        "suggestion": "使用Leak Period（如SonarQube的New Code概念）只统计新增代码的问题；存量问题制定专项清理计划。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go"]
    },
    {
        "id": "CQ-QT-003", "name": "质量债务增长率告警", "severity": "medium",
        "category": "quality-trend",
        "description": "当代码质量债务的增长速度超过修复速度时发出告警，表明技术债务正在失控累积。",
        "suggestion": "设定技术债务增长率阈值（如每月新增>修复的150%时告警）；将债务控制纳入Definition of Done。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.cs","*.go"]
    }
]})

# ============================================================
# B7 - 架构合规 缺失维度
# ============================================================

# B7-06 ADR(架构决策记录)合规
save_json('brain7_architecture/adr_rules.json', {"rules": [
    {
        "id": "ARCH-ADR-001", "name": "代码实现与架构决策记录不一致", "severity": "high",
        "category": "adr-compliance",
        "description": "架构决策记录（ADR）明确要求使用特定技术/模式（如'使用消息队列解耦订单和库存'），但代码实现未遵循该决策。",
        "suggestion": "定期审查ADR与代码实现的一致性；将ADR作为代码审查的参考标准；偏离ADR需要新的决策记录说明原因。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs","*.md"]
    },
    {
        "id": "ARCH-ADR-002", "name": "重要架构变更缺少ADR", "severity": "medium",
        "category": "adr-compliance",
        "description": "引入了重要的架构级变更（如新增中间件、改变通信协议、引入新的存储方案）但未创建对应的架构决策记录。",
        "suggestion": "为每个重要架构决策创建ADR文档；记录背景、选项对比、决策理由和后果；ADR与代码变更一起提交。",
        "applicable_files": ["*.java","*.py","*.js","*.ts","*.go","*.cs","*.md"]
    },
    {
        "id": "ARCH-ADR-003", "name": "ADR状态未更新", "severity": "low",
        "category": "adr-compliance",
        "description": "代码中已经废弃或替换了某个架构决策对应的实现（如从REST迁移到gRPC），但ADR仍标记为Accepted（已采纳）而非Superseded（已替代）。",
        "suggestion": "废弃架构决策时更新ADR状态为Deprecated/Superseded；创建新ADR记录替代方案；维护ADR索引目录。",
        "applicable_files": ["*.md","*.java","*.py","*.js","*.ts","*.go"]
    }
]})

# B7-09 依赖注入合规
save_json('brain7_architecture/di_rules.json', {"rules": [
    {
        "id": "ARCH-DI-001", "name": "使用Service Locator反模式替代依赖注入", "severity": "medium",
        "category": "dependency-injection",
        "description": "类内部直接通过全局注册表/服务定位器（如ApplicationContext.getBean()、Injector.get()）获取依赖，而非通过构造函数/方法注入。",
        "suggestion": "使用构造函数注入替代Service Locator；依赖应通过参数传入而非内部查找；使依赖关系显式化。",
        "applicable_files": ["*.java","*.cs","*.ts","*.py"]
    },
    {
        "id": "ARCH-DI-002", "name": "直接new依赖对象而非注入", "severity": "medium",
        "category": "dependency-injection",
        "description": "类中直接使用new关键字创建依赖对象（如new UserService()、new DatabaseConnection()），而非通过依赖注入获取，导致无法替换/mock。",
        "suggestion": "使用构造函数注入依赖；使用工厂模式创建复杂对象；使用DI框架管理生命周期。",
        "applicable_files": ["*.java","*.cs","*.ts","*.py","*.go"]
    },
    {
        "id": "ARCH-DI-003", "name": "依赖注入的作用域不当", "severity": "medium",
        "category": "dependency-injection",
        "description": "将短生命周期组件注入到长生命周期组件中（如将Request-scoped的Bean注入到Singleton中），可能导致状态泄漏或过期引用。",
        "suggestion": "确保注入的依赖生命周期≥宿主组件；使用Provider/Lazy injection延迟获取；检查DI框架的作用域配置。",
        "applicable_files": ["*.java","*.cs","*.ts"]
    }
]})

# B7-10 架构腐化趋势
save_json('brain7_architecture/architecture_decay_rules.json', {"rules": [
    {
        "id": "ARCH-DECAY-001", "name": "架构违规数量趋势增长", "severity": "high",
        "category": "architecture-decay",
        "description": "架构违规检测数量随时间持续增长（如分层违规从10个增长到50个），表明架构约束未被遵守，架构正在腐化。",
        "suggestion": "建立架构违规数量基线和阈值；每个sprint回顾违规趋势；新增违规必须在当前sprint修复；将架构合规纳入DoD。",
        "applicable_files": ["*.java","*.cs","*.py","*.ts","*.go"]
    },
    {
        "id": "ARCH-DECAY-002", "name": "新增架构违规检测", "severity": "medium",
        "category": "architecture-decay",
        "description": "本次变更引入了新的架构违规（如新的跨层调用、新的循环依赖），这些违规如果不及时修复将加速架构腐化。",
        "suggestion": "在CI中添加架构合规检查（ArchUnit/dependency-cruiser）；新增违规必须立即修复或记录例外。",
        "applicable_files": ["*.java","*.cs","*.py","*.ts","*.go"]
    },
    {
        "id": "ARCH-DECAY-003", "name": "模块间耦合度持续增加", "severity": "medium",
        "category": "architecture-decay",
        "description": "模块间的依赖关系数量和强度随时间持续增加，模块边界逐渐模糊，系统趋向单体化。",
        "suggestion": "定期测量模块间耦合度指标；设定耦合度增长上限；对高耦合模块进行拆分或引入抽象层解耦。",
        "applicable_files": ["*.java","*.cs","*.py","*.ts","*.go"]
    }
]})

# B7-11 领域模型纯度
save_json('brain7_architecture/domain_purity_rules.json', {"rules": [
    {
        "id": "ARCH-DOM-001", "name": "领域层包含基础设施代码", "severity": "high",
        "category": "domain-purity",
        "description": "领域层（Domain Layer）的代码中直接引用了基础设施相关类（如数据库连接、HTTP客户端、文件系统操作、消息队列），违反Clean Architecture/DDD原则。",
        "suggestion": "在领域层定义接口（Repository/Gateway），在基础设施层实现；领域层只能依赖抽象而非具体实现；使用依赖倒置。",
        "applicable_files": ["*.java","*.cs","*.py","*.ts","*.go"]
    },
    {
        "id": "ARCH-DOM-002", "name": "领域对象包含持久化注解", "severity": "medium",
        "category": "domain-purity",
        "description": "领域模型/实体类上直接使用了持久化框架的注解（如@Entity、@Table、@Column），将领域逻辑与持久化关注点耦合。",
        "suggestion": "使用独立的持久化映射配置（如Fluent NHibernate、Flyway migration）；或将领域对象与数据库实体分离（CQRS模式）。",
        "applicable_files": ["*.java","*.cs","*.ts","*.py"]
    },
    {
        "id": "ARCH-DOM-003", "name": "领域事件包含技术实现细节", "severity": "medium",
        "category": "domain-purity",
        "description": "领域事件类中包含了技术实现细节（如HTTP响应码、数据库字段名、JSON序列化配置），应只描述业务语义。",
        "suggestion": "领域事件只包含业务含义明确的属性；技术细节在事件处理层（Application/Infrastructure）转换。",
        "applicable_files": ["*.java","*.cs","*.py","*.ts","*.go"]
    },
    {
        "id": "ARCH-DOM-004", "name": "领域服务依赖外部服务", "severity": "high",
        "category": "domain-purity",
        "description": "领域服务（Domain Service）直接依赖外部服务（如发送邮件、调用第三方API），应通过领域事件或应用服务协调。",
        "suggestion": "领域服务只包含纯业务逻辑；外部服务调用提升到应用服务层；使用领域事件解耦跨限界上下文的操作。",
        "applicable_files": ["*.java","*.cs","*.py","*.ts","*.go"]
    }
]})

print("\n✅ 所有缺口维度规则生成完成！")
