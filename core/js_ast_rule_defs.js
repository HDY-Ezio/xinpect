// ============================================================
// 规则实现
// ============================================================

const RULES = {
  // ===== React Hooks 规则 =====
  
  'HOOKS-001': {
    name: 'Hook 调用不在函数组件或自定义 Hook 中',
    severity: 'error',
    description: 'React Hook 只能在函数组件或自定义 Hook 中调用',
  },
  
  'HOOKS-002': {
    name: 'Hook 调用在条件判断/循环中',
    severity: 'error',
    description: 'React Hook 不能在条件判断、循环或嵌套函数中调用，必须在函数顶层',
  },
  
  'HOOKS-003': {
    name: 'useEffect 缺少依赖数组',
    severity: 'warning',
    description: 'useEffect 未指定依赖数组，每次渲染都会执行',
  },
  
  'HOOKS-004': {
    name: 'useEffect 依赖数组不完整',
    severity: 'warning',
    description: 'useEffect 回调中使用了外部变量但未列入依赖数组',
  },
  
  'HOOKS-005': {
    name: 'useCallback/useMemo 缺少依赖数组或依赖不完整',
    severity: 'warning',
    description: 'useCallback/useMemo 的依赖数组缺失或不完整',
  },
  
  'HOOKS-006': {
    name: 'Hook 返回值未使用',
    severity: 'warning',
    description: 'Hook 返回值未被使用（如 useState 的 setter 未使用）',
  },
  
  'HOOKS-007': {
    name: 'useEffect 中直接调用异步函数导致竞态',
    severity: 'warning',
    description: 'useEffect 的回调函数不应直接是 async 函数，应在内部定义 async 函数并调用',
  },
  
  'HOOKS-008': {
    name: 'useState 初始值为复杂计算未用函数式初始化',
    severity: 'info',
    description: 'useState 初始值为复杂计算时应使用函数式初始化以避免每次渲染都执行',
  },
  
  // ===== TypeScript 类型规则 =====
  
  'TS-001': {
    name: 'any 类型使用',
    severity: 'warning',
    description: '使用 any 类型会破坏 TypeScript 类型安全',
  },
  
  'TS-002': {
    name: '非空断言 ! 滥用',
    severity: 'warning',
    description: '非空断言 ! 会绕过类型检查，可能导致运行时错误',
  },
  
  'TS-003': {
    name: 'ts-ignore/ts-expect-error 无注释',
    severity: 'info',
    description: '@ts-ignore 或 @ts-expect-error 指令应附带说明注释',
  },
  
  // ===== JS 质量规则 =====
  
  'JS-001': {
    name: '未使用的变量/导入',
    severity: 'warning',
    description: '存在未使用的变量或导入，应移除以保持代码整洁',
  },
  
  'JS-002': {
    name: '使用 == 而非 ===',
    severity: 'warning',
    description: '使用 == 会导致隐式类型转换，建议使用 ===',
  },
  
  'JS-003': {
    name: 'eval() 使用',
    severity: 'error',
    description: 'eval() 存在安全风险且性能较差',
  },
  
  'JS-004': {
    name: 'console.log 遗留',
    severity: 'info',
    description: '生产代码中应移除 console.log 调试语句',
  },
  
  'JS-005': {
    name: '空代码块',
    severity: 'info',
    description: '空的代码块可能是未完成的实现',
  },
};


// ============================================================

module.exports = { RULES };
