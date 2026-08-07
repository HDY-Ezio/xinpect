/**
 * React Hook 识别与上下文分析工具
 * 
 * Hook 调用判断、函数组件识别、依赖数组处理、
 * 闭包变量分析、setState setter 收集等
 */

const { babelTraverse } = require('./js_ast_babel.js');
const { collectIdentifiers, collectPatternNames } = require('./js_ast_utils.js');

/**
 * 判断函数节点是否为 React 函数组件
 * 条件：函数名首字母大写 且 返回 JSX
 */
function isReactFunctionComponent(path) {
  const node = path.node;
  let name = '';
  
  if (node.type === 'FunctionDeclaration') {
    name = node.id ? node.id.name : '';
  } else if (node.type === 'FunctionExpression' || node.type === 'ArrowFunctionExpression') {
    const parent = path.parent;
    if (parent && parent.type === 'VariableDeclarator' && parent.id && parent.id.type === 'Identifier') {
      name = parent.id.name;
    } else if (parent && parent.type === 'AssignmentExpression' && parent.left && parent.left.type === 'Identifier') {
      name = parent.left.name;
    } else if (parent && parent.type === 'ObjectProperty' && parent.key) {
      name = parent.key.name || parent.key.value || '';
    }
  }
  
  // 组件名必须首字母大写
  if (!name || name[0] !== name[0].toUpperCase() || name[0] === '_') {
    return false;
  }
  
  return hasJSXReturn(node);
}

/**
 * 检查函数体是否包含 JSX 返回
 */
function hasJSXReturn(node) {
  if (!node.body) return false;
  let found = false;
  try {
    babelTraverse({ type: 'Program', body: [node] }, {
      JSXElement() { found = true; },
      JSXFragment() { found = true; },
      noScope: true,
    }, undefined, undefined);
  } catch (e) {
    // fallback
  }
  return found;
}

/**
 * 判断函数是否为自定义 Hook（以 use 开头）
 */
function isCustomHook(path) {
  const node = path.node;
  let name = '';
  
  if (node.type === 'FunctionDeclaration') {
    name = node.id ? node.id.name : '';
  } else if (node.type === 'FunctionExpression' || node.type === 'ArrowFunctionExpression') {
    const parent = path.parent;
    if (parent && parent.type === 'VariableDeclarator' && parent.id && parent.id.type === 'Identifier') {
      name = parent.id.name;
    } else if (parent && parent.type === 'AssignmentExpression' && parent.left && parent.left.type === 'Identifier') {
      name = parent.left.name;
    }
  }
  
  return /^use[A-Z]/.test(name);
}

/**
 * 向上查找最近的函数作用域
 */
function findEnclosingFunction(path) {
  let p = path.parentPath;
  while (p) {
    if (p.isFunction()) return p;
    p = p.parentPath;
  }
  return null;
}

/**
 * Hook 调用是否在合法上下文中（函数组件 / 自定义 Hook）
 */
function isInValidHookContext(path) {
  const funcPath = findEnclosingFunction(path);
  if (!funcPath) return false;
  return isReactFunctionComponent(funcPath) || isCustomHook(funcPath);
}

/**
 * Hook 调用是否在条件判断或循环中
 */
function isInConditionalOrLoop(path) {
  let p = path.parentPath;
  while (p && !p.isFunction()) {
    if (
      p.isIfStatement() ||
      p.isForStatement() ||
      p.isForInStatement() ||
      p.isForOfStatement() ||
      p.isWhileStatement() ||
      p.isDoWhileStatement() ||
      p.isSwitchStatement() ||
      p.isSwitchCase() ||
      p.isConditionalExpression() ||
      p.isLogicalExpression()
    ) {
      return true;
    }
    p = p.parentPath;
  }
  return false;
}

/**
 * 判断 CallExpression 是否是 React Hook 调用
 */
function isHookCall(node) {
  const callee = node.callee;
  let name = '';
  if (callee.type === 'Identifier') {
    name = callee.name;
  } else if (callee.type === 'MemberExpression' && callee.property && callee.property.type === 'Identifier') {
    name = callee.property.name;
  }
  return /^use[A-Z]/.test(name) || _KNOWN_HOOKS.has(name);
}

