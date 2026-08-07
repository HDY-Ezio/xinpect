/**
 * Hook 规则检查函数集
 * 
 * 从 CallExpression visitor 中抽取的 Hook 规则实现
 * 每个规则独立函数，早返回风格，降低嵌套
 */

const {
  isHookCall, getHookName, getDepArray,
  extractDepIdentifiers, getClosureVariables, GLOBAL_IGNORE_SET,
  collectSetStateSetters, isInValidHookContext, isInConditionalOrLoop,
} = require('./js_ast_hook_utils.js');
const { isComplexComputation } = require('./js_ast_analysis.js');

// ============================================================
// Hook 规则检查函数
// ============================================================

function _checkHooksRules(path, node, hookName, enabledRules, addIssue) {
  _checkHookContext(path, node, hookName, enabledRules, addIssue);
  _checkUseEffectDeps(path, node, hookName, enabledRules, addIssue);
  _checkMemoDep(path, node, hookName, enabledRules, addIssue);
  _checkUseEffectAsync(node, hookName, enabledRules, addIssue);
  _checkUseStateInit(node, hookName, enabledRules, addIssue);
}

function _checkHookContext(path, node, hookName, enabledRules, addIssue) {
  // HOOKS-001: 检查是否在合法上下文中
  if (enabledRules.has('HOOKS-001') && !isInValidHookContext(path)) {
    addIssue('HOOKS-001', node, 
      `Hook ${hookName} 的调用不在 React 函数组件或自定义 Hook 中`,
      '将 Hook 调用移至 React 函数组件或自定义 Hook 内');
  }
  // HOOKS-002: 检查是否在条件/循环中
  if (enabledRules.has('HOOKS-002') && isInValidHookContext(path) && isInConditionalOrLoop(path)) {
    addIssue('HOOKS-002', node,
      `Hook ${hookName} 在条件判断或循环中调用，破坏了 Hook 调用顺序`,
      '将 Hook 调用移至函数组件顶层，避免在条件或循环中调用');
  }
}

function _checkUseEffectDeps(path, node, hookName, enabledRules, addIssue) {
  if (hookName !== 'useEffect') return;
  const { deps, hasDepsArg } = getDepArray(node);
  
  // HOOKS-003: useEffect 缺少依赖数组
  if (enabledRules.has('HOOKS-003') && !hasDepsArg) {
    addIssue('HOOKS-003', node,
      'useEffect 缺少依赖数组，每次渲染都会执行',
      '如果确实不需要依赖，传入空数组 [] 表示仅在挂载时执行');
    return;
  }
  
  // HOOKS-004: useEffect 依赖不完整
  if (!enabledRules.has('HOOKS-004')) return;
  if (!hasDepsArg || deps === null || node.arguments.length === 0) return;
  
  const callback = node.arguments[0];
  if (!callback) return;
  if (callback.type !== 'ArrowFunctionExpression' && callback.type !== 'FunctionExpression') return;
  
  const missing = _findMissingDeps(path, callback, deps);
  if (missing.length === 0) return;
  
  addIssue('HOOKS-004', node,
    `useEffect 依赖数组缺少: ${missing.join(', ')}`,
    `请将 ${missing.join(', ')} 添加到依赖数组中，或使用 useRef/useCallback 处理`);
}

function _checkMemoDep(path, node, hookName, enabledRules, addIssue) {
  if (hookName !== 'useCallback' && hookName !== 'useMemo') return;
  if (!enabledRules.has('HOOKS-005')) return;
  
  const { deps, hasDepsArg } = getDepArray(node);
  
  if (!hasDepsArg) {
    addIssue('HOOKS-005', node,
      `${hookName} 缺少依赖数组`,
      `${hookName} 应提供依赖数组以控制缓存失效条件`);
    return;
  }
  
  if (deps === null || node.arguments.length === 0) return;
  
  const callback = node.arguments[0];
  if (!callback) return;
  if (callback.type !== 'ArrowFunctionExpression' && callback.type !== 'FunctionExpression') return;
  
  const missing = _findMissingDeps(path, callback, deps);
  if (missing.length === 0) return;
  
  addIssue('HOOKS-005', node,
    `${hookName} 依赖数组缺少: ${missing.join(', ')}`,
    `请将 ${missing.join(', ')} 添加到依赖数组中`);
}

function _findMissingDeps(path, callback, deps) {
  const closureVars = getClosureVariables(path, callback);
  const depNames = new Set(extractDepIdentifiers(deps));
  const missing = closureVars.filter(v => !depNames.has(v));
  const setStateSetters = collectSetStateSetters(path);
  return missing.filter(v => 
    !GLOBAL_IGNORE_SET.has(v) &&
    !setStateSetters.has(v) &&
    v !== 'dispatch'
  );
}

function _checkUseEffectAsync(node, hookName, enabledRules, addIssue) {
  if (!enabledRules.has('HOOKS-007')) return;
  if (hookName !== 'useEffect') return;
  const args = node.arguments || [];
  if (args.length === 0) return;
  const callback = args[0];
  if (!callback) return;
  if (callback.type !== 'ArrowFunctionExpression' && callback.type !== 'FunctionExpression') return;
  if (!callback.async) return;
  addIssue('HOOKS-007', callback,
    'useEffect 回调直接为 async 函数，可能导致竞态条件和清理问题',
    '在 useEffect 内部定义 async 函数并调用，同时返回清理函数');
}

function _checkUseStateInit(node, hookName, enabledRules, addIssue) {
  if (!enabledRules.has('HOOKS-008')) return;
  if (hookName !== 'useState') return;
  const args = node.arguments || [];
  if (args.length === 0) return;
  const init = args[0];
  if (!isComplexComputation(init)) return;
  addIssue('HOOKS-008', init,
    'useState 初始值为复杂计算，应使用函数式初始化避免每次渲染都执行',
    '改为 useState(() => computeValue()) 形式');
}

function _checkEvalCall(node, enabledRules, addIssue) {
  if (!enabledRules.has('JS-003')) return;
  const callee = node.callee;
  if (callee.type !== 'Identifier' || callee.name !== 'eval') return;
  addIssue('JS-003', node,
    '使用了 eval() 函数，存在安全风险和性能问题',
    '避免使用 eval，考虑使用 JSON.parse 或其他安全方案');
}

function _checkConsoleLog(node, enabledRules, addIssue) {
  if (!enabledRules.has('JS-004')) return;
  const callee = node.callee;
  if (callee.type !== 'MemberExpression') return;
  if (!callee.object || callee.object.type !== 'Identifier' || callee.object.name !== 'console') return;
  if (!callee.property || callee.property.type !== 'Identifier') return;
  if (!['log', 'debug', 'info'].includes(callee.property.name)) return;
  addIssue('JS-004', node,
    `console.${callee.property.name} 调试语句`,
    '生产代码应移除或通过环境变量控制 console 输出');
}


module.exports = {
  _checkHooksRules,
  _checkEvalCall,
  _checkConsoleLog,
};
