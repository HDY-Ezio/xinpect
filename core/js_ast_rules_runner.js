/**
 * JS/TS AST 规则执行器
 * 
 * 煋鉴 v4.4 前端 AST 规则引擎 - 执行层
 * 基于 @babel/traverse 单次遍历执行所有规则
 */

const { babelParser, babelTraverse } = require('./js_ast_babel.js');
const { makeIssue } = require('./js_ast_utils.js');
const { isHookCall, getHookName, getDepArray } = require('./js_ast_hook_utils.js');
const {
  _checkHooksRules, _checkEvalCall, _checkConsoleLog,
} = require('./js_ast_hook_rules.js');
const { recordVarDeclaration } = require('./js_ast_analysis.js');
const { RULES } = require('./js_ast_rule_defs.js');

/**
 * 判断标识符是否处于声明/定义上下文（应跳过使用跟踪）
 * 包括：属性名、声明左侧、导入说明符、函数名、对象key、解构模式等
 */
function _isDeclarationContext(path) {
  const parent = path.parent;
  const node = path.node;
  if (!parent) return false;
  const ptype = parent.type;
  
  // 跳过属性名 (obj.prop 中的 prop，非计算的)
  if (ptype === 'MemberExpression' && parent.property === node && !parent.computed) return true;
  
  // 跳过声明左侧
  if (ptype === 'VariableDeclarator' && parent.id === node) return true;
  
  // 跳过导入说明符
  if (ptype === 'ImportSpecifier') return true;
  if ((ptype === 'ImportDefaultSpecifier' || ptype === 'ImportNamespaceSpecifier') &&
      parent.local === node) return true;
  
  // 跳过函数名
  if ((ptype === 'FunctionDeclaration' || ptype === 'FunctionExpression') &&
      parent.id === node) return true;
  
  // 跳过对象属性 key
  if (ptype === 'ObjectProperty' && parent.key === node && !parent.computed) return true;
  
  // 跳过解构模式中的标识符
  if (_isInDestructuringPattern(path)) return true;
  
  return false;
}

function _isInDestructuringPattern(path) {
  const parent = path.parent;
  const node = path.node;
  if (!parent) return false;
  
  const isPatternChild = 
    parent.type === 'ArrayPattern' ||
    parent.type === 'ObjectPattern' ||
    (parent.type === 'ObjectProperty' && parent.value === node);
  
  if (!isPatternChild) return false;
  
  // 向上确认是否是声明/参数/赋值的左侧
  let p = path.parentPath;
  while (p && p.node) {
    if (p.isVariableDeclarator()) return true;
    if (p.isAssignmentExpression() && p.node.left === node) return true;
    if (p.isFunction()) {
      const params = p.node.params || [];
      return params.some(param => 
        param === node || 
        param.type === 'ArrayPattern' || 
        param.type === 'ObjectPattern'
      );
    }
    p = p.parentPath;
  }
  
  return false;
}

/**
 * 跟踪 Hook 返回值声明（HOOKS-006 前置数据收集）
 * 卫语句风格，降低嵌套
 */
function _trackHookDeclarations(node, state) {
  const init = node.init;
  if (!init) return;
  if (init.type !== 'CallExpression') return;
  if (!isHookCall(init)) return;

  const hookName = getHookName(init);
  const id = node.id;

  // useState 解构形式: [state, setState] = useState(...)
  if (hookName === 'useState' && id.type === 'ArrayPattern') {
    const elements = id.elements;
    if (!elements || elements.length < 2) return;
    const setter = elements[1];
    if (!setter || setter.type !== 'Identifier') return;
    state.hookDeclarations.push({
      name: setter.name,
      hookName,
      node: setter,
      kind: 'setter',
      used: false,
    });
    return;
  }

  // useState 非解构形式 - 跳过，无法可靠判断
  if (hookName === 'useState' && id.type === 'Identifier') return;

  // 单返回值 Hook: const value = useXxx(...)
  if (id.type !== 'Identifier') return;
  state.hookDeclarations.push({
    name: id.name,
    hookName,
    node: id,
    kind: 'return-value',
    used: false,
  });
}

/**
 * 记录导入声明（JS-001 前置数据收集）
 */
function _recordImportDeclarations(node, state) {
  const specs = node.specifiers || [];
  for (const spec of specs) {
    if (!spec.local) continue;
    if (spec.local.type !== 'Identifier') continue;
    state.declaredVars.set(spec.local.name, {
      node: spec.local,
      type: 'import',
      used: false,
    });
  }
}

/**
 * 跟踪标识符使用（JS-001 未使用变量 + HOOKS-006 未使用 setter）
 */