const _KNOWN_HOOKS = new Set([
  'useState', 'useEffect', 'useCallback', 'useMemo', 'useRef',
  'useReducer', 'useContext', 'useLayoutEffect',
]);

function getHookName(node) {
  const callee = node.callee;
  if (callee.type === 'Identifier') return callee.name;
  if (callee.type === 'MemberExpression' && callee.property && callee.property.type === 'Identifier') {
    return callee.property.name;
  }
  return '';
}

/**
 * 获取 useEffect/useCallback/useMemo 的依赖数组
 */
function getDepArray(node) {
  const args = node.arguments || [];
  if (args.length < 2) {
    return { deps: null, hasDepsArg: false };
  }
  const depArg = args[1];
  if (depArg.type === 'ArrayExpression') {
    return { deps: depArg.elements, hasDepsArg: true };
  }
  return { deps: null, hasDepsArg: true };
}

/**
 * 从依赖数组中提取标识符名称
 */
function extractDepIdentifiers(deps) {
  if (!deps) return [];
  const names = new Set();
  for (const el of deps) {
    if (!el) continue;
    collectIdentifiers(el, names);
  }
  return [...names];
}

// 全局忽略的标识符（内置全局对象/函数、React API 等）
const GLOBAL_IGNORE_SET = new Set([
  'React', 'window', 'document', 'console', 'navigator', 'location',
  'setTimeout', 'setInterval', 'clearTimeout', 'clearInterval',
  'fetch', 'Promise', 'Math', 'JSON', 'Object', 'Array', 'String',
  'Number', 'Boolean', 'Date', 'Error', 'RegExp', 'Map', 'Set',
  'WeakMap', 'WeakSet', 'Symbol', 'BigInt', 'isNaN', 'parseInt',
  'parseFloat', 'encodeURI', 'decodeURI', 'encodeURIComponent',
  'decodeURIComponent', 'Infinity', 'NaN', 'undefined',
  'requestAnimationFrame', 'cancelAnimationFrame',
  'localStorage', 'sessionStorage', 'history',
  'URL', 'URLSearchParams', 'FormData', 'Blob', 'File',
  'TextEncoder', 'TextDecoder',
  'process', 'module', 'require', 'exports',
  'useState', 'useEffect', 'useCallback', 'useMemo', 'useRef',
  'useReducer', 'useContext', 'useLayoutEffect', 'useImperativeHandle',
  'useDebugValue', 'useDeferredValue', 'useTransition', 'useId',
  'useSyncExternalStore', 'useInsertionEffect',
]);

/**
 * 提取闭包变量：在回调函数中引用但未在其中声明的标识符
 */
function getClosureVariables(path, funcNode) {
  const usedInCallback = new Set();
  const declaredInCallback = new Set();
  
  // 先收集函数体内声明的所有变量
  _collectDeclarations(funcNode.body, declaredInCallback);
  
  // 收集顶层参数
  for (const p of funcNode.params || []) {
    if (p.type === 'Identifier') declaredInCallback.add(p.name);
    else if (p.type === 'ObjectPattern' || p.type === 'ArrayPattern') {
      collectPatternNames(p, declaredInCallback);
    }
  }
  
  // 收集在回调中使用的标识符
  _collectUsedIdentifiers(funcNode.body, usedInCallback);
  
  const closureVars = [];
  for (const name of usedInCallback) {
    if (!declaredInCallback.has(name)) {
      closureVars.push(name);
    }
  }
  return closureVars;
}

/**
 * 收集节点内所有变量声明（函数内部的）
 */
