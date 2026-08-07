/**
 * JS/TS AST 基础工具函数
 * 
 * 位置计算、问题构造、标识符/模式提取等纯工具函数
 * 不依赖 babel，可独立使用
 */

function getLine(node) {
  return node.loc ? node.loc.start.line : 0;
}

function getCol(node) {
  return node.loc ? node.loc.start.column + 1 : 0;
}

function getEndLine(node) {
  return node.loc ? node.loc.end.line : 0;
}

function getEndCol(node) {
  return node.loc ? node.loc.end.column + 1 : 0;
}

function makeIssue(ruleId, node, message, severity, fix, contentLines) {
  const line = getLine(node);
  const snippet = contentLines[line - 1] ? contentLines[line - 1].trim().slice(0, 120) : '';
  return {
    ruleId,
    message,
    line,
    col: getCol(node),
    endLine: getEndLine(node),
    endCol: getEndCol(node),
    severity,
    fix: fix || '',
    snippet,
  };
}

/**
 * 递归收集节点中的所有标识符
 */
function collectIdentifiers(node, names) {
  if (!node) return;
  if (node.type === 'Identifier') {
    names.add(node.name);
    return;
  }
  for (const key of Object.keys(node)) {
    if (key === 'loc' || key === 'leadingComments' || key === 'trailingComments') continue;
    const val = node[key];
    _collectFromValue(val, names);
  }
}

function _collectFromValue(val, names) {
  if (!val) return;
  if (typeof val !== 'object') return;
  if (typeof val.type === 'string') {
    collectIdentifiers(val, names);
    return;
  }
  if (Array.isArray(val)) {
    for (const item of val) {
      _collectFromValue(item, names);
    }
  }
}

/**
 * 从解构模式中收集所有标识符名
 */
function collectPatternNames(pattern, names) {
  if (!pattern) return;
  if (pattern.type === 'Identifier') {
    names.add(pattern.name);
  } else if (pattern.type === 'ObjectPattern') {
    for (const prop of pattern.properties || []) {
      if (prop.type === 'RestElement' && prop.argument) {
        names.add(prop.argument.name);
      } else if (prop.value) {
        collectPatternNames(prop.value, names);
      }
    }
  } else if (pattern.type === 'ArrayPattern') {
    for (const el of pattern.elements || []) {
      if (el) collectPatternNames(el, names);
    }
  }
}

module.exports = {
  getLine, getCol, getEndLine, getEndCol,
  makeIssue,
  collectIdentifiers, collectPatternNames,
};
