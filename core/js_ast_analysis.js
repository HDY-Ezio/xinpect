/**
 * JS/TS AST 分析辅助工具
 * 
 * 表达式复杂度判断、变量声明记录等辅助分析函数
 */

/**
 * 判断一个表达式是否为"复杂计算"
 * 函数调用、复杂运算、对象/数组字面量（大的）等
 */
function isComplexComputation(node) {
  if (!node) return false;
  
  // 函数调用
  if (node.type === 'CallExpression') return true;
  
  // New 表达式
  if (node.type === 'NewExpression') return true;
  
  // 复杂的二元运算
  if (node.type === 'BinaryExpression' || node.type === 'LogicalExpression') {
    return _hasComplexChild(node);
  }
  
  // 三元表达式
  if (node.type === 'ConditionalExpression') return true;
  
  // 模板字符串（包含变量插值的）
  if (node.type === 'TemplateLiteral' && node.expressions && node.expressions.length > 0) {
    return true;
  }
  
  // 对象/数组字面量（较大的）
  if (node.type === 'ObjectExpression' && (node.properties || []).length > 5) return true;
  if (node.type === 'ArrayExpression' && (node.elements || []).length > 5) return true;
  
  return false;
}

function _hasComplexChild(node) {
  let hasComplex = false;
  function check(n) {
    if (!n || hasComplex) return;
    if (n.type === 'CallExpression' || n.type === 'NewExpression') hasComplex = true;
    if (n.type === 'ConditionalExpression') hasComplex = true;
    if (n.type === 'MemberExpression' && n.computed) hasComplex = true;
    if (n.left) check(n.left);
    if (n.right) check(n.right);
  }
  check(node);
  return hasComplex;
}

/**
 * JS-001 辅助：记录变量声明（占位实现）
 * 复杂的作用域分析需要 scope manager，当前版本暂不精确检测
 */
function recordVarDeclaration(id, declaratorNode) {
  // 占位实现
}

module.exports = {
  isComplexComputation,
  recordVarDeclaration,
};
