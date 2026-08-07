/**
 * Babel 依赖初始化（单例）
 * 所有 JS AST 模块共享同一份 babel 引用，避免重复加载
 */

let babelParser, babelTraverse, t;

try {
  babelParser = require('@babel/parser');
  babelTraverse = require('@babel/traverse').default;
  t = require('@babel/types');
} catch (_e) {
  babelParser = null;
  babelTraverse = null;
  t = null;
}

function isAvailable() {
  return babelParser !== null && babelTraverse !== null;
}

module.exports = {
  babelParser,
  babelTraverse,
  t,
  isAvailable,
};