function _trackIdentifierUsage(path, state, enabledRules) {
  const needJS001 = enabledRules.has('JS-001');
  const needHooks006 = enabledRules.has('HOOKS-006');
  if (!needJS001 && !needHooks006) return;
  if (_isDeclarationContext(path)) return;

  const name = path.node.name;

  // JS-001: 标记为已使用
  if (needJS001) {
    const v = state.declaredVars.get(name);
    if (v) v.used = true;
  }

  // HOOKS-006: 标记 Hook 返回值已使用
  if (!needHooks006) return;
  for (const dec of state.hookDeclarations) {
    if (dec.name !== name) continue;
    dec.used = true;
  }
}

/**
 * JS-005: 检测空代码块
 * 仅报告有意义的父节点类型（控制流、函数、try/catch 等）
 */
const _EMPTY_BLOCK_PARENTS = new Set([
  'IfStatement', 'ForStatement', 'ForInStatement', 'ForOfStatement',
  'WhileStatement', 'DoWhileStatement',
  'FunctionDeclaration', 'FunctionExpression', 'ArrowFunctionExpression',
  'CatchClause', 'TryStatement',
]);

function _checkEmptyBlocks(ast, addIssue) {
  babelTraverse(ast, {
    BlockStatement(path) {
      const node = path.node;
      if (node.body.length !== 0) return;
      const parent = path.parent;
      if (!parent) return;
      if (!_EMPTY_BLOCK_PARENTS.has(parent.type)) return;
      addIssue('JS-005', node,
        `空的代码块 (${parent.type})`,
        '添加实现代码或注释说明为何为空');
    },
  });
}

/**
 * TS-003: 检测 ts-ignore/ts-expect-error 无注释
 */
function _checkTsIgnoreComments(ast, addIssue) {
  const comments = ast.comments || [];
  for (const comment of comments) {
    const text = comment.value.trim();
    const isIgnore = /^@ts-ignore/.test(text);
    const isExpectError = /^@ts-expect-error/.test(text);
    if (!isIgnore && !isExpectError) continue;

    const rest = text.replace(/^@ts-(ignore|expect-error)\s*/, '').trim();
    if (rest) continue;

    const loc = comment.loc || { start: { line: 0, column: 0 }, end: { line: 0, column: 0 } };
    const fakeNode = {
      loc: {
        start: { line: loc.start.line, column: loc.start.column },
        end: { line: loc.end.line, column: loc.end.column },
      }
    };
    const directive = text.split(' ')[0];
    addIssue('TS-003', fakeNode,
      `${directive} 指令缺少说明注释`,
      '在 ts-ignore/ts-expect-error 后添加注释说明原因');
  }
}