function _collectDeclarations(node, declaredSet) {
  if (!node) return;
  
  babelTraverse(node, {
    VariableDeclarator(vdPath) {
      const id = vdPath.node.id;
      if (id.type === 'Identifier') declaredSet.add(id.name);
      else if (id.type === 'ObjectPattern') collectPatternNames(id, declaredSet);
      else if (id.type === 'ArrayPattern') collectPatternNames(id, declaredSet);
    },
    FunctionDeclaration(fdPath) {
      if (fdPath.node.id) declaredSet.add(fdPath.node.id.name);
    },
    FunctionExpression(fePath) {
      if (fePath.node.id) declaredSet.add(fePath.node.id.name);
      for (const param of fePath.node.params || []) {
        _addParamName(param, declaredSet);
      }
    },
    ArrowFunctionExpression(afPath) {
      for (const param of afPath.node.params || []) {
        _addParamName(param, declaredSet);
      }
    },
    CatchClause(ccPath) {
      if (ccPath.node.param && ccPath.node.param.type === 'Identifier') {
        declaredSet.add(ccPath.node.param.name);
      }
    },
    noScope: true,
  });
}

function _addParamName(param, names) {
  if (param.type === 'Identifier') names.add(param.name);
  else if (param.type === 'ObjectPattern' || param.type === 'ArrayPattern') {
    collectPatternNames(param, names);
  }
}

/**
 * 收集节点内所有使用的标识符（排除各种声明/属性上下文）
 */
function _collectUsedIdentifiers(node, usedSet) {
  if (!node) return;
  
  babelTraverse(node, {
    Identifier(idPath) {
      const name = idPath.node.name;
      if (_shouldSkipIdentifier(idPath)) return;
      usedSet.add(name);
    },
    noScope: true,
  });
}

/**
 * 判断标识符是否应该跳过（属性名、解构、声明左侧、函数名、对象key、导入说明符等）
 */
function _shouldSkipIdentifier(idPath) {
  const parent = idPath.parent;
  if (!parent) return false;
  const node = idPath.node;
  const ptype = parent.type;
  
  // 跳过属性访问的 property (obj.prop 中的 prop，非计算的)
  if (ptype === 'MemberExpression' && parent.property === node && !parent.computed) return true;
  
  // 跳过解构模式中的标识符
  if (ptype === 'ArrayPattern' || ptype === 'ObjectPattern') return true;
  
  // 跳过声明的左侧
  if (ptype === 'VariableDeclarator' && parent.id === node) return true;
  
  // 跳过函数名
  if ((ptype === 'FunctionDeclaration' || ptype === 'FunctionExpression') && parent.id === node) return true;
  
  // 跳过对象属性 key
  if (ptype === 'ObjectProperty' && parent.key === node && !parent.computed) return true;
  
  // 跳过导入说明符
  if (ptype === 'ImportSpecifier') return true;
  if (ptype === 'ImportDefaultSpecifier' || ptype === 'ImportNamespaceSpecifier') return true;
  
  return false;
}

/**
 * 收集当前组件内所有 useState 返回的 setter 函数名
 */
function collectSetStateSetters(path) {
  const setters = new Set();
  
  let compPath = path;
  while (compPath && !compPath.isProgram()) {
    if (compPath.isFunction() && (
      isReactFunctionComponent(compPath) || isCustomHook(compPath)
    )) {
      break;
    }
    compPath = compPath.parentPath;
  }
  
  if (!compPath || compPath.isProgram()) return setters;
  
  babelTraverse(compPath.node.body, {
    VariableDeclarator(vdPath) {
      const init = vdPath.node.init;
      if (!init || init.type !== 'CallExpression') return;
      if (!isHookCall(init) || getHookName(init) !== 'useState') return;
      const id = vdPath.node.id;
      if (id.type !== 'ArrayPattern' || id.elements.length < 2) return;
      const setter = id.elements[1];
      if (!setter || setter.type !== 'Identifier') return;
      setters.add(setter.name);
    },
    noScope: true,
  });
  
  return setters;
}

module.exports = {
  isReactFunctionComponent, hasJSXReturn, isCustomHook,
  findEnclosingFunction, isInValidHookContext, isInConditionalOrLoop,
  isHookCall, getHookName,
  getDepArray, extractDepIdentifiers,
  getClosureVariables,
  GLOBAL_IGNORE_SET, collectSetStateSetters,
};