// ============================================================
function runRules(content, filename, ruleIds) {
  if (!babelParser || !babelTraverse) {
    return { issues: [], error: 'Babel parser not available' };
  }
  
  // 计算文件类型以选择插件
  const isTS = /\.tsx?$/.test(filename || '');
  const isJSX = /\.[jt]sx$/.test(filename || '');
  
  const plugins = [
    'jsx', 'objectRestSpread', 'classProperties',
    'asyncGenerators', 'dynamicImport', 'optionalChaining',
    'nullishCoalescingOperator',
    'decorators-legacy', 'exportDefaultFrom',
  ];
  if (isTS) plugins.push('typescript');
  
  let ast;
  try {
    ast = babelParser.parse(content, {
      sourceType: 'unambiguous',
      plugins: plugins,
      errorRecovery: true,
      tokens: false,
    });
  } catch (e) {
    return { issues: [], error: e.message };
  }
  
  const contentLines = content.split('\n');
  const issues = [];
  
  // 确定要执行的规则
  // ruleIds 为空或未提供时执行所有规则
  const enabledRules = ruleIds && ruleIds.length > 0
    ? new Set(ruleIds.filter(id => RULES[id]))
    : new Set(Object.keys(RULES));
  
  function addIssue(ruleId, node, message, fix) {
    const rule = RULES[ruleId];
    if (!rule) return;
    issues.push(makeIssue(ruleId, node, message || rule.description, rule.severity, fix, contentLines));
  }
  
  // 状态跟踪
  const state = {
    // HOOKS-006: 跟踪 hook 返回值的使用情况
    hookDeclarations: [], // [{ name, hookName, node, setterName, used }]
    // JS-001: 变量/导入声明与使用
    declaredVars: new Map(), // name -> { node, type: 'import'|'var', used: false }
    // HOOKS-001/002 上下文
    currentFunction: null,
  };
  
  babelTraverse(ast, {
    // ---------- HOOKS-001: Hook 调用位置合法性 ----------
    // ---------- HOOKS-002: Hook 在条件/循环中 ----------
    CallExpression(path) {
      const node = path.node;
      const isHook = isHookCall(node);
      const hookName = isHook ? getHookName(node) : '';
      
      // ---------- HOOKS 相关规则（仅 Hook 调用时执行）----------
      if (isHook) {
        _checkHooksRules(path, node, hookName, enabledRules, addIssue);
      }
      
      // ---------- JS-003: eval() 使用 ----------
      _checkEvalCall(node, enabledRules, addIssue);
      
      // ---------- JS-004: console.log 遗留 ----------
      _checkConsoleLog(node, enabledRules, addIssue);
    },
    
    // ---------- HOOKS-006: 跟踪 Hook 返回值声明 ----------
    VariableDeclarator(path) {
      const node = path.node;
      _trackHookDeclarations(node, state);
      
      // JS-001: 记录变量声明
      if (enabledRules.has('JS-001')) {
        recordVarDeclaration(node.id, node);
      }
    },
    
    // ---------- JS-001: 导入声明 ----------
    ImportDeclaration(path) {
      if (!enabledRules.has('JS-001')) return;
      _recordImportDeclarations(path.node, state);
    },
    
    // ---------- JS-001: 标识符使用跟踪 ----------
    Identifier(path) {
      _trackIdentifierUsage(path, state, enabledRules);
    },
    
    // ---------- JS-002: == 运算符 ----------
    BinaryExpression(path) {
      if (!enabledRules.has('JS-002')) return;
      const node = path.node;
      if (node.operator === '==' || node.operator === '!=') {
        addIssue('JS-002', node,
          `使用了 ${node.operator} 运算符，存在隐式类型转换风险`,
          `建议使用 ${node.operator === '==' ? '===' : '!=='} 进行严格比较`);
      }
    },
    
    // ---------- TS-001: any 类型 ----------
    TSAnyKeyword(path) {
      if (!enabledRules.has('TS-001')) return;
      addIssue('TS-001', path.node,
        '使用了 any 类型，降低了 TypeScript 的类型安全性',
        '考虑使用 unknown 或具体类型替代 any');
    },
    
    // ---------- TS-002: 非空断言 ----------
    TSNonNullExpression(path) {
      if (!enabledRules.has('TS-002')) return;
      addIssue('TS-002', path.node,
        '使用了非空断言 !，绕过了 TypeScript 类型检查',
        '使用类型守卫或可选链替代非空断言');
    },
    
    // ---------- JS-005: 空代码块 ----------
    // 在 Program 退出时收集空块（通过遍历）
  });
  
  // ---------- HOOKS-006: 报告未使用的 Hook 返回值 ----------
  if (enabledRules.has('HOOKS-006')) {
    for (const dec of state.hookDeclarations) {
      if (!dec.used) {
        const desc = dec.kind === 'setter' 
          ? `useState 的 setter ${dec.name} 未被使用`
          : `Hook ${dec.hookName} 的返回值 ${dec.name} 未被使用`;
        addIssue('HOOKS-006', dec.node, desc,
          dec.kind === 'setter' 
            ? '如果不需要 setter，考虑使用变量或 useRef 替代 useState'
            : '移除未使用的 Hook 或使用其返回值');
      }
    }
  }
  
  // ---------- JS-001: 报告未使用的变量/导入 ----------
  if (enabledRules.has('JS-001')) {
    for (const [name, info] of state.declaredVars) {
      if (!info.used && !/^_/.test(name)) {
        // 跳过以 _ 开头的变量（惯例表示有意忽略）
        const desc = info.type === 'import' 
          ? `导入的 ${name} 未被使用`
          : `变量 ${name} 声明后未被使用`;
        addIssue('JS-001', info.node, desc, '移除未使用的声明以保持代码整洁');
      }
    }
  }
  
  // ---------- JS-005: 空代码块 ----------
  if (enabledRules.has('JS-005')) {
    _checkEmptyBlocks(ast, addIssue);
  }
  
  // ---------- TS-003: ts-ignore/ts-expect-error 无注释 ----------
  if (enabledRules.has('TS-003')) {
    _checkTsIgnoreComments(ast, addIssue);
  }
  
  return { issues, error: null };
}

/**
 * 判断一个表达式是否为"复杂计算"
 * 函数调用、复杂运算、对象/数组字面量（大的）等
 */
// ============================================================
// 导出
// ============================================================

module.exports = {
  runRules,
  RULES,
};
